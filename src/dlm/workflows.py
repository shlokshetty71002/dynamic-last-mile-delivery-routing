"""Application-layer workflows shared verbatim by the CLI and Streamlit client."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from dlm.disruption.schema import Scenario
from dlm.instance.matrix import build_matrix, points_from_instance
from dlm.instance.schema import DeliveryInstance
from dlm.network.snapping import snap_to_node
from dlm.simulation import Experiment, ExperimentResult, InformationModel
from dlm.simulation.metrics import SustainabilityAssumptions
from dlm.solver import Solution, default_solver


def plan_delivery(
    graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    *,
    matrix_cache_dir: str | Path | None = None,
) -> Solution:
    """Build the point matrix and solve a baseline delivery run."""

    instance = resolve_instance(graph, instance)
    matrix = build_matrix(
        graph,
        points_from_instance(instance),
        cache_dir=matrix_cache_dir,
    )
    return default_solver(instance.fleet_size).solve(instance, matrix)


def compare_delivery(
    graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    scenario: Scenario,
    *,
    information_model: InformationModel = InformationModel.REACTIVE,
    matrix_cache_dir: str | Path | None = None,
) -> ExperimentResult:
    """Run the canonical T1/T2/T3 comparison used by every interface."""

    instance = resolve_instance(graph, instance)
    return Experiment(
        graph,
        instance,
        scenario,
        information_model=information_model,
        matrix_cache_dir=matrix_cache_dir,
    ).run()


def comparison_configuration(
    graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    scenario: Scenario,
    result: ExperimentResult,
    *,
    information_model: InformationModel = InformationModel.REACTIVE,
) -> dict[str, object]:
    """Return the complete deterministic configuration needed to replay a comparison."""

    resolved = resolve_instance(graph, instance)
    return {
        "graph": {
            "area_name": graph.graph.get("dlm_area_name"),
            "cache_key": graph.graph.get("dlm_cache_key"),
            "network_type": graph.graph.get("dlm_network_type"),
            "osmnx_version": graph.graph.get("dlm_osmnx_version"),
        },
        "information_model": information_model.value,
        "instance": resolved.model_dump(mode="json"),
        "scenario": scenario.model_dump(mode="json"),
        "solver": result.solver,
        "sustainability": SustainabilityAssumptions().model_dump(mode="json"),
    }


def resolve_instance(
    graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    *,
    max_snap_distance_m: float = 500.0,
) -> DeliveryInstance:
    """Snap coordinate-only committed instances without altering their saved source files."""

    if all(point.node is not None for point in instance.points):
        return instance
    depot = instance.depot
    if depot.node is None:
        depot = depot.model_copy(
            update={
                "node": snap_to_node(
                    graph,
                    depot.lat,
                    depot.lon,
                    max_distance_m=max_snap_distance_m,
                ).node
            }
        )
    stops = []
    for stop in instance.stops:
        if stop.node is None:
            stop = stop.model_copy(
                update={
                    "node": snap_to_node(
                        graph,
                        stop.lat,
                        stop.lon,
                        max_distance_m=max_snap_distance_m,
                    ).node
                }
            )
        stops.append(stop)
    return DeliveryInstance(
        name=instance.name,
        depot=depot,
        stops=tuple(stops),
        fleet_size=instance.fleet_size,
        vehicle_capacity=instance.vehicle_capacity,
        seed=instance.seed,
        created_at=instance.created_at,
    )
