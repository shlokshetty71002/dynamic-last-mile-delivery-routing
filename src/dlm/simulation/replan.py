"""Re-optimisation from the driver's actual node at first disruption discovery."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from dlm.instance.matrix import MatrixBuildError, PointRef, build_matrix
from dlm.instance.schema import DeliveryInstance, NodeId, Stop
from dlm.simulation.execution import (
    ExecutionRecord,
    ExecutionStatus,
    InformationModel,
    _execute_route,
)
from dlm.solver.base import Solution, VehicleRoute, order_cost_s
from dlm.solver.two_opt import improve_directed_order


@dataclass(frozen=True)
class ReplanRecord:
    """Execution outcome after at most one re-optimisation per affected vehicle."""

    status: ExecutionStatus
    total_time_s: float | None
    driving_time_s: float
    service_time_s: float
    distance_m: float
    route_paths: tuple[tuple[NodeId, ...], ...]
    stops_served: tuple[str, ...]
    stops_missed: tuple[str, ...]
    replans: int
    fallback_used: bool
    candidate_time_s: float | None


def replan_at_first_discovery(
    base_graph: nx.MultiDiGraph,
    disrupted_graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    baseline: Solution,
) -> ReplanRecord:
    """Reorder each affected vehicle's remaining stops from its discovery node."""

    totals: list[ExecutionRecord | ReplanRecord] = []
    candidate_times: list[float] = []
    fallback_used = False
    replans = 0
    for route in baseline.routes:
        frozen = _execute_route(
            base_graph,
            disrupted_graph,
            instance,
            route,
            InformationModel.REACTIVE,
        )
        if not frozen.detections:
            totals.append(frozen)
            continue
        replans += 1
        candidate = _replan_vehicle(disrupted_graph, instance, route, frozen)
        if candidate.total_time_s is not None:
            candidate_times.append(candidate.total_time_s)
        if (
            frozen.total_time_s is not None
            and candidate.total_time_s is not None
            and candidate.total_time_s > frozen.total_time_s + 1e-9
        ):
            totals.append(frozen)
            fallback_used = True
        elif candidate.total_time_s is None and frozen.total_time_s is not None:
            totals.append(frozen)
            fallback_used = True
        else:
            totals.append(candidate)

    served = tuple(point for record in totals for point in record.stops_served)
    missed = tuple(point for record in totals for point in record.stops_missed)
    status = (
        ExecutionStatus.COMPLETE
        if not missed
        else ExecutionStatus.INFEASIBLE
        if not served
        else ExecutionStatus.PARTIAL
    )
    return ReplanRecord(
        status=status,
        total_time_s=None if missed else sum(record.total_time_s or 0.0 for record in totals),
        driving_time_s=sum(record.driving_time_s for record in totals),
        service_time_s=sum(record.service_time_s for record in totals),
        distance_m=sum(record.distance_m for record in totals),
        route_paths=tuple(path for record in totals for path in record.route_paths),
        stops_served=served,
        stops_missed=missed,
        replans=replans,
        fallback_used=fallback_used,
        candidate_time_s=sum(candidate_times) if candidate_times else None,
    )


def _replan_vehicle(
    graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    route: VehicleRoute,
    frozen: ExecutionRecord,
) -> ReplanRecord:
    event = frozen.detections[0]
    by_id = {point.id: point for point in instance.points}
    home_node = instance.depot.node
    assert home_node is not None
    remaining = [point_id for point_id in event.remaining_stop_ids if point_id != "depot"]
    points = [PointRef("start", event.current_node)]
    for point_id in remaining:
        node = by_id[point_id].node
        if node is None:
            return _failed_replan(event, remaining, by_id)
        points.append(PointRef(point_id, node))
    same_as_home = event.current_node == home_node
    if not same_as_home:
        points.append(PointRef("home", home_node))
    try:
        matrix = build_matrix(graph, points)
    except MatrixBuildError:
        return _failed_replan(event, remaining, by_id)

    unvisited = set(remaining)
    current = "start"
    order = [current]
    while unvisited:
        next_id = min(unvisited, key=lambda point_id: (matrix.cost(current, point_id), point_id))
        order.append(next_id)
        unvisited.remove(next_id)
        current = next_id
    order.append("start" if same_as_home else "home")
    improved, _ = improve_directed_order(tuple(order), matrix)
    remaining_driving = order_cost_s(improved, matrix)
    remaining_service = sum(by_id[point_id].service_time_s for point_id in remaining)
    remaining_distance = sum(
        float(matrix.distance_m[matrix.index(source), matrix.index(target)])
        for source, target in zip(improved, improved[1:], strict=False)
    )
    replanned_path: list[NodeId] = []
    for source, target in zip(improved, improved[1:], strict=False):
        segment = matrix.path(source, target)
        replanned_path.extend(segment if not replanned_path else segment[1:])
    sunk_service = sum(by_id[point_id].service_time_s for point_id in event.served_stop_ids)
    sunk_driving = event.sunk_time_s - sunk_service
    full_path = list(event.sunk_path)
    full_path.extend(replanned_path if not full_path else replanned_path[1:])
    all_stops = tuple((*event.served_stop_ids, *remaining))
    total_time = event.sunk_time_s + remaining_driving + remaining_service
    return ReplanRecord(
        status=ExecutionStatus.COMPLETE,
        total_time_s=total_time,
        driving_time_s=sunk_driving + remaining_driving,
        service_time_s=sunk_service + remaining_service,
        distance_m=event.sunk_distance_m + remaining_distance,
        route_paths=(tuple(full_path),),
        stops_served=all_stops,
        stops_missed=(),
        replans=1,
        fallback_used=False,
        candidate_time_s=total_time,
    )


def _failed_replan(event, remaining: list[str], by_id: dict[str, Stop]) -> ReplanRecord:
    sunk_service = sum(by_id[point_id].service_time_s for point_id in event.served_stop_ids)
    return ReplanRecord(
        status=ExecutionStatus.PARTIAL if event.served_stop_ids else ExecutionStatus.INFEASIBLE,
        total_time_s=None,
        driving_time_s=event.sunk_time_s - sunk_service,
        service_time_s=sunk_service,
        distance_m=event.sunk_distance_m,
        route_paths=(event.sunk_path,),
        stops_served=event.served_stop_ids,
        stops_missed=tuple(remaining),
        replans=1,
        fallback_used=False,
        candidate_time_s=None,
    )
