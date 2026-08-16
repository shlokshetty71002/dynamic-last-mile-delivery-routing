"""Directed full-cost 2-opt and relocate local search."""

from __future__ import annotations

from dataclasses import dataclass

from dlm.instance.matrix import TravelMatrix
from dlm.instance.schema import DeliveryInstance
from dlm.solver.base import Solution, build_solution, order_cost_s
from dlm.solver.nearest_neighbour import nearest_neighbour_order


def improve_directed_order(
    initial: tuple[str, ...],
    matrix: TravelMatrix,
    *,
    max_iterations: int = 200,
    tolerance_s: float = 1e-9,
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """Improve a route by full directed re-evaluation of 2-opt and relocate moves."""

    best = tuple(initial)
    best_cost = order_cost_s(best, matrix)
    trajectory = [best_cost]
    if len(best) <= 4:
        return best, tuple(trajectory)
    for _ in range(max_iterations):
        candidate_order = best
        candidate_cost = best_cost
        n = len(best) - 1
        for left in range(1, n - 1):
            for right in range(left + 1, n):
                proposed = (*best[:left], *reversed(best[left : right + 1]), *best[right + 1 :])
                cost = order_cost_s(proposed, matrix)
                if (cost, proposed) < (candidate_cost - tolerance_s, candidate_order):
                    candidate_order, candidate_cost = proposed, cost
        for source in range(1, n):
            shortened = list(best)
            moved = shortened.pop(source)
            for target in range(1, n):
                proposed_list = shortened.copy()
                proposed_list.insert(target, moved)
                proposed = tuple(proposed_list)
                cost = order_cost_s(proposed, matrix)
                if (cost, proposed) < (candidate_cost - tolerance_s, candidate_order):
                    candidate_order, candidate_cost = proposed, cost
        if candidate_cost >= best_cost - tolerance_s:
            break
        best, best_cost = candidate_order, candidate_cost
        trajectory.append(best_cost)
    return best, tuple(trajectory)


@dataclass(frozen=True)
class NearestNeighbourTwoOptSolver:
    """Explainable baseline: nearest-neighbour construction plus directed local search."""

    max_iterations: int = 200
    name: str = "nearest-neighbour+directed-2opt"

    def solve(self, instance: DeliveryInstance, matrix: TravelMatrix) -> Solution:
        """Construct and monotonically improve one depot-to-depot route."""

        initial = nearest_neighbour_order(matrix)
        improved, trajectory = improve_directed_order(
            initial, matrix, max_iterations=self.max_iterations
        )
        return build_solution(
            instance,
            matrix,
            [list(improved)],
            solver=self.name,
            meta={
                "initial_driving_time_s": trajectory[0],
                "final_driving_time_s": trajectory[-1],
                "improvement_s": trajectory[0] - trajectory[-1],
                "trajectory_s": list(trajectory),
                "iterations": len(trajectory) - 1,
            },
        )
