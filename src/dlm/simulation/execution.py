"""Edge-by-edge route execution under explicit driver information models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import networkx as nx

from dlm.instance.schema import DeliveryInstance, NodeId
from dlm.solver.base import Solution, VehicleRoute


class InformationModel(StrEnum):
    """What the driver knows about a disruption before reaching it."""

    REACTIVE = "reactive"
    OMNISCIENT = "omniscient"


class ExecutionStatus(StrEnum):
    """Whether all selected stops were served."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    INFEASIBLE = "infeasible"


@dataclass(frozen=True)
class DetectionEvent:
    """First point where a reactive driver encounters a removed planned edge."""

    vehicle_id: int
    current_node: NodeId
    blocked_edge: tuple[NodeId, NodeId, int | str]
    target_id: str
    remaining_stop_ids: tuple[str, ...]
    sunk_time_s: float
    sunk_distance_m: float
    sunk_path: tuple[NodeId, ...]
    served_stop_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionRecord:
    """Auditable execution outcome for frozen route orders."""

    status: ExecutionStatus
    total_time_s: float | None
    driving_time_s: float
    service_time_s: float
    distance_m: float
    detours: int
    stops_served: tuple[str, ...]
    stops_missed: tuple[str, ...]
    route_paths: tuple[tuple[NodeId, ...], ...]
    detections: tuple[DetectionEvent, ...]


def execute_frozen_routes(
    base_graph: nx.MultiDiGraph,
    disrupted_graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    solution: Solution,
    *,
    information_model: InformationModel,
) -> ExecutionRecord:
    """Execute the baseline stop order under disruption without reordering stops."""

    records = [
        _execute_route(base_graph, disrupted_graph, instance, route, information_model)
        for route in solution.routes
    ]
    served = tuple(point for record in records for point in record.stops_served)
    missed = tuple(point for record in records for point in record.stops_missed)
    if not served:
        status = ExecutionStatus.INFEASIBLE
    elif missed:
        status = ExecutionStatus.PARTIAL
    else:
        status = ExecutionStatus.COMPLETE
    total_time_s = None if missed else sum(record.total_time_s or 0.0 for record in records)
    return ExecutionRecord(
        status=status,
        total_time_s=total_time_s,
        driving_time_s=sum(record.driving_time_s for record in records),
        service_time_s=sum(record.service_time_s for record in records),
        distance_m=sum(record.distance_m for record in records),
        detours=sum(record.detours for record in records),
        stops_served=served,
        stops_missed=missed,
        route_paths=tuple(path for record in records for path in record.route_paths),
        detections=tuple(event for record in records for event in record.detections),
    )


def _execute_route(
    base_graph: nx.MultiDiGraph,
    disrupted_graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    route: VehicleRoute,
    information_model: InformationModel,
) -> ExecutionRecord:
    point_by_id = {point.id: point for point in instance.points}
    driving = 0.0
    service = 0.0
    distance = 0.0
    detours = 0
    served: list[str] = []
    missed: list[str] = []
    driven_path: list[NodeId] = []
    detections: list[DetectionEvent] = []

    for leg_index, leg in enumerate(route.legs):
        target = point_by_id[leg.target_id]
        if target.node is None:
            missed.extend(_remaining_ids(route, leg_index))
            break
        try:
            if information_model is InformationModel.OMNISCIENT:
                path = nx.shortest_path(
                    disrupted_graph,
                    leg.path[0],
                    target.node,
                    weight="travel_time",
                )
                leg_time, leg_distance = path_cost(disrupted_graph, path)
                driving += leg_time
                distance += leg_distance
                if tuple(path) != leg.path:
                    detours += 1
                _extend_path(driven_path, path)
            else:
                reached, added_time, added_distance, added_detours, event, path = (
                    _drive_reactive_leg(
                        base_graph,
                        disrupted_graph,
                        route,
                        leg_index,
                        driving + service,
                        distance,
                        tuple(driven_path),
                        tuple(served),
                    )
                )
                driving += added_time
                distance += added_distance
                detours += added_detours
                _extend_path(driven_path, path)
                if event is not None:
                    detections.append(event)
                if not reached:
                    missed.extend(_remaining_ids(route, leg_index))
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            missed.extend(_remaining_ids(route, leg_index))
            break
        if leg.target_id != "depot":
            service += target.service_time_s
            served.append(leg.target_id)

    status = (
        ExecutionStatus.COMPLETE
        if not missed
        else ExecutionStatus.INFEASIBLE
        if not served
        else ExecutionStatus.PARTIAL
    )
    return ExecutionRecord(
        status=status,
        total_time_s=None if missed else driving + service,
        driving_time_s=driving,
        service_time_s=service,
        distance_m=distance,
        detours=detours,
        stops_served=tuple(served),
        stops_missed=tuple(dict.fromkeys(missed)),
        route_paths=(tuple(driven_path),),
        detections=tuple(detections),
    )


