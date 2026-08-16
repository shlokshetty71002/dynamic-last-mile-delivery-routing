"""Tests for single-vehicle local search and capacity-safe fleet routing."""

from __future__ import annotations

import importlib.util
import itertools

import networkx as nx
import pytest

from dlm.instance.matrix import build_matrix, points_from_instance
from dlm.instance.schema import DeliveryInstance
from dlm.solver import (
    ClarkeWrightSolver,
    NearestNeighbourTwoOptSolver,
    ORToolsSolver,
)
from dlm.solver.base import order_cost_s


def test_nn_two_opt_covers_every_stop_and_is_monotone(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    matrix = build_matrix(road_graph, points_from_instance(delivery_instance))
    solution = NearestNeighbourTwoOptSolver().solve(delivery_instance, matrix)
    assert set(solution.order[1:-1]) == {stop.id for stop in delivery_instance.stops}
    assert solution.order[0] == solution.order[-1] == "depot"
    trajectory = solution.meta["trajectory_s"]
    assert all(left >= right for left, right in zip(trajectory, trajectory[1:], strict=False))
    assert solution.total_time_s == solution.total_driving_time_s + 120.0


def test_heuristic_finds_fixture_optimum(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    matrix = build_matrix(road_graph, points_from_instance(delivery_instance))
    solution = NearestNeighbourTwoOptSolver().solve(delivery_instance, matrix)
    optimum = min(
        order_cost_s(("depot", *permutation, "depot"), matrix)
        for permutation in itertools.permutations(stop.id for stop in delivery_instance.stops)
    )
    assert solution.total_driving_time_s == optimum


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_single_vehicle_handles_degenerate_dynamic_sizes(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance, n: int
) -> None:
    instance = DeliveryInstance(
        name=f"n-{n}",
        depot=delivery_instance.depot,
        stops=delivery_instance.stops[:n],
        fleet_size=1,
        vehicle_capacity=delivery_instance.vehicle_capacity,
        seed=42,
        created_at=delivery_instance.created_at,
    )
    matrix = build_matrix(road_graph, points_from_instance(instance))
    solution = NearestNeighbourTwoOptSolver().solve(instance, matrix)
    assert len(solution.order) == n + 2


def test_clarke_wright_respects_fleet_and_capacity(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    instance = DeliveryInstance(
        name="fleet-two",
        depot=delivery_instance.depot,
        stops=delivery_instance.stops,
        fleet_size=2,
        vehicle_capacity=3.0,
        seed=42,
        created_at=delivery_instance.created_at,
    )
    matrix = build_matrix(road_graph, points_from_instance(instance))
    solution = ClarkeWrightSolver().solve(instance, matrix)
    assert len(solution.routes) == 2
    assert all(route.load <= 3.0 for route in solution.routes)
    served = [point for route in solution.routes for point in route.order[1:-1]]
    assert sorted(served) == sorted(stop.id for stop in instance.stops)


def test_k_one_clarke_wright_is_baseline_regression(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    matrix = build_matrix(road_graph, points_from_instance(delivery_instance))
    baseline = NearestNeighbourTwoOptSolver().solve(delivery_instance, matrix)
    fleet_adapter = ClarkeWrightSolver().solve(delivery_instance, matrix)
    assert fleet_adapter.order == baseline.order
    assert fleet_adapter.total_time_s == baseline.total_time_s


@pytest.mark.skipif(importlib.util.find_spec("ortools") is None, reason="optional benchmark")
def test_ortools_is_no_worse_than_primary_heuristic(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    matrix = build_matrix(road_graph, points_from_instance(delivery_instance))
    heuristic = NearestNeighbourTwoOptSolver().solve(delivery_instance, matrix)
    oracle = ORToolsSolver(time_limit_s=2).solve(delivery_instance, matrix)
    assert oracle.total_driving_time_s <= heuristic.total_driving_time_s
