"""Regression tests for T1/T2/T3 execution, replanning, and environmental metrics."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import networkx as nx

from dlm.disruption.schema import Disruption, DisruptionType, Scenario
from dlm.instance.schema import DeliveryInstance
from dlm.simulation import Experiment, InformationModel, SustainabilityAssumptions


def closure(name: str, *edges: tuple[int, int, int]) -> Scenario:
    return Scenario(
        name=name,
        description="Deterministic execution test.",
        source="Test fixture.",
        created=date(2026, 8, 16),
        disruptions=(
            Disruption(
                id="closure",
                type=DisruptionType.EDGE_CLOSURE,
                edge_ids=edges,
            ),
        ),
    )


def test_no_route_contact_gives_exact_t1_t2_t3_equality(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    result = Experiment(
        road_graph,
        delivery_instance,
        closure("no_contact", (1, 4, 0)),
    ).run()
    assert result.t1_s == result.t2_s == result.t3_s
    assert result.saving_percent == 0.0
    assert result.detours == 0
    assert result.replans == 0


def test_closure_makes_frozen_route_worse_and_replan_no_regret(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    result = Experiment(
        road_graph,
        delivery_instance,
        closure("two_exit_closure", (0, 1, 0), (0, 5, 0)),
    ).run()
    assert result.t2_s is not None and result.t3_s is not None
    assert result.t2_s > result.t1_s
    assert result.t3_s <= result.t2_s
    assert result.saving_percent is not None and result.saving_percent > 0
    assert result.detours >= 1
    assert result.replans == 1


def test_reactive_is_not_cheaper_than_omniscient_frozen_execution(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    disruption = closure("blocked_alpha", (1, 2, 0))
    reactive = Experiment(road_graph, delivery_instance, disruption).run()
    omniscient = Experiment(
        road_graph,
        delivery_instance,
        disruption,
        information_model=InformationModel.OMNISCIENT,
    ).run()
    assert reactive.t2_s is not None and omniscient.t2_s is not None
    assert reactive.t2_s >= omniscient.t2_s


def test_unreachable_scenario_is_structured_partial_service(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    incident = (
        (2, 3, 0),
        (3, 2, 0),
        (3, 4, 0),
        (4, 3, 0),
        (3, 6, 0),
        (6, 3, 0),
    )
    result = Experiment(
        road_graph,
        delivery_instance,
        closure("isolate_stop", *incident),
    ).run()
    assert result.t2_s is None
    assert result.t3_s is None
    assert result.saving_percent is None
    assert result.stops_missed


def test_result_and_config_are_byte_reproducible(
    road_graph: nx.MultiDiGraph,
    delivery_instance: DeliveryInstance,
    tmp_path: Path,
) -> None:
    experiment = Experiment(
        road_graph,
        delivery_instance,
        closure("repeatable", (1, 4, 0)),
    )
    output = experiment.write(tmp_path)
    first_result = (output / "result.json").read_bytes()
    first_config = (output / "config.yaml").read_bytes()
    second = experiment.write(tmp_path)
    assert (second / "result.json").read_bytes() == first_result
    assert (second / "config.yaml").read_bytes() == first_config


def test_fuel_and_carbon_formula_is_transparent() -> None:
    assumptions = SustainabilityAssumptions(
        diesel_l_per_100km=10.0,
        diesel_co2_kg_per_l=2.5,
        fuel_price_eur_per_l=2.0,
    )
    metrics = assumptions.calculate(10_000.0)
    assert metrics.distance_km == 10.0
    assert metrics.fuel_l == 1.0
    assert metrics.co2_kg == 2.5
    assert metrics.fuel_cost_eur == 2.0
