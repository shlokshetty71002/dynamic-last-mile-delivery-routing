"""Reproducible T1/T2/T3 experiment orchestration and sustainability metrics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import networkx as nx
import yaml
from pydantic import BaseModel, ConfigDict, Field

from dlm.disruption.engine import DisruptedGraph, apply_scenario
from dlm.disruption.schema import Scenario
from dlm.instance.matrix import MatrixBuildError, build_matrix, points_from_instance
from dlm.instance.schema import DeliveryInstance, NodeId
from dlm.simulation.execution import (
    ExecutionRecord,
    ExecutionStatus,
    InformationModel,
    execute_frozen_routes,
)
from dlm.simulation.replan import replan_at_first_discovery
from dlm.solver import Solver, default_solver
from dlm.solver.base import Solution, SolverError

RESULT_SCHEMA_VERSION = 1


class EnvironmentalMetrics(BaseModel):
    """Distance-based diesel use, carbon emissions, and configured fuel cost."""

    model_config = ConfigDict(frozen=True)

    distance_km: float
    fuel_l: float
    co2_kg: float
    fuel_cost_eur: float


class SustainabilityAssumptions(BaseModel):
    """Transparent configurable factors used for fuel and CO₂ estimates."""

    model_config = ConfigDict(frozen=True)

    diesel_l_per_100km: float = Field(default=8.5, gt=0)
    diesel_co2_kg_per_l: float = Field(default=2.68, gt=0)
    fuel_price_eur_per_l: float = Field(default=1.75, gt=0)

    def calculate(self, distance_m: float) -> EnvironmentalMetrics:
        """Estimate operational fuel and tailpipe CO₂ from routed distance."""

        distance_km = distance_m / 1000.0
        fuel_l = distance_km * self.diesel_l_per_100km / 100.0
        return EnvironmentalMetrics(
            distance_km=round(distance_km, 6),
            fuel_l=round(fuel_l, 6),
            co2_kg=round(fuel_l * self.diesel_co2_kg_per_l, 6),
            fuel_cost_eur=round(fuel_l * self.fuel_price_eur_per_l, 6),
        )


class ExperimentResult(BaseModel):
    """Fully serialisable three-case comparison record."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = RESULT_SCHEMA_VERSION
    run_id: str
    instance_name: str
    instance_hash: str
    scenario_name: str
    solver: str
    information_model: InformationModel
    status: ExecutionStatus
    n_stops: int
    fleet_size: int
    t1_s: float
    t2_s: float | None
    t3_s: float | None
    t3_oracle_s: float | None
    saving_percent: float | None
    oracle_saving_percent: float | None
    t1_environment: EnvironmentalMetrics
    t2_environment: EnvironmentalMetrics
    t3_environment: EnvironmentalMetrics
    t3_oracle_environment: EnvironmentalMetrics | None
    detours: int
    replans: int
    fallback_used: bool
    stops_served: int
    stops_missed: tuple[str, ...]
    n_edges_removed: int
    n_edges_slowed: int
    removed_length_m: float
    baseline_orders: tuple[tuple[str, ...], ...]
    t1_paths: tuple[tuple[NodeId, ...], ...]
    t2_paths: tuple[tuple[NodeId, ...], ...]
    t3_paths: tuple[tuple[NodeId, ...], ...]
    oracle_orders: tuple[tuple[str, ...], ...]

    def summary_row(self) -> dict[str, object]:
        """Return one tidy batch-results row without large route paths."""

        excluded = {"t1_paths", "t2_paths", "t3_paths", "baseline_orders", "oracle_orders"}
        payload = self.model_dump(mode="json", exclude=excluded)
        for prefix in ("t1", "t2", "t3", "t3_oracle"):
            environment = payload.pop(f"{prefix}_environment", None)
            if environment:
                payload.update({f"{prefix}_{key}": value for key, value in environment.items()})
        return payload


