"""Irish road-speed imputation and deterministic free-flow travel times."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import networkx as nx
import yaml

_NUMBER = re.compile(r"(?<![A-Za-z])(?P<value>\d+(?:\.\d+)?)")


class SpeedConfigurationError(ValueError):
    """Raised when the external Irish speed-default table is invalid."""


class TravelTimeError(ValueError):
    """Raised when an edge cannot receive a valid speed or travel time."""


@dataclass(frozen=True)
class SpeedDefaults:
    """Validated free-flow speed defaults in kilometres per hour.

    Parameters
    ----------
    highway_kph
        Mapping from OpenStreetMap ``highway`` values to imputed speeds in km/h.
    fallback_kph
        Speed in km/h for an unrecognised or missing highway type.
    """

    highway_kph: dict[str, float]
    fallback_kph: float


def load_speed_defaults(path: str | Path | None = None) -> SpeedDefaults:
    """Load and validate the versioned Irish speed table.

    Parameters
    ----------
    path
        Optional YAML path. When omitted, the packaged Stage 1 table is used.

    Returns
    -------
    SpeedDefaults
        Positive speeds expressed in kilometres per hour.
    """

    if path is None:
        resource = files("dlm.network").joinpath("irish_speed_defaults.yaml")
        with resource.open("r", encoding="utf-8") as stream:
            payload = yaml.safe_load(stream)
    else:
        with Path(path).open("r", encoding="utf-8") as stream:
            payload = yaml.safe_load(stream)

    if not isinstance(payload, dict) or payload.get("units") != "km/h":
        raise SpeedConfigurationError("Speed defaults must be a YAML mapping with units: km/h")
    raw_table = payload.get("highway_kph")
    if not isinstance(raw_table, dict) or not raw_table:
        raise SpeedConfigurationError("highway_kph must be a non-empty mapping")

    try:
        table = {str(key): float(value) for key, value in raw_table.items()}
        fallback = float(payload["fallback_kph"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SpeedConfigurationError("All configured speeds must be numeric") from exc
    if fallback <= 0 or any(value <= 0 for value in table.values()):
        raise SpeedConfigurationError("All configured speeds must be greater than zero km/h")
    return SpeedDefaults(highway_kph=table, fallback_kph=fallback)


def annotate_travel_times(
    graph: nx.MultiDiGraph,
    defaults: SpeedDefaults | None = None,
) -> nx.MultiDiGraph:
    """Add ``speed_kph``, ``speed_source``, and ``travel_time`` to every edge.

    OpenStreetMap ``maxspeed`` wins when it contains a positive numeric value. Missing or
    non-numeric values use the external per-highway table. For simplified edges containing
    multiple speed tags, the lowest valid value is used conservatively. The graph is mutated
    and returned. Edge length must be in metres; travel time is written in seconds.

    Parameters
    ----------
    graph
        Directed road graph with an edge ``length`` attribute in metres.
    defaults
        Validated speed table. The packaged Irish defaults are loaded when omitted.

    Returns
    -------
    networkx.MultiDiGraph
        The same graph with complete speed and travel-time attributes.
    """

    active_defaults = defaults or load_speed_defaults()
    for u, v, key, data in graph.edges(keys=True, data=True):
        speed_kph = _parse_maxspeed_kph(data.get("maxspeed"))
        highway = _select_highway(data.get("highway"), active_defaults)
        if speed_kph is None:
            speed_kph = active_defaults.highway_kph.get(highway, active_defaults.fallback_kph)
            source = "imputed"
        else:
            source = "osm"

        try:
            length_m = float(data["length"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TravelTimeError(f"Edge {(u, v, key)!r} has no numeric length in metres") from exc
        if not math.isfinite(length_m) or length_m < 0 or speed_kph <= 0:
            raise TravelTimeError(f"Edge {(u, v, key)!r} has invalid length or speed")

        data["speed_kph"] = float(speed_kph)
        data["speed_source"] = source
        data["speed_highway"] = highway
        data["travel_time"] = length_m / (speed_kph * 1000.0 / 3600.0)
    return graph


def _parse_maxspeed_kph(value: Any) -> float | None:
    """Return the lowest valid OSM speed value in km/h, or ``None``."""

    if value is None:
        return None
    values = value if isinstance(value, (list, tuple, set)) else [value]
    parsed: list[float] = []
    for item in values:
        for token in str(item).split(";"):
            match = _NUMBER.search(token)
            if match is None:
                continue
            speed = float(match.group("value"))
            if "mph" in token.lower():
                speed *= 1.609344
            if math.isfinite(speed) and speed > 0:
                parsed.append(speed)
    return min(parsed) if parsed else None


def _select_highway(value: Any, defaults: SpeedDefaults) -> str:
    """Choose the first configured highway class, retaining a readable fallback label."""

    values = value if isinstance(value, (list, tuple, set)) else [value]
    labels = [str(item) for item in values if item is not None]
    for label in labels:
        if label in defaults.highway_kph:
            return label
    return labels[0] if labels else "unknown"
