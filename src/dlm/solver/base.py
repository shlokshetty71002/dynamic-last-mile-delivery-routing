"""Shared route, solution, and solver contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from dlm.instance.matrix import TravelMatrix
from dlm.instance.schema import DeliveryInstance, NodeId


class SolverError(RuntimeError):
    """Raised when a routing problem is infeasible or a solver fails."""


@dataclass(frozen=True)
class RouteLeg:
    """One route leg, with shortest-path travel time and distance."""

    source_id: str
    target_id: str
    travel_time_s: float
    distance_m: float
    path: tuple[NodeId, ...]


@dataclass(frozen=True)
class VehicleRoute:
    """One depot-to-depot vehicle route."""

    vehicle_id: int
    order: tuple[str, ...]
    legs: tuple[RouteLeg, ...]
    driving_time_s: float
    service_time_s: float
    distance_m: float
    load: float

    @property
    def total_time_s(self) -> float:
        """Return driving plus service time in seconds."""

        return self.driving_time_s + self.service_time_s

    @property
    def path_nodes(self) -> tuple[NodeId, ...]:
        """Return the continuous expanded road-node path for mapping."""

        expanded: list[NodeId] = []
        for leg in self.legs:
            expanded.extend(leg.path if not expanded else leg.path[1:])
        return tuple(expanded)


@dataclass(frozen=True)
class Solution:
    """Complete single- or multi-vehicle solution using one consistent interface."""

    routes: tuple[VehicleRoute, ...]
    solver: str
    total_time_s: float
    total_driving_time_s: float
    total_service_time_s: float
    total_distance_m: float
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def order(self) -> tuple[str, ...]:
        """Return the sole route order for single-vehicle solutions."""

        if len(self.routes) != 1:
            raise SolverError("order is only defined for a single-vehicle solution")
        return self.routes[0].order


class Solver(Protocol):
    """Protocol implemented by all routing algorithms in the project."""

    name: str

    def solve(self, instance: DeliveryInstance, matrix: TravelMatrix) -> Solution:
        """Solve one validated delivery instance against a matching matrix."""


def order_cost_s(order: tuple[str, ...] | list[str], matrix: TravelMatrix) -> float:
    """Return driving time in seconds for an explicit point-ID order."""

    return sum(
        matrix.cost(source, target) for source, target in zip(order, order[1:], strict=False)
    )


def build_solution(
    instance: DeliveryInstance,
    matrix: TravelMatrix,
    orders: list[list[str]] | tuple[tuple[str, ...], ...],
    *,
    solver: str,
    meta: dict[str, Any] | None = None,
) -> Solution:
    """Validate route coverage and calculate all auditable solution totals."""

    expected = {stop.id for stop in instance.stops}
    served: list[str] = []
    by_id = {point.id: point for point in instance.points}
    routes: list[VehicleRoute] = []
    for vehicle_id, raw_order in enumerate(orders, start=1):
        order = tuple(raw_order)
        if len(order) < 3 or order[0] != "depot" or order[-1] != "depot":
            raise SolverError("Every vehicle route must start and end at depot")
        route_stops = [point_id for point_id in order[1:-1] if point_id != "depot"]
        served.extend(route_stops)
        legs = tuple(
            RouteLeg(
                source_id=source,
                target_id=target,
                travel_time_s=matrix.cost(source, target),
                distance_m=float(matrix.distance_m[matrix.index(source), matrix.index(target)]),
                path=matrix.path(source, target),
            )
            for source, target in zip(order, order[1:], strict=False)
        )
        driving_time_s = sum(leg.travel_time_s for leg in legs)
        service_time_s = sum(by_id[point_id].service_time_s for point_id in route_stops)
        load = sum(by_id[point_id].demand for point_id in route_stops)
        if instance.vehicle_capacity is not None and load > instance.vehicle_capacity + 1e-9:
            raise SolverError(
                f"Vehicle {vehicle_id} load {load:g} exceeds capacity {instance.vehicle_capacity:g}"
            )
        routes.append(
            VehicleRoute(
                vehicle_id=vehicle_id,
                order=order,
                legs=legs,
                driving_time_s=driving_time_s,
                service_time_s=service_time_s,
                distance_m=sum(leg.distance_m for leg in legs),
                load=load,
            )
        )
    if set(served) != expected or len(served) != len(expected):
        raise SolverError("Routes must serve every stop exactly once")
    return Solution(
        routes=tuple(routes),
        solver=solver,
        total_time_s=sum(route.total_time_s for route in routes),
        total_driving_time_s=sum(route.driving_time_s for route in routes),
        total_service_time_s=sum(route.service_time_s for route in routes),
        total_distance_m=sum(route.distance_m for route in routes),
        meta=meta or {},
    )