class Experiment:
    """Run the baseline, frozen-disruption, reactive replan, and oracle cases."""

    def __init__(
        self,
        graph: nx.MultiDiGraph,
        instance: DeliveryInstance,
        scenario: Scenario,
        *,
        solver: Solver | None = None,
        information_model: InformationModel = InformationModel.REACTIVE,
        sustainability: SustainabilityAssumptions | None = None,
        matrix_cache_dir: str | Path | None = None,
    ) -> None:
        self.graph = graph
        self.instance = instance
        self.scenario = scenario
        self.solver = solver or default_solver(instance.fleet_size)
        self.information_model = information_model
        self.sustainability = sustainability or SustainabilityAssumptions()
        self.matrix_cache_dir = matrix_cache_dir

    def run(self) -> ExperimentResult:
        """Execute all comparison cases and assert the operational no-regret policy."""

        matrix = build_matrix(
            self.graph,
            points_from_instance(self.instance),
            cache_dir=self.matrix_cache_dir,
        )
        baseline = self.solver.solve(self.instance, matrix)
        disrupted = apply_scenario(self.graph, self.scenario)
        t2 = execute_frozen_routes(
            self.graph,
            disrupted.graph,
            self.instance,
            baseline,
            information_model=self.information_model,
        )
        oracle = self._oracle(disrupted)
        if self.information_model is InformationModel.REACTIVE:
            t3 = replan_at_first_discovery(
                self.graph,
                disrupted.graph,
                self.instance,
                baseline,
            )
        else:
            t3 = _record_from_solution(oracle) if oracle is not None else _failed_record(t2)

        if t2.total_time_s is not None and t3.total_time_s is not None:
            if t3.total_time_s > t2.total_time_s + 1e-9:
                raise AssertionError(
                    "T3 exceeded T2 despite the no-regret fallback; investigate this scenario"
                )
        saving = _saving_percent(t2.total_time_s, t3.total_time_s)
        oracle_time = None if oracle is None else oracle.total_time_s
        oracle_saving = _saving_percent(t2.total_time_s, oracle_time)
        status = t3.status
        run_id = self._run_id()
        return ExperimentResult(
            run_id=run_id,
            instance_name=self.instance.name,
            instance_hash=self.instance.content_hash(),
            scenario_name=self.scenario.name,
            solver=self.solver.name,
            information_model=self.information_model,
            status=status,
            n_stops=self.instance.n_stops,
            fleet_size=self.instance.fleet_size,
            t1_s=round(baseline.total_time_s, 6),
            t2_s=_rounded(t2.total_time_s),
            t3_s=_rounded(t3.total_time_s),
            t3_oracle_s=_rounded(oracle_time),
            saving_percent=_rounded(saving),
            oracle_saving_percent=_rounded(oracle_saving),
            t1_environment=self.sustainability.calculate(baseline.total_distance_m),
            t2_environment=self.sustainability.calculate(t2.distance_m),
            t3_environment=self.sustainability.calculate(t3.distance_m),
            t3_oracle_environment=None
            if oracle is None
            else self.sustainability.calculate(oracle.total_distance_m),
            detours=t2.detours,
            replans=0 if isinstance(t3, ExecutionRecord) else t3.replans,
            fallback_used=False if isinstance(t3, ExecutionRecord) else t3.fallback_used,
            stops_served=len(t3.stops_served),
            stops_missed=t3.stops_missed,
            n_edges_removed=disrupted.audit.n_edges_removed,
            n_edges_slowed=disrupted.audit.n_edges_slowed,
            removed_length_m=round(disrupted.audit.total_length_removed_m, 6),
            baseline_orders=tuple(route.order for route in baseline.routes),
            t1_paths=tuple(route.path_nodes for route in baseline.routes),
            t2_paths=t2.route_paths,
            t3_paths=t3.route_paths,
            oracle_orders=() if oracle is None else tuple(route.order for route in oracle.routes),
        )

    def write(self, output_root: str | Path) -> Path:
        """Run and write byte-stable result JSON plus its complete YAML configuration."""

        result = self.run()
        destination = Path(output_root) / result.run_id
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "result.json").write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        config = self._config_payload()
        (destination / "config.yaml").write_text(
            yaml.safe_dump(config, sort_keys=True, allow_unicode=True),
            encoding="utf-8",
        )
        return destination

    def _oracle(self, disrupted: DisruptedGraph) -> Solution | None:
        try:
            matrix = build_matrix(disrupted.graph, points_from_instance(self.instance))
            return self.solver.solve(self.instance, matrix)
        except (MatrixBuildError, SolverError, nx.NetworkXError):
            return None

    def _config_payload(self) -> dict[str, object]:
        return {
            "information_model": self.information_model.value,
            "instance": self.instance.model_dump(mode="json", exclude={"created_at"}),
            "scenario": self.scenario.model_dump(mode="json"),
            "solver": self.solver.name,
            "sustainability": self.sustainability.model_dump(mode="json"),
        }

    def _run_id(self) -> str:
        encoded = json.dumps(self._config_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]


def _record_from_solution(solution: Solution) -> ExecutionRecord:
    stop_ids = tuple(point for route in solution.routes for point in route.order[1:-1])
    return ExecutionRecord(
        status=ExecutionStatus.COMPLETE,
        total_time_s=solution.total_time_s,
        driving_time_s=solution.total_driving_time_s,
        service_time_s=solution.total_service_time_s,
        distance_m=solution.total_distance_m,
        detours=0,
        stops_served=stop_ids,
        stops_missed=(),
        route_paths=tuple(route.path_nodes for route in solution.routes),
        detections=(),
    )


def _failed_record(reference: ExecutionRecord) -> ExecutionRecord:
    return ExecutionRecord(
        status=reference.status,
        total_time_s=None,
        driving_time_s=reference.driving_time_s,
        service_time_s=reference.service_time_s,
        distance_m=reference.distance_m,
        detours=reference.detours,
        stops_served=reference.stops_served,
        stops_missed=reference.stops_missed,
        route_paths=reference.route_paths,
        detections=reference.detections,
    )


def _saving_percent(t2_s: float | None, t3_s: float | None) -> float | None:
    if t2_s is None or t3_s is None or t2_s <= 0:
        return None
    return (t2_s - t3_s) / t2_s * 100.0


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 6)
