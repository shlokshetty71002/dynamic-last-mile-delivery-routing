"""Proof that CLI and UI clients call one identical tested scientific workflow."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import networkx as nx

from dlm.disruption.schema import (
    Disruption,
    DisruptionType,
    Scenario,
    scenario_from_geojson,
)
from dlm.instance.schema import DeliveryInstance
from dlm.workflows import compare_delivery, comparison_configuration


def test_shared_workflow_is_byte_identical_for_both_clients(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    scenario = Scenario(
        name="parity",
        description="CLI/UI parity fixture.",
        source="Test fixture.",
        created=date(2026, 8, 16),
        disruptions=(
            Disruption(
                id="closure",
                type=DisruptionType.EDGE_CLOSURE,
                edge_ids=((1, 2, 0),),
            ),
        ),
    )
    cli_result = compare_delivery(road_graph, delivery_instance, scenario)
    ui_result = compare_delivery(road_graph, delivery_instance, scenario)
    assert cli_result.model_dump_json() == ui_result.model_dump_json()
    assert comparison_configuration(
        road_graph,
        delivery_instance,
        scenario,
        cli_result,
    ) == comparison_configuration(
        road_graph,
        delivery_instance,
        scenario,
        ui_result,
    )


def test_drawn_scenario_yaml_replays_identically(
    road_graph: nx.MultiDiGraph,
    delivery_instance: DeliveryInstance,
    tmp_path: Path,
) -> None:
    drawn = scenario_from_geojson(
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [-6.301, 53.329],
                    [-6.289, 53.329],
                    [-6.289, 53.341],
                    [-6.301, 53.341],
                    [-6.301, 53.329],
                ]
            ],
        },
        name="drawn_parity",
        disruption_type=DisruptionType.SLOW_ZONE,
        factor=2.0,
    )
    path = drawn.save(tmp_path / "drawn.yaml")
    loaded = Scenario.load(path)
    from_ui = compare_delivery(road_graph, delivery_instance, drawn)
    from_cli = compare_delivery(road_graph, delivery_instance, loaded)
    assert from_ui.model_dump_json() == from_cli.model_dump_json()


def test_streamlit_client_contains_no_solver_or_graph_algorithm_calls() -> None:
    app_source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    forbidden = (
        "nx.shortest_path",
        "networkx",
        "build_matrix(",
        "apply_scenario(",
        ".solve(",
    )
    assert not any(token in app_source for token in forbidden)
    assert "compare_delivery(" in app_source
    assert "from state import initialise_state, reset_run_state" in app_source
