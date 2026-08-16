"""Mutable instance construction API shared by the CLI and Streamlit client."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import networkx as nx

from dlm.instance.geocode import CachedGeocoder
from dlm.instance.presets import get_preset
from dlm.instance.schema import (
    DEFAULT_SERVICE_TIME_S,
    MAX_STOPS,
    DeliveryInstance,
    Depot,
    LocationSource,
    Stop,
)
from dlm.network.snapping import SnapResult, snap_to_node


class InstanceBuilderError(ValueError):
    """Raised when an edit would create an invalid routing instance."""


@dataclass(frozen=True)
class MutationResult:
    """Plain-language record of an instance edit and matrix invalidation scope."""

    action: str
    location_id: str
    label: str
    invalidated_nodes: tuple[int | str, ...]


class InstanceBuilder:
    """Build and edit a dynamic delivery instance without rebuilding its road graph."""

    def __init__(
        self,
        graph: nx.MultiDiGraph,
        *,
        name: str = "delivery-run",
        seed: int = 42,
        max_snap_distance_m: float = 500.0,
        geocoder: CachedGeocoder | None = None,
        preset_path: str | Path | None = None,
    ) -> None:
        self.graph = graph
        self.name = name
        self.seed = seed
        self.max_snap_distance_m = max_snap_distance_m
        self.geocoder = geocoder
        self.preset_path = preset_path
        self.depot: Depot | None = None
        self.stops: list[Stop] = []
        self.fleet_size = 1
        self.vehicle_capacity: float | None = None

    def set_depot_from_latlon(
        self,
        lat: float,
        lon: float,
        *,
        label: str = "Depot",
        source: LocationSource = LocationSource.LATLON,
    ) -> MutationResult:
        """Select and snap the mandatory depot from WGS84 coordinates."""

        snapped = self._snap(lat, lon)
        old = () if self.depot is None or self.depot.node is None else (self.depot.node,)
        self._ensure_node_unused(snapped.node, ignore_id="depot")
        self.depot = Depot(label=label, lat=lat, lon=lon, node=snapped.node, source=source)
        return MutationResult("set_depot", "depot", label, (*old, snapped.node))

    def set_depot_from_preset(self, name: str) -> MutationResult:
        """Select the depot from the curated Dublin catalogue."""

        preset = get_preset(name, self.preset_path)
        return self.set_depot_from_latlon(
            preset.lat,
            preset.lon,
            label=preset.name,
            source=LocationSource.PRESET,
        )

    def set_depot_from_address(self, query: str, *, choice: int | None = None) -> MutationResult:
        """Select the depot from an explicitly resolved address candidate."""

        candidate = self._require_geocoder().resolve(query, choice=choice)
        return self.set_depot_from_latlon(
            candidate.lat,
            candidate.lon,
            label=candidate.display_name,
            source=LocationSource.ADDRESS,
        )

    def add_stop_from_latlon(
        self,
        lat: float,
        lon: float,
        *,
        label: str | None = None,
        demand: float = 0.0,
        service_time_s: float = DEFAULT_SERVICE_TIME_S,
        source: LocationSource = LocationSource.LATLON,
    ) -> MutationResult:
        """Add and snap one delivery stop from WGS84 coordinates."""

        if len(self.stops) >= MAX_STOPS:
            raise InstanceBuilderError(f"At most {MAX_STOPS} delivery stops are supported")
        snapped = self._snap(lat, lon)
        self._ensure_node_unused(snapped.node)
        stop_id = self._next_stop_id()
        active_label = label or f"Customer {len(self.stops) + 1}"
        stop = Stop(
            id=stop_id,
            label=active_label,
            lat=lat,
            lon=lon,
            node=snapped.node,
            demand=demand,
            service_time_s=service_time_s,
            source=source,
        )
        self.stops.append(stop)
        return MutationResult("add", stop_id, active_label, (snapped.node,))

    def add_stop_from_preset(self, name: str, **kwargs: float) -> MutationResult:
        """Add one delivery stop from the curated Dublin catalogue."""

        preset = get_preset(name, self.preset_path)
        return self.add_stop_from_latlon(
            preset.lat,
            preset.lon,
            label=preset.name,
            source=LocationSource.PRESET,
            **kwargs,
        )

    def add_stop_from_address(
        self,
        query: str,
        *,
        choice: int | None = None,
        **kwargs: float,
    ) -> MutationResult:
        """Add one delivery stop from an explicitly resolved address candidate."""

        candidate = self._require_geocoder().resolve(query, choice=choice)
        return self.add_stop_from_latlon(
            candidate.lat,
            candidate.lon,
            label=candidate.display_name,
            source=LocationSource.ADDRESS,
            **kwargs,
        )

    def add_random_stops(self, n: int, *, seed: int | None = None) -> list[MutationResult]:
        """Add ``n`` uniformly sampled routable nodes with a reproducible seed."""

        if n < 1 or len(self.stops) + n > MAX_STOPS:
            raise InstanceBuilderError(
                f"Random addition must leave the instance between 1 and {MAX_STOPS} stops"
            )
        used = {point.node for point in self.stops}
        if self.depot is not None:
            used.add(self.depot.node)
        candidates = sorted((node for node in self.graph if node not in used), key=str)
        if len(candidates) < n:
            raise InstanceBuilderError("Road graph does not contain enough unused nodes")
        rng = random.Random(self.seed if seed is None else seed)
        chosen = rng.sample(candidates, n)
        results: list[MutationResult] = []
        for node in chosen:
            data = self.graph.nodes[node]
            results.append(
                self.add_stop_from_latlon(
                    float(data["y"]),
                    float(data["x"]),
                    label=f"Random {len(self.stops) + 1}",
                    source=LocationSource.RANDOM,
                )
            )
        return results

    def remove_stop(self, stop_id: str) -> MutationResult:
        """Remove one stop while invalidating only its matrix row and column."""

        index, stop = self._find_stop(stop_id)
        self.stops.pop(index)
        invalidated = () if stop.node is None else (stop.node,)
        return MutationResult("remove", stop.id, stop.label, invalidated)

    def rename_stop(self, stop_id: str, label: str) -> MutationResult:
        """Rename a stop without invalidating any matrix values."""

        index, stop = self._find_stop(stop_id)
        self.stops[index] = stop.model_copy(update={"label": label})
        return MutationResult("rename", stop.id, label, ())

    def move_stop(self, stop_id: str, lat: float, lon: float) -> MutationResult:
        """Move and re-snap one stop, invalidating only old/new rows and columns."""

        index, stop = self._find_stop(stop_id)
        snapped = self._snap(lat, lon)
        self._ensure_node_unused(snapped.node, ignore_id=stop_id)
        self.stops[index] = stop.model_copy(
            update={
                "lat": lat,
                "lon": lon,
                "node": snapped.node,
                "source": LocationSource.LATLON,
            }
        )
        old = () if stop.node is None else (stop.node,)
        return MutationResult("move", stop.id, stop.label, (*old, snapped.node))

    def build(self) -> DeliveryInstance:
        """Validate reachability and freeze the current builder state."""

        if self.depot is None:
            raise InstanceBuilderError("Choose a depot before building the delivery instance")
        if not self.stops:
            raise InstanceBuilderError("Add at least one delivery stop")
        nodes = [self.depot.node, *(stop.node for stop in self.stops)]
        if any(node is None for node in nodes):
            raise InstanceBuilderError("Every depot and stop must resolve to a road node")
        depot_node = self.depot.node
        assert depot_node is not None
        unreachable = [
            stop.label
            for stop in self.stops
            if stop.node is None
            or not nx.has_path(self.graph, depot_node, stop.node)
            or not nx.has_path(self.graph, stop.node, depot_node)
        ]
        if unreachable:
            raise InstanceBuilderError(
                "Locations are not mutually reachable with the depot: " + ", ".join(unreachable)
            )
        return DeliveryInstance(
            name=self.name,
            depot=self.depot,
            stops=tuple(self.stops),
            fleet_size=self.fleet_size,
            vehicle_capacity=self.vehicle_capacity,
            seed=self.seed,
            created_at=datetime.now(UTC),
        )

    @classmethod
    def from_instance(
        cls,
        graph: nx.MultiDiGraph,
        instance: DeliveryInstance,
        **kwargs: object,
    ) -> InstanceBuilder:
        """Create an editable builder from a validated saved instance."""

        builder = cls(graph, name=instance.name, seed=instance.seed, **kwargs)
        depot = instance.depot
        if depot.node is None:
            depot = depot.model_copy(update={"node": builder._snap(depot.lat, depot.lon).node})
        builder.depot = depot
        stops: list[Stop] = []
        for stop in instance.stops:
            if stop.node is None:
                stop = stop.model_copy(update={"node": builder._snap(stop.lat, stop.lon).node})
            stops.append(stop)
        builder.stops = stops
        builder.fleet_size = instance.fleet_size
        builder.vehicle_capacity = instance.vehicle_capacity
        builder.build()
        return builder

    def _snap(self, lat: float, lon: float) -> SnapResult:
        return snap_to_node(
            self.graph,
            lat,
            lon,
            max_distance_m=self.max_snap_distance_m,
        )

    def _find_stop(self, stop_id: str) -> tuple[int, Stop]:
        for index, stop in enumerate(self.stops):
            if stop.id == stop_id:
                return index, stop
        raise InstanceBuilderError(f"Unknown stop ID: {stop_id}")

    def _ensure_node_unused(self, node: int | str, *, ignore_id: str | None = None) -> None:
        points: list[Depot | Stop] = ([] if self.depot is None else [self.depot]) + self.stops
        for point in points:
            if point.id != ignore_id and point.node == node:
                raise InstanceBuilderError(
                    f"Location snaps to the same road node as {point.label!r}; move or merge it"
                )

    def _next_stop_id(self) -> str:
        used = {stop.id for stop in self.stops}
        number = 1
        while f"s{number}" in used:
            number += 1
        return f"s{number}"

    def _require_geocoder(self) -> CachedGeocoder:
        if self.geocoder is None:
            raise InstanceBuilderError("Address input requires a configured CachedGeocoder")
        return self.geocoder