def _drive_reactive_leg(
    base_graph: nx.MultiDiGraph,
    disrupted_graph: nx.MultiDiGraph,
    route: VehicleRoute,
    leg_index: int,
    sunk_time_s: float,
    sunk_distance_m: float,
    sunk_path: tuple[NodeId, ...],
    served_ids: tuple[str, ...],
) -> tuple[bool, float, float, int, DetectionEvent | None, tuple[NodeId, ...]]:
    leg = route.legs[leg_index]
    added_time = 0.0
    added_distance = 0.0
    path: list[NodeId] = [leg.path[0]]
    for u, v in zip(leg.path, leg.path[1:], strict=False):
        key, _ = best_edge(base_graph, u, v)
        if disrupted_graph.has_edge(u, v, key):
            data = disrupted_graph[u][v][key]
            added_time += float(data["travel_time"])
            added_distance += float(data.get("length", 0.0))
            path.append(v)
            continue
        remaining = _remaining_ids(route, leg_index)
        event = DetectionEvent(
            vehicle_id=route.vehicle_id,
            current_node=u,
            blocked_edge=(u, v, key),
            target_id=leg.target_id,
            remaining_stop_ids=remaining,
            sunk_time_s=sunk_time_s + added_time,
            sunk_distance_m=sunk_distance_m + added_distance,
            sunk_path=(*sunk_path, *path[1:]) if sunk_path else tuple(path),
            served_stop_ids=served_ids,
        )
        try:
            detour = nx.shortest_path(disrupted_graph, u, leg.path[-1], weight="travel_time")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return False, added_time, added_distance, 0, event, tuple(path)
        detour_time, detour_distance = path_cost(disrupted_graph, detour)
        added_time += detour_time
        added_distance += detour_distance
        _extend_path(path, detour)
        return True, added_time, added_distance, 1, event, tuple(path)
    return True, added_time, added_distance, 0, None, tuple(path)


def best_edge(graph: nx.MultiDiGraph, u: NodeId, v: NodeId) -> tuple[int | str, dict[str, object]]:
    """Return the deterministic minimum-travel-time parallel edge."""

    edges = graph.get_edge_data(u, v)
    if not edges:
        raise nx.NetworkXNoPath(f"Missing directed edge {u!r}->{v!r}")
    key = min(
        edges,
        key=lambda candidate: (
            float(edges[candidate].get("travel_time", math.inf)),
            str(candidate),
        ),
    )
    return key, edges[key]


def path_cost(
    graph: nx.MultiDiGraph, path: list[NodeId] | tuple[NodeId, ...]
) -> tuple[float, float]:
    """Return travel time in seconds and length in metres for one node path."""

    travel_time = 0.0
    distance = 0.0
    for u, v in zip(path, path[1:], strict=False):
        _, data = best_edge(graph, u, v)
        travel_time += float(data["travel_time"])
        distance += float(data.get("length", 0.0))
    return travel_time, distance


def _remaining_ids(route: VehicleRoute, leg_index: int) -> tuple[str, ...]:
    return tuple(point for point in route.order[leg_index + 1 : -1] if point != "depot")


def _extend_path(target: list[NodeId], addition: list[NodeId] | tuple[NodeId, ...]) -> None:
    target.extend(addition if not target else addition[1:])
