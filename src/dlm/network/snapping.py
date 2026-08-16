"""Safe latitude/longitude to routable road-node snapping."""

from __future__ import annotations

import math
from collections.abc import Hashable
from dataclasses import dataclass

import networkx as nx
import numpy as np

EARTH_RADIUS_M = 6_371_009.0


class InvalidCoordinateError(ValueError):
    """Raised when latitude, longitude, or the snap guard is invalid."""


class GraphCoordinateError(ValueError):
    """Raised when graph nodes do not contain usable WGS84 coordinates."""


class SnapTooFarError(ValueError):
    """Raised when the nearest routable node exceeds the allowed distance."""


@dataclass(frozen=True)
class SnapResult:
    """Nearest routable node and great-circle distance from the input point.

    Attributes
    ----------
    node
        Graph node identifier.
    distance_m
        Great-circle distance from the input coordinate in metres.
    """

    node: Hashable
    distance_m: float


def snap_to_node(
    graph: nx.MultiDiGraph,
    lat: float,
    lon: float,
    *,
    max_distance_m: float = 500.0,
) -> SnapResult:
    """Snap a WGS84 coordinate to the nearest graph node with a distance guard.

    The vectorised great-circle calculation avoids optional spatial-index dependencies and is
    deterministic. It is appropriate for interactive points on the Stage 1 M50 graph.

    Parameters
    ----------
    graph
        Road graph whose nodes have ``x`` longitude and ``y`` latitude in EPSG:4326.
    lat
        Latitude in decimal degrees.
    lon
        Longitude in decimal degrees.
    max_distance_m
        Largest permitted point-to-node distance in metres.

    Returns
    -------
    SnapResult
        Nearest node identifier and distance in metres.

    Raises
    ------
    InvalidCoordinateError
        If the coordinate or maximum distance is invalid.
    GraphCoordinateError
        If the graph is empty or lacks usable node coordinates.
    SnapTooFarError
        If the nearest node is farther than ``max_distance_m``.
    """

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise InvalidCoordinateError("Latitude must be [-90, 90] and longitude [-180, 180]")
    if not math.isfinite(max_distance_m) or max_distance_m <= 0:
        raise InvalidCoordinateError("Maximum snap distance must be greater than zero metres")
    if graph.number_of_nodes() == 0:
        raise GraphCoordinateError("Cannot snap to an empty road network")

    node_ids: list[Hashable] = []
    lats: list[float] = []
    lons: list[float] = []
    try:
        for node, data in graph.nodes(data=True):
            node_ids.append(node)
            lats.append(float(data["y"]))
            lons.append(float(data["x"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise GraphCoordinateError(
            "Every road-network node must have numeric x=longitude and y=latitude"
        ) from exc

    distances = _great_circle_distances_m(lat, lon, np.asarray(lats), np.asarray(lons))
    nearest_index = int(np.argmin(distances))
    distance_m = float(distances[nearest_index])
    if distance_m > max_distance_m:
        raise SnapTooFarError(
            f"Location is {distance_m:.0f} m from the nearest routable road node, "
            f"exceeding the {max_distance_m:.0f} m limit. Choose a point inside the "
            "supported M50 road-network area."
        )
    return SnapResult(node=node_ids[nearest_index], distance_m=distance_m)


def _great_circle_distances_m(
    lat: float,
    lon: float,
    node_lats: np.ndarray,
    node_lons: np.ndarray,
) -> np.ndarray:
    """Return vectorised haversine distances in metres."""

    lat1 = np.deg2rad(lat)
    lon1 = np.deg2rad(lon)
    lat2 = np.deg2rad(node_lats)
    lon2 = np.deg2rad(node_lons)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        np.sin(delta_lat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))
