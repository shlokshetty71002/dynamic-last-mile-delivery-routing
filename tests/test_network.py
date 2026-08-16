"""Stage 0 configuration and deterministic Stage 1 road-network tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import networkx as nx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from dlm.cli import app
from dlm.config import JsonFormatter, Settings
from dlm.network.loader import (
    NetworkBuildResult,
    NetworkSpec,
    NetworkStats,
    build_or_load_network,
    cache_key,
)
from dlm.network.snapping import InvalidCoordinateError, SnapTooFarError, snap_to_node
from dlm.network.travel_time import SpeedDefaults, annotate_travel_times, load_speed_defaults


def test_stage_zero_settings_have_deterministic_seed_and_units(tmp_path) -> None:
    """The foundation exposes the agreed seed and SI unit policy."""

    settings = Settings(project_root=tmp_path)

    assert settings.global_seed == 42
    assert settings.distance_unit == "metres"
    assert settings.time_unit == "seconds"
    assert settings.resolved_cache_dir == tmp_path / "data/cache"
    assert settings.resolved_results_dir == tmp_path / "results"


def test_environment_prefix_can_override_safe_settings(monkeypatch, tmp_path) -> None:
    """DLM-prefixed environment values override defaults without source edits."""

    monkeypatch.setenv("DLM_GLOBAL_SEED", "25206591")
    monkeypatch.setenv("DLM_LOG_LEVEL", "debug")

    settings = Settings(project_root=tmp_path)

    assert settings.global_seed == 25206591
    assert settings.log_level == "DEBUG"


def test_non_si_time_unit_is_rejected(tmp_path) -> None:
    """Changing the project-wide seconds convention fails loudly."""

    with pytest.raises(ValidationError, match="must be seconds"):
        Settings(project_root=tmp_path, time_unit="minutes")


def test_json_logging_is_machine_readable() -> None:
    """Structured logging emits a deterministic JSON record."""

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="dlm.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="foundation ready",
        args=(),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "dlm.test"
    assert payload["message"] == "foundation ready"
    assert "timestamp" in payload


def test_packaged_irish_speed_defaults_are_positive() -> None:
    """The Stage 1 YAML table is packaged, labelled in km/h, and valid."""

    defaults = load_speed_defaults()

    assert defaults.highway_kph["motorway"] == 100
    assert defaults.highway_kph["residential"] == 50
    assert defaults.fallback_kph == 50


def test_edge_travel_times_prefer_osm_speed_then_impute() -> None:
    """Explicit maxspeed wins; missing values use the external highway table."""

    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_edge(1, 2, length=1000.0, highway="primary", maxspeed="50")
    graph.add_edge(2, 1, length=1000.0, highway="residential")
    defaults = SpeedDefaults(
        highway_kph={"primary": 60.0, "residential": 40.0},
        fallback_kph=30.0,
    )

    annotate_travel_times(graph, defaults)

    outward = graph.edges[1, 2, 0]
    returned = graph.edges[2, 1, 0]
    assert outward["speed_kph"] == 50.0
    assert outward["speed_source"] == "osm"
    assert outward["travel_time"] == pytest.approx(72.0)
    assert returned["speed_kph"] == 40.0
    assert returned["speed_source"] == "imputed"
    assert returned["travel_time"] == pytest.approx(90.0)


def test_mph_and_multi_value_maxspeed_use_conservative_valid_value() -> None:
    """Mixed simplified-edge speeds are normalised to the lowest valid km/h value."""

    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_edge(
        1,
        2,
        length=100.0,
        highway="primary",
        maxspeed=["40 mph", "80"],
    )

    annotate_travel_times(
        graph,
        SpeedDefaults(highway_kph={"primary": 60.0}, fallback_kph=50.0),
    )

    assert graph.edges[1, 2, 0]["speed_kph"] == pytest.approx(64.37376)


def test_cache_key_covers_area_version_and_speed_policy() -> None:
    """Any input that changes graph meaning also changes its cache identity."""

    defaults = SpeedDefaults(highway_kph={"residential": 50.0}, fallback_kph=50.0)
    base = NetworkSpec()

    assert cache_key(base, osmnx_version="2.1.1", speed_defaults=defaults) == cache_key(
        base,
        osmnx_version="2.1.1",
        speed_defaults=defaults,
    )
    assert cache_key(base, osmnx_version="2.1.1", speed_defaults=defaults) != cache_key(
        NetworkSpec(bbox=(-6.49, 53.20, -6.05, 53.47)),
        osmnx_version="2.1.1",
        speed_defaults=defaults,
    )
    assert cache_key(base, osmnx_version="2.1.1", speed_defaults=defaults) != cache_key(
        base,
        osmnx_version="2.1.2",
        speed_defaults=defaults,
    )


def test_network_build_extracts_strong_component_and_reuses_cache(tmp_path) -> None:
    """The first build writes GraphML and the second run loads it without downloading."""

    calls = 0

    def downloader(_: NetworkSpec) -> nx.MultiDiGraph:
        nonlocal calls
        calls += 1
        return _fixture_graph(include_isolated=True)

    defaults = SpeedDefaults(
        highway_kph={"residential": 40.0, "primary": 60.0},
        fallback_kph=30.0,
    )
    first = build_or_load_network(
        cache_dir=tmp_path,
        speed_defaults=defaults,
        downloader=downloader,
    )
    second = build_or_load_network(
        cache_dir=tmp_path,
        speed_defaults=defaults,
        downloader=downloader,
    )

    assert calls == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.elapsed_seconds < 5.0
    assert second.stats.strongly_connected is True
    assert second.stats.nodes == 3
    assert second.stats.edges == 6
    assert second.stats.osm_speed_edges == 1
    assert second.stats.imputed_speed_edges == 5
    assert first.cache_path.exists()
    assert first.cache_path.with_suffix(".json").exists()


def test_directed_graph_does_not_invent_reverse_one_way_edge() -> None:
    """A one-way fixture edge remains directed instead of receiving a fake reverse edge."""

    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=-6.26, y=53.34)
    graph.add_node(2, x=-6.25, y=53.34)
    graph.add_edge(1, 2, length=100.0, highway="residential", oneway=True)

    assert graph.has_edge(1, 2)
    assert not graph.has_edge(2, 1)


def test_safe_snapping_returns_nearest_node_and_rejects_irish_sea() -> None:
    """Nearby Dublin input snaps, while a remote sea coordinate fails loudly."""

    graph = _fixture_graph()

    snapped = snap_to_node(graph, 53.3001, -6.2999, max_distance_m=100.0)

    assert snapped.node == 1
    assert snapped.distance_m < 20.0
    with pytest.raises(SnapTooFarError, match="supported M50 road-network area"):
        snap_to_node(graph, 53.35, -5.80, max_distance_m=500.0)


def test_safe_snapping_validates_latitude() -> None:
    """Invalid WGS84 input is rejected before any nearest-node calculation."""

    with pytest.raises(InvalidCoordinateError, match="Latitude"):
        snap_to_node(_fixture_graph(), 91.0, -6.26)


def test_network_stats_cli_emits_machine_readable_json(monkeypatch, tmp_path) -> None:
    """The Stage 1 stats command exposes library evidence without UI-only logic."""

    graph = _fixture_graph()
    result = NetworkBuildResult(
        graph=graph,
        cache_path=Path(tmp_path) / "fixture.graphml",
        cache_hit=True,
        elapsed_seconds=0.123,
        stats=NetworkStats(
            nodes=3,
            edges=6,
            strongly_connected=True,
            total_edge_length_m=600.0,
            osm_speed_edges=1,
            imputed_speed_edges=5,
            osm_speed_percent=16.667,
            imputed_speed_percent=83.333,
        ),
    )
    monkeypatch.setattr("dlm.cli.build_or_load_network", lambda *args, **kwargs: result)

    response = CliRunner().invoke(app, ["network", "stats"])

    assert response.exit_code == 0
    payload = json.loads(response.stdout)
    assert payload["strongly_connected"] is True
    assert payload["nodes"] == 3
    assert payload["cache_hit"] is True


def _fixture_graph(*, include_isolated: bool = False) -> nx.MultiDiGraph:
    """Return a tiny directed graph with one explicit speed and known connectivity."""

    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=-6.3000, y=53.3000)
    graph.add_node(2, x=-6.2900, y=53.3000)
    graph.add_node(3, x=-6.2900, y=53.3100)
    edges = [
        (1, 2, {"maxspeed": "50", "highway": "primary"}),
        (2, 1, {"highway": "residential"}),
        (2, 3, {"highway": "primary"}),
        (3, 2, {"highway": "primary"}),
        (3, 1, {"highway": "residential"}),
        (1, 3, {"highway": "residential"}),
    ]
    for origin, destination, attributes in edges:
        graph.add_edge(origin, destination, length=100.0, **attributes)
    if include_isolated:
        graph.add_node(99, x=-6.40, y=53.40)
    return graph
