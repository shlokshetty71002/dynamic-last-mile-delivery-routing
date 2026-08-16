"""Optional OR-Tools benchmark adapter using the shared travel matrix."""

from __future__ import annotations

from dataclasses import dataclass

from dlm.instance.matrix import TravelMatrix
from dlm.instance.schema import DeliveryInstance
from dlm.solver.base import Solution, SolverError, build_solution


@dataclass(frozen=True)
class ORToolsSolver:
    """Benchmark routing solver; the hand-written heuristic remains the primary method."""

    time_limit_s: int = 10
    name: str = "ortools-guided-local-search"

    def solve(self, instance: DeliveryInstance, matrix: TravelMatrix) -> Solution:
        """Solve TSP/CVRP using OR-Tools and return the common solution model."""

        try:
            from ortools.constraint_solver import pywrapcp, routing_enums_pb2
        except ImportError as exc:
            raise SolverError(
                "OR-Tools benchmark is unavailable; install the project benchmark dependencies"
            ) from exc

        manager = pywrapcp.RoutingIndexManager(matrix.size, instance.fleet_size, 0)
        routing = pywrapcp.RoutingModel(manager)

        def transit(from_index: int, to_index: int) -> int:
            source = manager.IndexToNode(from_index)
            target = manager.IndexToNode(to_index)
            return int(round(float(matrix.time_s[source, target]) * 1000))

        transit_index = routing.RegisterTransitCallback(transit)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

        if instance.vehicle_capacity is not None:
            demand_by_index = [0.0, *(stop.demand for stop in instance.stops)]
            scale = 1000

            def demand(index: int) -> int:
                return int(round(demand_by_index[manager.IndexToNode(index)] * scale))

            demand_index = routing.RegisterUnaryTransitCallback(demand)
            capacity = int(round(instance.vehicle_capacity * scale))
            routing.AddDimensionWithVehicleCapacity(
                demand_index,
                0,
                [capacity] * instance.fleet_size,
                True,
                "Capacity",
            )

        parameters = pywrapcp.DefaultRoutingSearchParameters()
        parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        parameters.time_limit.seconds = self.time_limit_s
        parameters.log_search = False
        assignment = routing.SolveWithParameters(parameters)
        if assignment is None:
            raise SolverError("OR-Tools could not find a feasible routing solution")

        orders: list[list[str]] = []
        for vehicle in range(instance.fleet_size):
            index = routing.Start(vehicle)
            order = ["depot"]
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                if node_index != 0:
                    order.append(matrix.points[node_index].id)
                index = assignment.Value(routing.NextVar(index))
            order.append("depot")
            if len(order) > 2:
                orders.append(order)
        return build_solution(
            instance,
            matrix,
            orders,
            solver=self.name,
            meta={"time_limit_s": self.time_limit_s, "vehicles_used": len(orders)},
        )
