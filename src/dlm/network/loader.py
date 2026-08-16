"""OSMnx road-network acquisition, strong connectivity, caching, and statistics."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox

from dlm.config import get_settings
from dlm.network.travel_time import SpeedDefaults, annotate_travel_times, load_speed_defaults

LOGGER = logging.getLogger(__name__)

# WGS84 rectangular study envelope covering Dublin Bay and the urban/suburban M50 catchment.
# The rectangle is deliberately explicit and cache-keyed; it is not claimed to be the M50 polygon.
M50_CATCHMENT_BBOX = (-6.50, 53.20, -6.05, 53.47)
CACHE_SCHEMA_VERSION = 1


class NetworkBuildError(RuntimeError):
    """Raised when a usable directed road graph cannot be built or loaded."""


@dataclass(frozen=True)
class NetworkSpec:
    """Complete, hashable specification of a Dublin road-network request.

    Parameters
    ----------
    area_name
        Human-readable study-area identifier.
    bbox
        WGS84 bounding box as ``(west, south, east, north)``.
    place_query
        Optional OSM/Nominatim place query. When set, it is tried before ``bbox``.
    network_type
        OSMnx network filter. ``drive`` respects directed one-way restrictions.
    simplify
        Whether OSMnx should simplify topology before the strong-component step.
    """

    area_name: str = "m50_catchment"
    bbox: tuple[float, float, float, float] = M50_CATCHMENT_BBOX
    place_query: str | None = None
    network_type: str = "drive"
    simplify: bool = True

    def __post_init__(self) -> None:
        """Validate the request before it can influence a cache key or download."""

        west, south, east, north = self.bbox
        if not self.area_name.strip():
            raise ValueError("area_name cannot be empty")
        if not (-11 <= west < east <= -5 and 51 <= south < north <= 56):
            raise ValueError("bbox must be ordered WGS84 coordinates within Ireland")
        if self.network_type != "drive":
            raise ValueError("Stage 1 supports only network_type='drive'")


@dataclass(frozen=True)
class NetworkStats:
    """Auditable graph statistics with lengths in metres and proportions in percent."""

    nodes: int
    edges: int
    strongly_connected: bool
    total_edge_length_m: float
    osm_speed_edges: int
    imputed_speed_edges: int
    osm_speed_percent: float
    imputed_speed_percent: float

    def as_dict(self) -> dict[str, int | float | bool]:
        """Return a JSON-serialisable, deterministically ordered payload."""

        return asdict(self)


@dataclass(frozen=True)
class NetworkBuildResult:
    """A loaded graph plus cache and timing evidence."""

    graph: nx.MultiDiGraph
    cache_path: Path
    cache_hit: bool
    elapsed_seconds: float
    stats: NetworkStats


def cache_key(
    spec: NetworkSpec,
    *,
    osmnx_version: str | None = None,
    speed_defaults: SpeedDefaults | None = None,
) -> str:
    """Return the first 16 hex characters of the complete network-input hash.

    Parameters
    ----------
    spec
        Area and OSMnx graph-construction inputs.
    osmnx_version
        Version override for tests. The installed version is used by default.
    speed_defaults
        Speed-table override. Packaged values are used by default.

    Returns
    -------
    str
        Stable cache key incorporating area, build flags, OSMnx, and speed policy.
    """

    defaults = speed_defaults or load_speed_defaults()
    payload = {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "osmnx_version": osmnx_version or ox.__version__,
        "spec": asdict(spec),
        "speed_defaults": {
            "fallback_kph": defaults.fallback_kph,
            "highway_kph": defaults.highway_kph,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def build_or_load_network(
    spec: NetworkSpec | None = None,
    *,
    cache_dir: str | Path | None = None,
    force_rebuild: bool = False,
    speed_defaults: SpeedDefaults | None = None,
    downloader: Callable[[NetworkSpec], nx.MultiDiGraph] | None = None,
) -> NetworkBuildResult:
    """Build the directed M50 graph once, then load its validated cache thereafter.

    Parameters
    ----------
    spec
        Network request. The explicit M50 catchment specification is the default.
    cache_dir
        Directory for GraphML, a fast local binary sidecar, and JSON metadata. Project settings
        are used when omitted.
    force_rebuild
        Ignore an existing matching cache and download again.
    speed_defaults
        Optional validated speed table, mainly for controlled experiments.
    downloader
        Optional download function used by deterministic fixture tests.

    Returns
    -------
    NetworkBuildResult
        Directed strongly connected graph, cache location, timing, and statistics.
    """

    started = time.perf_counter()
    active_spec = spec or NetworkSpec()
    active_defaults = speed_defaults or load_speed_defaults()
    directory = Path(cache_dir) if cache_dir is not None else get_settings().resolved_cache_dir
    directory.mkdir(parents=True, exist_ok=True)
    key = cache_key(active_spec, speed_defaults=active_defaults)
    graph_path = directory / f"{key}.graphml"
    binary_path = directory / f"{key}.pickle"
    metadata_path = directory / f"{key}.json"

    if graph_path.exists() and not force_rebuild:
        graph, stats = _load_cached_graph(graph_path, binary_path, key)
        return NetworkBuildResult(
            graph=graph,
            cache_path=graph_path,
            cache_hit=True,
            elapsed_seconds=time.perf_counter() - started,
            stats=stats,
        )

    download = downloader or _download_graph
    try:
        raw_graph = download(active_spec)
    except Exception as exc:
        raise NetworkBuildError(
            "OpenStreetMap road-network download failed. Check internet access and retry; "
            "an existing matching cache would avoid this download."
        ) from exc
    if not isinstance(raw_graph, nx.MultiDiGraph) or raw_graph.number_of_nodes() == 0:
        raise NetworkBuildError("OSMnx returned an empty graph or an unexpected graph type")

    graph = ox.truncate.largest_component(raw_graph, strongly=True).copy()
    annotate_travel_times(graph, active_defaults)
    stats = network_stats(graph)
    if not stats.strongly_connected:
        raise NetworkBuildError("Largest-component extraction did not produce a strong graph")

    graph.graph.update(
        {
            "dlm_area_name": active_spec.area_name,
            "dlm_cache_key": key,
            "dlm_cache_schema_version": CACHE_SCHEMA_VERSION,
            "dlm_network_type": active_spec.network_type,
            "dlm_osmnx_version": ox.__version__,
        }
    )
    _save_graph_atomically(graph, graph_path)
    _save_binary_atomically(graph, binary_path)
    metadata = {
        "accessed_at_utc": datetime.now(UTC).isoformat(),
        "binary_file": binary_path.name,
        "cache_key": key,
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "graph_file": graph_path.name,
        "osmnx_version": ox.__version__,
        "spec": asdict(active_spec),
        "stats": stats.as_dict(),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return NetworkBuildResult(
        graph=graph,
        cache_path=graph_path,
        cache_hit=False,
        elapsed_seconds=time.perf_counter() - started,
        stats=stats,
    )


def network_stats(graph: nx.MultiDiGraph) -> NetworkStats:
    """Calculate connectivity, length, and speed-provenance evidence for a graph.

    Parameters
    ----------
    graph
        Travel-time-annotated directed road graph.

    Returns
    -------
    NetworkStats
        Counts, edge length in metres, and OSM/imputed speed percentages.
    """

    edges = graph.number_of_edges()
    osm_edges = 0
    imputed_edges = 0
    total_length_m = 0.0
    for _, _, _, data in graph.edges(keys=True, data=True):
        try:
            total_length_m += float(data.get("length", 0.0))
        except (TypeError, ValueError) as exc:
            raise NetworkBuildError("Graph contains a non-numeric edge length") from exc
        if data.get("speed_source") == "osm":
            osm_edges += 1
        elif data.get("speed_source") == "imputed":
            imputed_edges += 1
    denominator = edges or 1
    return NetworkStats(
        nodes=graph.number_of_nodes(),
        edges=edges,
        strongly_connected=bool(graph) and nx.is_strongly_connected(graph),
        total_edge_length_m=round(total_length_m, 3),
        osm_speed_edges=osm_edges,
        imputed_speed_edges=imputed_edges,
        osm_speed_percent=round(osm_edges / denominator * 100.0, 3),
        imputed_speed_percent=round(imputed_edges / denominator * 100.0, 3),
    )


def _download_graph(spec: NetworkSpec) -> nx.MultiDiGraph:
    """Download with a place query when supplied, falling back to the explicit bbox."""

    kwargs: dict[str, Any] = {
        "network_type": spec.network_type,
        "simplify": spec.simplify,
        "retain_all": True,
    }
    if spec.place_query:
        try:
            return ox.graph.graph_from_place(spec.place_query, **kwargs)
        except Exception:
            LOGGER.warning(
                "Place query failed; falling back to the configured M50 bounding box",
                exc_info=True,
            )
    return ox.graph.graph_from_bbox(spec.bbox, **kwargs)


def _save_graph_atomically(graph: nx.MultiDiGraph, destination: Path) -> None:
    """Save GraphML beside its final path, then atomically replace the destination."""

    temporary = destination.with_suffix(".tmp.graphml")
    ox.io.save_graphml(graph, temporary)
    os.replace(temporary, destination)


def _load_cached_graph(
    graph_path: Path,
    binary_path: Path,
    expected_key: str,
) -> tuple[nx.MultiDiGraph, NetworkStats]:
    """Load a trusted local binary sidecar, falling back to portable GraphML.

    The sidecar is an optimisation generated only by this loader. A missing, corrupt, stale, or
    incompatible sidecar is never fatal: GraphML is loaded, validated, and used to replace it.
    Users must not copy untrusted pickle files into the cache directory.
    """

    if binary_path.exists():
        try:
            with binary_path.open("rb") as handle:
                graph = pickle.load(handle)  # noqa: S301 - trusted, project-generated cache only
            stats = _validate_cached_graph(graph, binary_path, expected_key)
            return graph, stats
        except (
            AttributeError,
            EOFError,
            ImportError,
            IndexError,
            NetworkBuildError,
            OSError,
            pickle.PickleError,
            TypeError,
            ValueError,
        ) as exc:
            LOGGER.warning(
                "Fast graph cache could not be used; rebuilding it from GraphML: %s",
                binary_path,
                exc_info=exc,
            )

    graph = ox.io.load_graphml(graph_path)
    stats = _validate_cached_graph(graph, graph_path, expected_key)
    _save_binary_atomically(graph, binary_path)
    return graph, stats


def _validate_cached_graph(
    graph: object,
    source: Path,
    expected_key: str,
) -> NetworkStats:
    """Reject a cache whose type, identity, or directed connectivity is invalid."""

    if not isinstance(graph, nx.MultiDiGraph):
        raise NetworkBuildError(f"Cached graph has an unexpected type: {source}")
    if graph.graph.get("dlm_cache_key") != expected_key:
        raise NetworkBuildError(f"Cached graph key does not match its request: {source}")
    stats = network_stats(graph)
    if not stats.strongly_connected:
        raise NetworkBuildError(f"Cached graph is not strongly connected: {source}")
    return stats


def _save_binary_atomically(graph: nx.MultiDiGraph, destination: Path) -> None:
    """Write a fast local graph sidecar atomically; GraphML remains authoritative."""

    temporary = destination.with_suffix(".tmp.pickle")
    try:
        with temporary.open("wb") as handle:
            pickle.dump(graph, handle, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
