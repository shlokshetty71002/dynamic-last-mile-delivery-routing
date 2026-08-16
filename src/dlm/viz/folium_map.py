"""Interactive maps for selected stops, disruptions, and comparison routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx

from dlm.disruption.schema import DisruptionType, Scenario
from dlm.instance.schema import DeliveryInstance, NodeId
from dlm.simulation.metrics import ExperimentResult

DUBLIN_CENTRE = (53.3498, -6.2603)


class VisualisationDependencyError(RuntimeError):
    """Raised when an optional visualisation dependency is missing."""


def instance_map(instance: DeliveryInstance, *, zoom_start: int = 11):
    """Return a Folium map of the user-selected depot and dynamic stops."""

    folium = _folium()
    points = instance.points
    centre = (
        sum(point.lat for point in points) / len(points),
        sum(point.lon for point in points) / len(points),
    )
    map_object = folium.Map(location=centre, zoom_start=zoom_start, control_scale=True)
    folium.Marker(
        (instance.depot.lat, instance.depot.lon),
        tooltip=f"Depot: {instance.depot.label}",
        icon=folium.Icon(color="black", icon="home"),
    ).add_to(map_object)
    for number, stop in enumerate(instance.stops, start=1):
        folium.Marker(
            (stop.lat, stop.lon),
            tooltip=f"{number}. {stop.label}",
            icon=folium.Icon(color="blue", icon="info-sign"),
        ).add_to(map_object)
    return map_object


def comparison_map(
    graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    result: ExperimentResult,
    scenario: Scenario,
):
    """Return toggleable baseline, frozen, re-optimised, oracle, and disruption layers."""

    folium = _folium()
    map_object = instance_map(instance)
    layers = [
        ("T1 planned route", result.t1_paths, "#0072B2"),
        ("T2 frozen route under disruption", result.t2_paths, "#E69F00"),
        ("T3 re-optimised route", result.t3_paths, "#009E73"),
    ]
    for name, paths, colour in layers:
        group = folium.FeatureGroup(name=name, show=True)
        for path in paths:
            coordinates = _path_coordinates(graph, path)
            if len(coordinates) >= 2:
                folium.PolyLine(
                    coordinates,
                    color=colour,
                    weight=5,
                    opacity=0.8,
                    tooltip=name,
                ).add_to(group)
        group.add_to(map_object)
    disruption_group = folium.FeatureGroup(name="Disruptions", show=True)
    for disruption in scenario.disruptions:
        if disruption.geometry:
            coordinates = [(lat, lon) for lon, lat in disruption.geometry]
            if disruption.type in {DisruptionType.POLYGON_CLOSURE, DisruptionType.SLOW_ZONE}:
                folium.Polygon(
                    coordinates,
                    color="#D55E00",
                    fill=True,
                    fill_opacity=0.25,
                    tooltip=f"{disruption.id}: {disruption.type.value}",
                ).add_to(disruption_group)
            else:
                folium.PolyLine(
                    coordinates,
                    color="#D55E00",
                    weight=8,
                    opacity=0.8,
                    tooltip=f"{disruption.id}: {disruption.type.value}",
                ).add_to(disruption_group)
        for u, v, _key in disruption.edge_ids:
            coordinates = _path_coordinates(graph, (u, v))
            folium.PolyLine(coordinates, color="#D55E00", weight=8).add_to(disruption_group)
    disruption_group.add_to(map_object)
    folium.LayerControl(collapsed=False).add_to(map_object)
    return map_object


def save_map(map_object: Any, path: str | Path) -> Path:
    """Write a standalone interactive HTML map."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    map_object.save(str(destination))
    return destination


def _path_coordinates(
    graph: nx.MultiDiGraph, path: tuple[NodeId, ...] | list[NodeId]
) -> list[tuple[float, float]]:
    return [
        (float(graph.nodes[node]["y"]), float(graph.nodes[node]["x"]))
        for node in path
        if node in graph
    ]


def _folium():
    try:
        import folium
    except ImportError as exc:
        raise VisualisationDependencyError(
            "Folium is unavailable; install the project visualisation dependencies"
        ) from exc
    return folium
