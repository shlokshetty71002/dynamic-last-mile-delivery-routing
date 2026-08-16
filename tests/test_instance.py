"""Tests for dynamic, mutable, and losslessly serialised delivery instances."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from dlm.instance.builder import InstanceBuilder, InstanceBuilderError
from dlm.instance.geocode import (
    AmbiguousAddressError,
    CachedGeocoder,
    GeocodeCandidate,
)
from dlm.instance.presets import load_presets
from dlm.instance.schema import DeliveryInstance, LocationSource
from dlm.workflows import resolve_instance


def test_builder_add_remove_move_and_dynamic_n(road_graph: nx.MultiDiGraph) -> None:
    builder = InstanceBuilder(road_graph, name="mutable", max_snap_distance_m=20)
    builder.set_depot_from_latlon(53.3300, -6.3000)
    added = builder.add_stop_from_latlon(53.3300, -6.2900, label="A")
    builder.add_stop_from_latlon(53.3300, -6.2800, label="B")
    assert builder.build().n_stops == 2

    removed = builder.remove_stop(added.location_id)
    assert removed.invalidated_nodes == (1,)
    builder.add_stop_from_latlon(53.3400, -6.2900, label="C")
    moved = builder.move_stop("s1", 53.3400, -6.3000)
    assert moved.invalidated_nodes == (4, 5)
    assert builder.build().n_stops == 2


@pytest.mark.parametrize("n", [1, 2, 3, 5, 7])
def test_random_instance_size_is_never_hard_coded(road_graph: nx.MultiDiGraph, n: int) -> None:
    builder = InstanceBuilder(road_graph, seed=123, max_snap_distance_m=20)
    builder.set_depot_from_latlon(53.3300, -6.3000)
    builder.add_random_stops(n, seed=123)
    instance = builder.build()
    assert instance.n_stops == n
    assert len(instance.points) == n + 1


def test_save_load_round_trip_is_lossless(
    delivery_instance: DeliveryInstance, tmp_path: Path
) -> None:
    path = delivery_instance.save(tmp_path / "instance.json")
    loaded = DeliveryInstance.load(path)
    assert loaded == delivery_instance
    assert loaded.content_hash() == delivery_instance.content_hash()


def test_builder_rejects_duplicate_road_node(road_graph: nx.MultiDiGraph) -> None:
    builder = InstanceBuilder(road_graph, max_snap_distance_m=20)
    builder.set_depot_from_latlon(53.3300, -6.3000)
    with pytest.raises(InstanceBuilderError, match="same road node"):
        builder.add_stop_from_latlon(53.3300, -6.3000)


def test_address_ambiguity_returns_candidates(road_graph: nx.MultiDiGraph, tmp_path: Path) -> None:
    candidates = [
        GeocodeCandidate("Main Street, Swords", 53.4597, -6.2181),
        GeocodeCandidate("Main Street, Blackrock", 53.3018, -6.1777),
    ]
    geocoder = CachedGeocoder(tmp_path, provider=lambda _query, _limit: candidates)
    builder = InstanceBuilder(road_graph, geocoder=geocoder)
    with pytest.raises(AmbiguousAddressError) as error:
        builder.set_depot_from_address("Main Street")
    assert error.value.candidates == candidates


def test_same_coordinate_input_sources_snap_to_same_node(road_graph: nx.MultiDiGraph) -> None:
    builder = InstanceBuilder(road_graph, max_snap_distance_m=20)
    builder.set_depot_from_latlon(53.3300, -6.3000)
    builder.add_stop_from_latlon(
        53.3300,
        -6.2900,
        label="Map choice",
        source=LocationSource.MAP_CLICK,
    )
    assert builder.stops[0].node == 1


def test_curated_catalogue_has_at_least_thirty_locations() -> None:
    presets = load_presets()
    assert len(presets) >= 30
    assert "ucd belfield" in presets
    assert "dublin port" in presets


def test_committed_report_instances_have_canonical_dynamic_sizes() -> None:
    expected = {
        "small-n8.json": 8,
        "medium-n20.json": 20,
        "large-n40.json": 40,
    }
    for filename, n_stops in expected.items():
        instance = DeliveryInstance.load(Path("data/instances") / filename)
        assert instance.n_stops == n_stops
        assert all(point.node is None for point in instance.points)


def test_coordinate_only_instance_resolves_without_changing_source(
    road_graph: nx.MultiDiGraph,
) -> None:
    instance = DeliveryInstance(
        name="portable",
        depot={
            "label": "Depot",
            "lat": 53.3300,
            "lon": -6.3000,
            "source": "preset",
        },
        stops=(
            {
                "id": "s1",
                "label": "Customer",
                "lat": 53.3300,
                "lon": -6.2900,
                "source": "preset",
            },
        ),
    )
    resolved = resolve_instance(road_graph, instance, max_snap_distance_m=20)
    assert instance.depot.node is None
    assert instance.stops[0].node is None
    assert resolved.node_ids == (0, 1)


def test_editable_builder_loads_coordinate_only_instance(
    road_graph: nx.MultiDiGraph,
) -> None:
    instance = DeliveryInstance(
        name="portable-builder",
        depot={"label": "Depot", "lat": 53.3300, "lon": -6.3000, "source": "preset"},
        stops=(
            {
                "id": "s1",
                "label": "Customer",
                "lat": 53.3300,
                "lon": -6.2900,
                "source": "preset",
            },
        ),
    )
    builder = InstanceBuilder.from_instance(
        road_graph,
        instance,
        max_snap_distance_m=20,
    )
    assert builder.build().node_ids == (0, 1)
    assert instance.depot.node is None
