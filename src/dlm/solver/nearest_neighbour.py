"""Deterministic, asymmetry-aware nearest-neighbour route construction."""

from __future__ import annotations

from dataclasses import dataclass

from dlm.instance.matrix import TravelMatrix
from dlm.instance.schema import DeliveryInstance
from dlm.solver.base import Solution, build_solution


def nearest_neighbour_order(matrix: TravelMatrix) -> tuple[str, ...]:
    """Construct one depot-to-depot order using outgoing directed travel time."""

    remaining = set(matrix.ids) - {"depot"}
    current = "depot"
    order = [current]
    while remaining:
        next_id = min(remaining, key=lambda point_id: (matrix.cost(current, point_id), point_id))
        order.append(next_id)
        remaining.remove(next_id)
        current = next_id
    order.append("depot")
    return tuple(order)


@dataclass(frozen=True)
class NearestNeighbourSolver:
    """Single-vehicle directed nearest-neighbour solver."""

    name: str = "nearest-neighbour"

    def solve(self, instance: DeliveryInstance, matrix: TravelMatrix) -> Solution:
        """Build a deterministic nearest-neighbour route for all dynamic stops."""

        return build_solution(
            instance,
            matrix,
            [list(nearest_neighbour_order(matrix))],
            solver=self.name,
            meta={"construction": "directed nearest neighbour"},
        )
