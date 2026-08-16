"""Non-mutating graph disruption application with complete audit records."""

from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
from shapely.geometry import LineString, Polygon

from dlm.disruption.schema import Disruption, DisruptionType, EdgeId, Scenario, Severity
from dlm.instance.schema import DeliveryInstance, NodeId


class DisruptionApplicationError(RuntimeError):
    """Raised when a valid scenario cannot be mapped to the selected graph."""


@dataclass(frozen=True)
class DisruptionAudit:
    """Exact graph changes made by a scenario."""

    removed_edges: tuple[EdgeId, ...]
    slowed_edges: tuple[EdgeId, ...]
    removed_nodes: tuple[NodeId, ...]
    total_length_removed_m: float
    active_disruption_ids: tuple[str, ...]

    @property
    def n_edges_removed(self) -> int:
        """Return the number of directed edges removed."""

        return len(self.removed_edges)

    @property
    def n_edges_slowed(self) -> int:
        """Return the number of directed edges whose travel time was multiplied."""

        return len(self.slowed_edges)


@dataclass(frozen=True)
class DisruptedGraph:
    """Modified graph plus immutable provenance and a base-graph reversion handle."""

    base_graph: nx.MultiDiGraph
    graph: nx.MultiDiGraph
    scenario: Scenario
    audit: DisruptionAudit

    def revert(self) -> nx.MultiDiGraph:
        """Return an independent graph equal to the untouched base graph."""

        return self.base_graph.copy()

    def unreachable_stops(self, instance: DeliveryInstance) -> tuple[str, ...]:
        """Return labels no longer reachable to and from the depot."""

        depot = instance.depot.node
        if depot is None or depot not in self.graph:
            return tuple(stop.label for stop in instance.stops)
        unreachable = []
        for stop in instance.stops:
            if (
                stop.node is None
                or stop.node not in self.graph
                or not nx.has_path(self.graph, depot, stop.node)
                or not nx.has_path(self.graph, stop.node, depot)
            ):
                unreachable.append(stop.label)
        return tuple(unreachable)


def apply_scenario(
    base_graph: nx.MultiDiGraph,
    scenario: Scenario,
    *,
    elapsed_s: float = 0.0,
) -> DisruptedGraph:
    """Apply active disruptions to a graph copy, never mutating the cached base graph."""

    graph = base_graph.copy()
    removed_edges: list[EdgeId] = []
    slowed_edges: list[EdgeId] = []
    removed_nodes: list[NodeId] = []
    total_length_removed_m = 0.0
    active_ids: list[str] = []

    for disruption in scenario.disruptions:
        if not disruption.active_at(elapsed_s):
            continue
        active_ids.append(disruption.id)
        if disruption.type is DisruptionType.NODE_CLOSURE:
            for node in disruption.node_ids:
                if node not in graph:
                    continue
                incident = set(graph.in_edges(node, keys=True)) | set(
                    graph.out_edges(node, keys=True)
                )
                for u, v, key in incident:
                    data = graph.get_edge_data(u, v, key) or {}
                    total_length_removed_m += float(data.get("length", 0.0))
                    removed_edges.append((u, v, key))
                graph.remove_node(node)
                removed_nodes.append(node)
            continue

        candidates = _candidate_edges(graph, disruption)
        if not candidates:
            raise DisruptionApplicationError(
                f"Disruption {disruption.id!r} matched no graph edges; check its IDs/geometry"
            )
        partial = disruption.severity is Severity.PARTIAL
        should_slow = disruption.type is DisruptionType.SLOW_ZONE or partial
        for u, v, key in sorted(candidates, key=lambda edge: tuple(map(str, edge))):
            if not graph.has_edge(u, v, key):
                continue
            if should_slow:
                data = graph[u][v][key]
                data["travel_time"] = float(data["travel_time"]) * disruption.factor
                data["disruption_factor"] = float(data.get("disruption_factor", 1.0)) * (
                    disruption.factor
                )
                slowed_edges.append((u, v, key))
            else:
                data = graph[u][v][key]
                total_length_removed_m += float(data.get("length", 0.0))
                graph.remove_edge(u, v, key)
                removed_edges.append((u, v, key))

    return DisruptedGraph(
        base_graph=base_graph,
        graph=graph,
        scenario=scenario,
        audit=DisruptionAudit(
            removed_edges=tuple(removed_edges),
            slowed_edges=tuple(slowed_edges),
            removed_nodes=tuple(removed_nodes),
            total_length_removed_m=total_length_removed_m,
            active_disruption_ids=tuple(active_ids),
        ),
    )


def _candidate_edges(graph: nx.MultiDiGraph, disruption: Disruption) -> set[EdgeId]:
    if disruption.type is DisruptionType.EDGE_CLOSURE:
        return {edge for edge in disruption.edge_ids if graph.has_edge(*edge)}
    if disruption.type is DisruptionType.CORRIDOR_CLOSURE and disruption.street:
        query = disruption.street.casefold()
        matches = {
            (u, v, key)
            for u, v, key, data in graph.edges(keys=True, data=True)
            if query in _edge_names(data.get("name"))
        }
        if matches:
            return matches
    area = _disruption_area(disruption)
    return {
        (u, v, key)
        for u, v, key, data in graph.edges(keys=True, data=True)
        if _edge_line(graph, u, v, data).intersects(area)
    }


def _edge_names(value: object) -> str:
    values = value if isinstance(value, list | tuple | set) else [value]
    return " | ".join(str(item).casefold() for item in values if item is not None)


def _disruption_area(disruption: Disruption):
    if disruption.type is DisruptionType.CORRIDOR_CLOSURE:
        line = LineString(disruption.geometry)
        mean_lat = sum(point[1] for point in disruption.geometry) / len(disruption.geometry)
        degrees = disruption.buffer_m / (111_320.0 * max(math.cos(math.radians(mean_lat)), 0.2))
        return line.buffer(degrees)
    polygon = Polygon(disruption.geometry)
    if not polygon.is_valid or polygon.is_empty:
        raise DisruptionApplicationError(f"Disruption {disruption.id!r} has invalid geometry")
    return polygon


def _edge_line(
    graph: nx.MultiDiGraph,
    u: NodeId,
    v: NodeId,
    data: dict[str, object],
) -> LineString:
    geometry = data.get("geometry")
    if isinstance(geometry, LineString):
        return geometry
    try:
        return LineString(
            [
                (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
                (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
            ]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DisruptionApplicationError(f"Edge {(u, v)!r} lacks usable WGS84 geometry") from exc
