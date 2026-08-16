"""Capacity-safe directed Clarke-Wright-style fleet construction."""

from __future__ import annotations

from dataclasses import dataclass

from dlm.instance.matrix import TravelMatrix
from dlm.instance.schema import DeliveryInstance
from dlm.solver.base import Solution, SolverError, build_solution, order_cost_s
from dlm.solver.two_opt import NearestNeighbourTwoOptSolver, improve_directed_order


@dataclass(frozen=True)
class ClarkeWrightSolver:
    """Merge singleton routes by maximum directed saving until fleet size is met."""

    improve_routes: bool = True
    name: str = "directed-clarke-wright"

    def solve(self, instance: DeliveryInstance, matrix: TravelMatrix) -> Solution:
        """Build at most ``fleet_size`` capacity-feasible depot routes."""

        if instance.fleet_size == 1:
            return NearestNeighbourTwoOptSolver().solve(instance, matrix)
        capacity = instance.vehicle_capacity
        demand = {stop.id: stop.demand for stop in instance.stops}
        routes: list[list[str]] = [[stop.id] for stop in instance.stops]
        target = min(instance.fleet_size, instance.n_stops)
        while len(routes) > target:
            best: tuple[float, tuple[str, ...], int, int] | None = None
            for first_index in range(len(routes)):
                for second_index in range(first_index + 1, len(routes)):
                    first = routes[first_index]
                    second = routes[second_index]
                    load = sum(demand[point] for point in (*first, *second))
                    if capacity is not None and load > capacity + 1e-9:
                        continue
                    separate = _inner_cost(first, matrix) + _inner_cost(second, matrix)
                    variants = (
                        (*first, *second),
                        (*first, *reversed(second)),
                        (*reversed(first), *second),
                        (*reversed(first), *reversed(second)),
                        (*second, *first),
                        (*second, *reversed(first)),
                        (*reversed(second), *first),
                        (*reversed(second), *reversed(first)),
                    )
                    merged = min(variants, key=lambda route: (_inner_cost(route, matrix), route))
                    saving = separate - _inner_cost(merged, matrix)
                    candidate = (saving, tuple(merged), first_index, second_index)
                    if best is None or candidate[:2] > best[:2]:
                        best = candidate
            if best is None:
                raise SolverError(
                    "Fleet/capacity combination is infeasible; increase vehicles or capacity"
                )
            _, merged, first_index, second_index = best
            routes[first_index] = list(merged)
            routes.pop(second_index)

        orders: list[list[str]] = []
        trajectories: list[list[float]] = []
        for route in routes:
            order = ("depot", *route, "depot")
            if self.improve_routes:
                order, trajectory = improve_directed_order(order, matrix)
            else:
                trajectory = (order_cost_s(order, matrix),)
            orders.append(list(order))
            trajectories.append(list(trajectory))
        return build_solution(
            instance,
            matrix,
            orders,
            solver=self.name,
            meta={
                "vehicles_used": len(orders),
                "fleet_size": instance.fleet_size,
                "route_trajectories_s": trajectories,
            },
        )


def _inner_cost(route: tuple[str, ...] | list[str], matrix: TravelMatrix) -> float:
    order = ("depot", *route, "depot")
    return order_cost_s(order, matrix)
