"""Tests for tidy batch output and seeded statistical summaries."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import networkx as nx

from dlm.disruption.schema import Disruption, DisruptionType, Scenario
from dlm.instance.schema import DeliveryInstance
from dlm.simulation.batch import (
    BatchCase,
    bootstrap_mean_ci,
    load_rows,
    run_batch,
    summarise_savings,
)


def fixture_scenario(name: str, edge: tuple[int, int, int]) -> Scenario:
    return Scenario(
        name=name,
        description="Batch test scenario.",
        source="Test fixture.",
        created=date(2026, 8, 16),
        disruptions=(
            Disruption(
                id="closure",
                type=DisruptionType.EDGE_CLOSURE,
                edge_ids=(edge,),
            ),
        ),
    )


def test_batch_writes_reloadable_tidy_rows(
    road_graph: nx.MultiDiGraph,
    delivery_instance: DeliveryInstance,
    tmp_path: Path,
) -> None:
    cases = [
        BatchCase(delivery_instance, fixture_scenario("no_contact", (1, 4, 0))),
        BatchCase(delivery_instance, fixture_scenario("route_contact", (1, 2, 0))),
    ]
    destination = tmp_path / "summary.csv"
    rows = run_batch(road_graph, cases, destination)
    loaded = load_rows(destination)
    assert len(rows) == len(loaded) == 2
    assert {row["scenario_name"] for row in loaded} == {"no_contact", "route_contact"}
    assert all("wall_time_ms" in row for row in loaded)


def test_bootstrap_and_group_summary_are_seeded() -> None:
    values = [0.0, 2.0, 4.0, 6.0]
    assert bootstrap_mean_ci(values, samples=500, seed=7) == bootstrap_mean_ci(
        values, samples=500, seed=7
    )
    rows = [{"scenario_name": "closure", "saving_percent": value} for value in values]
    summary = summarise_savings(rows, bootstrap_samples=500, seed=7)[0]
    assert summary["runs"] == 4
    assert summary["mean_saving_percent"] == 3.0
    assert summary["hurt_fraction"] == 0.0
