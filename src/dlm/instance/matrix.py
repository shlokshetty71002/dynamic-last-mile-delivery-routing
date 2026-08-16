"""Directed travel-time, distance, and full-path matrices with incremental updates."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np

from dlm.instance.schema import DeliveryInstance, NodeId


class MatrixBuildError(RuntimeError):
    """Raised when selected instance nodes are not mutually reachable."""


@dataclass(frozen=True)
class PointRef:
    """Stable instance point identifier and corresponding road-graph node."""

    id: str
    node: NodeId


@dataclass
class TravelMatrix:
    """Asymmetric point-to-point costs and node paths on one road graph."""

    points: list[PointRef]
    time_s: np.ndarray
    distance_m: np.ndarray
    paths: dict[tuple[str, str], tuple[NodeId, ...]]
    graph_key: str
    weight: str = "travel_time"

    @property
    def size(self) -> int:
        """Return the number of matrix points, including the depot."""

        return len(self.points)

    @property
    def ids(self) -> tuple[str, ...]:
        """Return point identifiers in matrix order."""

        return tuple(point.id for point in self.points)

    def index(self, point_id: str) -> int:
        """Return the matrix index for a depot or stop ID."""

        try:
            return self.ids.index(point_id)
        except ValueError as exc:
            raise KeyError(f"Unknown matrix point: {point_id}") from exc

    def cost(self, source_id: str, target_id: str) -> float:
        """Return shortest travel time in seconds between two points."""

        return float(self.time_s[self.index(source_id), self.index(target_id)])

    def path(self, source_id: str, target_id: str) -> tuple[NodeId, ...]:
        """Return the full shortest-path node sequence between two points."""

        return self.paths[(source_id, target_id)]

    def asymmetry_rate(self, *, tolerance_s: float = 1e-6) -> float:
        """Return the percentage of unordered point pairs with asymmetric travel time."""

        unequal = 0
        pairs = 0
        for i in range(self.size):
            for j in range(i + 1, self.size):
                pairs += 1
                if abs(float(self.time_s[i, j] - self.time_s[j, i])) > tolerance_s:
                    unequal += 1
        return 0.0 if pairs == 0 else unequal / pairs * 100.0

    def triangle_violations(self, *, tolerance_s: float = 1e-6) -> int:
        """Count directed triangle-inequality violations; exact shortest paths should have none."""

        count = 0
        for i in range(self.size):
            for j in range(self.size):
                for k in range(self.size):
                    if self.time_s[i, k] > self.time_s[i, j] + self.time_s[j, k] + tolerance_s:
                        count += 1
        return count

    def add_point(self, graph: nx.MultiDiGraph, point: PointRef) -> None:
        """Append one row and column using two Dijkstra searches, not a full rebuild."""

        if point.id in self.ids:
            raise MatrixBuildError(f"Matrix point ID already exists: {point.id}")
        if any(existing.node == point.node for existing in self.points):
            raise MatrixBuildError(f"Road node already exists in matrix: {point.node}")
        forward_lengths, forward_paths = nx.single_source_dijkstra(
            graph, point.node, weight=self.weight
        )
        reverse_lengths, reverse_paths = nx.single_source_dijkstra(
            graph.reverse(copy=False), point.node, weight=self.weight
        )
        old_size = self.size
        new_time = np.full((old_size + 1, old_size + 1), np.inf)
        new_distance = np.full((old_size + 1, old_size + 1), np.inf)
        new_time[:old_size, :old_size] = self.time_s
        new_distance[:old_size, :old_size] = self.distance_m
        new_time[old_size, old_size] = 0.0
        new_distance[old_size, old_size] = 0.0
        self.paths[(point.id, point.id)] = (point.node,)
        for index, existing in enumerate(self.points):
            if existing.node not in forward_paths or existing.node not in reverse_paths:
                raise MatrixBuildError(
                    f"Road nodes {point.node!r} and {existing.node!r} are not mutually reachable"
                )
            path_out = tuple(forward_paths[existing.node])
            path_in = tuple(reversed(reverse_paths[existing.node]))
            new_time[old_size, index] = float(forward_lengths[existing.node])
            new_time[index, old_size] = float(reverse_lengths[existing.node])
            new_distance[old_size, index] = _path_distance_m(graph, path_out, self.weight)
            new_distance[index, old_size] = _path_distance_m(graph, path_in, self.weight)
            self.paths[(point.id, existing.id)] = path_out
            self.paths[(existing.id, point.id)] = path_in
        self.points.append(point)
        self.time_s = new_time
        self.distance_m = new_distance

    def remove_point(self, point_id: str) -> None:
        """Drop one row, column, and related paths without running Dijkstra."""

        index = self.index(point_id)
        self.points.pop(index)
        self.time_s = np.delete(np.delete(self.time_s, index, axis=0), index, axis=1)
        self.distance_m = np.delete(np.delete(self.distance_m, index, axis=0), index, axis=1)
        self.paths = {key: value for key, value in self.paths.items() if point_id not in key}

    def move_point(self, graph: nx.MultiDiGraph, point_id: str, node: NodeId) -> None:
        """Replace one location via the exact remove-plus-incremental-add operation."""

        old_index = self.index(point_id)
        self.remove_point(point_id)
        self.add_point(graph, PointRef(point_id, node))
        if old_index != self.size - 1:
            order = list(range(self.size))
            moved = order.pop()
            order.insert(old_index, moved)
            self._reorder(order)

    def recompute_on(self, graph: nx.MultiDiGraph) -> TravelMatrix:
        """Rebuild the same points on a changed graph view."""

        return build_matrix(graph, self.points, weight=self.weight)

    def _reorder(self, order: list[int]) -> None:
        self.points = [self.points[index] for index in order]
        self.time_s = self.time_s[np.ix_(order, order)]
        self.distance_m = self.distance_m[np.ix_(order, order)]


def points_from_instance(instance: DeliveryInstance) -> list[PointRef]:
    """Convert a resolved instance to stable matrix point references."""

    nodes = instance.node_ids
    return [PointRef(point.id, node) for point, node in zip(instance.points, nodes, strict=True)]


def build_matrix(
    graph: nx.MultiDiGraph,
    points: list[PointRef],
    *,
    weight: str = "travel_time",
    cache_dir: str | Path | None = None,
) -> TravelMatrix:
    """Build or load an all-pairs directed shortest-path matrix for selected points."""

    if not points:
        raise MatrixBuildError("At least one matrix point is required")
    if len({point.id for point in points}) != len(points):
        raise MatrixBuildError("Matrix point IDs must be unique")
    if len({point.node for point in points}) != len(points):
        raise MatrixBuildError("Matrix road nodes must be unique")
    graph_key = graph_signature(graph, weight=weight)
    cache_path = None
    if cache_dir is not None:
        key_payload = {
            "graph": graph_key,
            "nodes": sorted(str(point.node) for point in points),
            "weight": weight,
        }
        key = hashlib.sha256(json.dumps(key_payload, sort_keys=True).encode()).hexdigest()[:20]
        cache_path = Path(cache_dir) / f"matrix-{key}.json"
        if cache_path.exists():
            return _load_cache(cache_path, points)

    size = len(points)
    time_s = np.full((size, size), np.inf)
    distance_m = np.full((size, size), np.inf)
    paths: dict[tuple[str, str], tuple[NodeId, ...]] = {}
    for source_index, source in enumerate(points):
        lengths, source_paths = nx.single_source_dijkstra(graph, source.node, weight=weight)
        for target_index, target in enumerate(points):
            if target.node not in source_paths:
                raise MatrixBuildError(f"No directed path from {source.id!r} to {target.id!r}")
            path = tuple(source_paths[target.node])
            time_s[source_index, target_index] = float(lengths[target.node])
            distance_m[source_index, target_index] = _path_distance_m(graph, path, weight)
            paths[(source.id, target.id)] = path
    matrix = TravelMatrix(list(points), time_s, distance_m, paths, graph_key, weight)
    if cache_path is not None:
        _save_cache(cache_path, matrix)
    return matrix


def graph_signature(graph: nx.MultiDiGraph, *, weight: str = "travel_time") -> str:
    """Return a stable graph fingerprint for scientifically safe matrix caching."""

    explicit = graph.graph.get("dlm_cache_key")
    if explicit:
        return str(explicit)
    digest = hashlib.sha256()
    for node in sorted(graph.nodes, key=str):
        digest.update(f"n:{node!r};".encode())
    edge_rows = sorted(graph.edges(keys=True, data=True), key=lambda row: tuple(map(str, row[:3])))
    for u, v, key, data in edge_rows:
        digest.update(
            f"e:{u!r}:{v!r}:{key!r}:{float(data.get(weight, math.inf)):.9f}:"
            f"{float(data.get('length', 0.0)):.9f};".encode()
        )
    return digest.hexdigest()[:20]


def _path_distance_m(graph: nx.MultiDiGraph, path: tuple[NodeId, ...], weight: str) -> float:
    distance = 0.0
    for u, v in zip(path, path[1:], strict=False):
        edges = graph.get_edge_data(u, v)
        if not edges:
            raise MatrixBuildError(f"Path references missing edge {u!r}->{v!r}")
        chosen = min(edges.values(), key=lambda data: float(data.get(weight, math.inf)))
        distance += float(chosen.get("length", 0.0))
    return distance


def _save_cache(path: Path, matrix: TravelMatrix) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "graph_key": matrix.graph_key,
        "weight": matrix.weight,
        "points": [{"id": point.id, "node": point.node} for point in matrix.points],
        "time_s": matrix.time_s.tolist(),
        "distance_m": matrix.distance_m.tolist(),
        "paths": {
            f"{source}\u001f{target}": list(nodes)
            for (source, target), nodes in sorted(matrix.paths.items())
        },
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    os.replace(temporary, path)


def _load_cache(path: Path, requested: list[PointRef]) -> TravelMatrix:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cached = [PointRef(item["id"], item["node"]) for item in payload["points"]]
    by_node = {str(point.node): index for index, point in enumerate(cached)}
    try:
        order = [by_node[str(point.node)] for point in requested]
    except KeyError as exc:
        raise MatrixBuildError("Matrix cache node set does not match the requested points") from exc
    time_s = np.asarray(payload["time_s"], dtype=float)[np.ix_(order, order)]
    distance_m = np.asarray(payload["distance_m"], dtype=float)[np.ix_(order, order)]
    cached_id_by_node = {str(point.node): point.id for point in cached}
    requested_id_by_node = {str(point.node): point.id for point in requested}
    id_map = {cached_id_by_node[node]: requested_id_by_node[node] for node in requested_id_by_node}
    paths: dict[tuple[str, str], tuple[NodeId, ...]] = {}
    for key, nodes in payload["paths"].items():
        source, target = key.split("\u001f")
        if source in id_map and target in id_map:
            paths[(id_map[source], id_map[target])] = tuple(nodes)
    return TravelMatrix(
        list(requested),
        time_s,
        distance_m,
        paths,
        str(payload["graph_key"]),
        str(payload["weight"]),
    )
