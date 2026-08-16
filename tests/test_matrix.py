"""Tests for exact directed matrices, caching, and incremental row/column updates."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import numpy as np

from dlm.instance.matrix import PointRef, build_matrix, points_from_instance
from dlm.instance.schema import DeliveryInstance


def test_hand_checked_directed_matrix(
    road_graph: nx.MultiDiGraph, delivery_instance: DeliveryInstance
) -> None:
    matrix = build_matrix(road_graph, points_from_instance(delivery_instance))
    assert matrix.cost("depot", "s1") == 32.0
    assert matrix.cost("s1", "depot") == 32.0
    assert matrix.cost("depot", "s2") != matrix.cost("s2", "depot")
    assert matrix.asymmetry_rate() > 0
    assert matrix.triangle_violations() == 0
    assert matrix.path("depot", "s1") == (0, 1, 2, 3)


def test_incremental_add_matches_full_rebuild(road_graph: nx.MultiDiGraph) -> None:
    initial = [PointRef("depot", 0), PointRef("s1", 3), PointRef("s2", 5)]
    incremental = build_matrix(road_graph, initial)
    incremental.add_point(road_graph, PointRef("s3", 6))
    full = build_matrix(road_graph, [*initial, PointRef("s3", 6)])
    np.testing.assert_allclose(incremental.time_s, full.time_s)
    np.testing.assert_allclose(incremental.distance_m, full.distance_m)
    assert incremental.paths == full.paths


def test_remove_then_add_restores_direct_construction(road_graph: nx.MultiDiGraph) -> None:
    points = [PointRef("depot", 0), PointRef("s1", 3), PointRef("s2", 5)]
    matrix = build_matrix(road_graph, points)
    matrix.remove_point("s1")
    matrix.add_point(road_graph, PointRef("s1", 3))
    expected = build_matrix(
        road_graph, [PointRef("depot", 0), PointRef("s2", 5), PointRef("s1", 3)]
    )
    np.testing.assert_allclose(matrix.time_s, expected.time_s)


def test_matrix_cache_reorders_same_node_set(road_graph: nx.MultiDiGraph, tmp_path: Path) -> None:
    first = [PointRef("depot", 0), PointRef("a", 3), PointRef("b", 5)]
    build_matrix(road_graph, first, cache_dir=tmp_path)
    reordered = [PointRef("depot", 0), PointRef("b", 5), PointRef("a", 3)]
    cached = build_matrix(road_graph, reordered, cache_dir=tmp_path)
    direct = build_matrix(road_graph, reordered)
    np.testing.assert_allclose(cached.time_s, direct.time_s)
    assert cached.paths == direct.paths
