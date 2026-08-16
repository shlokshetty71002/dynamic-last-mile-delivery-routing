"""Tests for scenario validation, non-mutating graph changes, and reachability audits."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import networkx as nx

from dlm.disruption.engine import apply_scenario
from dlm.disruption.generators import random_edge_closure
from dlm.disruption.schema import Disruption, DisruptionType, Scenario, Severity
from dlm.instance.schema import DeliveryInstance


def scenario(*disruptions: Disruption) -> Scenario:
    return Scenario(
        name="fixture_scenario",
        description="Deterministic test scenario.",
        source="Test fixture.",
        created=date(2026, 8, 16),
        disruptions=disruptions,
    )


def test_explicit_edge_closure_does_not_mutate_base(road_graph: nx.MultiDiGraph) -> None:
    before = road_graph.copy()
    disrupted = apply_scenario(
        road_graph,
        scenario(
            Disruption(
                id="close-alpha",
                type=DisruptionType.EDGE_CLOSURE,
                edge_ids=((1, 2, 0),),
            )
        ),
    )
    assert road_graph.has_edge(1, 2, 0)
    assert not disrupted.graph.has_edge(1, 2, 0)
    assert disrupted.audit.n_edges_removed == 1
    assert nx.utils.graphs_equal(road_graph, before)
    assert nx.utils.graphs_equal(disrupted.revert(), road_graph)


def test_street_corridor_closes_matching_named_edges(road_graph: nx.MultiDiGraph) -> None:
    disrupted = apply_scenario(
        road_graph,
        scenario(
            Disruption(
                id="alpha-street",
                type=DisruptionType.CORRIDOR_CLOSURE,
                street="Alpha Road",
            )
        ),
    )
    assert disrupted.audit.n_edges_removed == 4
    assert all(not disrupted.graph.has_edge(*edge) for edge in disrupted.audit.removed_edges)


def test_slow_zone_multiplies_only_intersecting_edges(road_graph: nx.MultiDiGraph) -> None:
    slow = Disruption(
        id="central-slow",
        type=DisruptionType.SLOW_ZONE,
        geometry=(
            (-6.291, 53.329),
            (-6.279, 53.329),
            (-6.279, 53.341),
            (-6.291, 53.341),
            (-6.291, 53.329),
        ),
        factor=3.0,
    )
    disrupted = apply_scenario(road_graph, scenario(slow))
    assert disrupted.audit.n_edges_slowed > 0
    assert disrupted.graph[1][4][0]["travel_time"] == 24.0
    assert road_graph[1][4][0]["travel_time"] == 8.0


def test_partial_closure_is_modelled_as_slow_access(road_graph: nx.MultiDiGraph) -> None:
    disrupted = apply_scenario(
        road_graph,
        scenario(
            Disruption(
                id="partial-alpha",
                type=DisruptionType.EDGE_CLOSURE,
                severity=Severity.PARTIAL,
                edge_ids=((0, 1, 0),),
                factor=2.0,
            )
        ),
    )
    assert disrupted.graph.has_edge(0, 1, 0)
    assert disrupted.graph[0][1][0]["travel_time"] == 20.0
    assert disrupted.audit.n_edges_slowed == 1


def test_unreachable_stop_is_a_structured_outcome(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    incident = ((2, 3, 0), (3, 2, 0), (3, 4, 0), (4, 3, 0), (3, 6, 0), (6, 3, 0))
    disrupted = apply_scenario(
        road_graph,
        scenario(
            Disruption(id="isolate-three", type=DisruptionType.EDGE_CLOSURE, edge_ids=incident)
        ),
    )
    assert disrupted.unreachable_stops(delivery_instance) == ("North East",)


def test_scenario_yaml_round_trip_is_canonical(tmp_path: Path) -> None:
    original = scenario(
        Disruption(
            id="close-one",
            type=DisruptionType.EDGE_CLOSURE,
            edge_ids=((1, 2, 0),),
        )
    )
    first = original.save(tmp_path / "first.yaml")
    loaded = Scenario.load(first)
    second = loaded.save(tmp_path / "second.yaml")
    assert loaded == original
    assert first.read_bytes() == second.read_bytes()


def test_random_generator_is_seeded(road_graph: nx.MultiDiGraph) -> None:
    first = random_edge_closure(road_graph, n_edges=3, seed=7)
    second = random_edge_closure(road_graph, n_edges=3, seed=7)
    assert first == second


def test_committed_scenarios_validate() -> None:
    scenario_dir = Path(__file__).resolve().parents[1] / "scenarios"
    loaded = [Scenario.load(path) for path in sorted(scenario_dir.glob("*.yaml"))]
    assert len(loaded) == 4
    assert {item.name for item in loaded} == {
        "luas_cross_city_works",
        "oconnell_march",
        "quays_bridge_closure",
        "st_patricks_parade",
    }
