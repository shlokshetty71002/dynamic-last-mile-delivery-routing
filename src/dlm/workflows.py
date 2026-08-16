"""Application-layer workflows shared verbatim by the CLI and Streamlit client."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path

import networkx as nx

from dlm.disruption.engine import apply_scenario
from dlm.disruption.schema import Disruption, DisruptionType, EdgeId, Scenario
from dlm.instance.matrix import build_matrix, points_from_instance
from dlm.instance.schema import DeliveryInstance
from dlm.network.snapping import snap_to_node
from dlm.simulation import ExecutionStatus, Experiment, ExperimentResult, InformationModel
from dlm.simulation.execution import best_edge
from dlm.simulation.metrics import SustainabilityAssumptions
from dlm.solver import Solution, default_solver


class DemoScenarioNotFoundError(RuntimeError):
    """Raised when bounded honest search finds no complete positive-saving demonstration."""


@dataclass(frozen=True)
class DemoSelection:
    """A selection-conditioned scenario, its complete result, and search telemetry."""

    scenario: Scenario
    result: ExperimentResult
    candidates_evaluated: int


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


def find_feasible_saving_demo(
    graph: nx.MultiDiGraph,
    instance: DeliveryInstance,
    *,
    minimum_saving_percent: float = 0.01,
    target_saving_percent: float = 1.0,
    max_route_edges: int = 12,
    max_candidates: int = 80,
    matrix_cache_dir: str | Path | None = None,
) -> DemoSelection:
    """Find a route-impacting closure that stays feasible and gives a positive T3 saving.

    This is a deterministic demonstration selector, not an unbiased experiment sampler. It tests
    one- and two-edge closures drawn only from the baseline route, rejects candidates that make
    any selected stop unreachable from the depot, and accepts only complete finite comparisons
    with ``T3 < T2``. The core experiment semantics remain unchanged.
    """

    if minimum_saving_percent <= 0:
        raise ValueError("minimum_saving_percent must be positive")
    if target_saving_percent < minimum_saving_percent:
        raise ValueError("target_saving_percent cannot be below the minimum")
    if max_route_edges < 2:
        raise ValueError("max_route_edges must be at least 2")
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")

    resolved = resolve_instance(graph, instance)
    baseline = plan_delivery(graph, resolved, matrix_cache_dir=matrix_cache_dir)
    route_edges = _candidate_route_edges(graph, baseline, max_route_edges=max_route_edges)
    if len(route_edges) < 2:
        raise DemoScenarioNotFoundError(
            "The baseline route contains too few distinct edges for a saving demonstration."
        )

    edge_groups = [(edge,) for edge in route_edges]
    edge_groups.extend(combinations(route_edges, 2))
    best: DemoSelection | None = None
    evaluated = 0
    for group in edge_groups:
        if evaluated >= max_candidates:
            break
        scenario = _demo_scenario(tuple(group))
        disrupted = apply_scenario(graph, scenario)
        if disrupted.unreachable_stops(resolved):
            continue
        evaluated += 1
        result = compare_delivery(
            graph,
            resolved,
            scenario,
            information_model=InformationModel.REACTIVE,
            matrix_cache_dir=matrix_cache_dir,
        )
        saving = result.saving_percent
        if (
            result.status is not ExecutionStatus.COMPLETE
            or result.t2_s is None
            or result.t3_s is None
            or not math.isfinite(result.t2_s)
            or not math.isfinite(result.t3_s)
            or saving is None
            or not math.isfinite(saving)
            or saving < minimum_saving_percent
        ):
            continue
        selection = DemoSelection(
            scenario=scenario,
            result=result,
            candidates_evaluated=evaluated,
        )
        if best is None or saving > (best.result.saving_percent or 0.0):
            best = selection
        if saving >= target_saving_percent:
            return selection

    if best is not None:
        return best
    raise DemoScenarioNotFoundError(
        "No complete positive-saving candidate was found within the bounded search. "
        "Try at least four geographically dispersed stops or a different instance."
    )


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


def _candidate_route_edges(
    graph: nx.MultiDiGraph,
    solution: Solution,
    *,
    max_route_edges: int,
) -> list[EdgeId]:
    """Return evenly distributed first/mid-leg baseline edges in deterministic order."""

    first_edges: list[EdgeId] = []
    middle_edges: list[EdgeId] = []
    for route in solution.routes:
        for leg in route.legs:
            if len(leg.path) < 2:
                continue
            indices = (0, (len(leg.path) - 2) // 2)
            for target, index in ((first_edges, indices[0]), (middle_edges, indices[1])):
                u, v = leg.path[index : index + 2]
                key, _ = best_edge(graph, u, v)
                edge = (u, v, key)
                if edge not in target:
                    target.append(edge)
    primary = _evenly_spaced(first_edges, max_route_edges)
    if len(primary) >= max_route_edges:
        return primary
    extras = [edge for edge in middle_edges if edge not in primary]
    return [*primary, *_evenly_spaced(extras, max_route_edges - len(primary))]


def _evenly_spaced(values: list[EdgeId], limit: int) -> list[EdgeId]:
    if len(values) <= limit:
        return list(values)
    if limit == 1:
        return [values[len(values) // 2]]
    indices = [round(index * (len(values) - 1) / (limit - 1)) for index in range(limit)]
    return [values[index] for index in dict.fromkeys(indices)]


def _demo_scenario(edges: tuple[EdgeId, ...]) -> Scenario:
    encoded = json.dumps(edges, default=str, separators=(",", ":")).encode()
    suffix = hashlib.sha256(encoded).hexdigest()[:8]
    return Scenario(
        name=f"feasible_saving_demo_{suffix}",
        description=(
            "Feasible route-impacting demonstration selected deterministically from the "
            "current baseline route."
        ),
        source=(
            "Synthetic selection-conditioned demonstration: candidate baseline-route closures "
            "were searched for reachability and positive T3 saving. This is not an unbiased "
            "estimate and must not be included in random-scenario inference."
        ),
        created=date.today(),
        disruptions=(
            Disruption(
                id="selected-route-edges",
                type=DisruptionType.EDGE_CLOSURE,
                edge_ids=edges,
            ),
        ),
    )
