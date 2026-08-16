"""Explainable single- and multi-vehicle solver interfaces."""

from dlm.solver.base import RouteLeg, Solution, Solver, SolverError, VehicleRoute
from dlm.solver.clarke_wright import ClarkeWrightSolver
from dlm.solver.nearest_neighbour import NearestNeighbourSolver
from dlm.solver.ortools_solver import ORToolsSolver
from dlm.solver.two_opt import NearestNeighbourTwoOptSolver


def default_solver(fleet_size: int = 1) -> Solver:
    """Return the project's primary explainable solver for the requested fleet size."""

    return NearestNeighbourTwoOptSolver() if fleet_size == 1 else ClarkeWrightSolver()


__all__ = [
    "ClarkeWrightSolver",
    "NearestNeighbourSolver",
    "NearestNeighbourTwoOptSolver",
    "ORToolsSolver",
    "RouteLeg",
    "Solution",
    "Solver",
    "SolverError",
    "VehicleRoute",
    "default_solver",
]
