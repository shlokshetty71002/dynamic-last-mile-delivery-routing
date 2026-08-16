"""Deterministic directed-road fixtures used across the scientific test suite."""

from __future__ import annotations

from datetime import UTC, datetime

import networkx as nx
import pytest

from dlm.instance.schema import DeliveryInstance, Depot, LocationSource, Stop


@pytest.fixture
def road_graph() -> nx.MultiDiGraph:
    """Return a small strongly connected, asymmetric road graph with WGS84 coordinates."""

    graph = nx.MultiDiGraph(crs="EPSG:4326", dlm_cache_key="fixture-v1")
    coordinates = {
        0: (-6.3000, 53.3300),
        1: (-6.2900, 53.3300),
        2: (-6.2800, 53.3300),
        3: (-6.2800, 53.3400),
        4: (-6.2900, 53.3400),
        5: (-6.3000, 53.3400),
        6: (-6.2700, 53.3350),
        7: (-6.3100, 53.3350),
    }
    for node, (lon, lat) in coordinates.items():
        graph.add_node(node, x=lon, y=lat)

    def edge(u: int, v: int, seconds: float, metres: float, name: str) -> None:
        graph.add_edge(
            u,
            v,
            key=0,
            travel_time=seconds,
            length=metres,
            speed_kph=metres / seconds * 3.6,
            speed_source="imputed",
            name=name,
            highway="residential",
        )

    edges = [
        (0, 1, 10, 100, "Alpha Road"),
        (1, 2, 10, 100, "Alpha Road"),
        (2, 3, 12, 120, "Beta Street"),
        (3, 4, 10, 100, "Gamma Street"),
        (4, 5, 10, 100, "Gamma Street"),
        (5, 0, 12, 120, "Delta Road"),
        (1, 4, 8, 80, "Central Link"),
        (4, 1, 14, 80, "Central Link"),
        (2, 6, 7, 70, "East Spur"),
        (6, 3, 7, 70, "East Spur"),
        (5, 7, 7, 70, "West Spur"),
        (7, 0, 7, 70, "West Spur"),
    ]
    for u, v, seconds, metres, name in edges:
        edge(u, v, seconds, metres, name)
    reverse_edges = [
        (1, 0, 15, 100, "Alpha Road"),
        (2, 1, 15, 100, "Alpha Road"),
        (3, 2, 18, 120, "Beta Street"),
        (4, 3, 15, 100, "Gamma Street"),
        (5, 4, 15, 100, "Gamma Street"),
        (0, 5, 18, 120, "Delta Road"),
        (6, 2, 11, 70, "East Spur"),
        (3, 6, 11, 70, "East Spur"),
        (7, 5, 11, 70, "West Spur"),
        (0, 7, 11, 70, "West Spur"),
    ]
    for u, v, seconds, metres, name in reverse_edges:
        edge(u, v, seconds, metres, name)
    return graph


@pytest.fixture
def delivery_instance() -> DeliveryInstance:
    """Return a four-stop fixture aligned with ``road_graph`` nodes."""

    locations = [
        ("s1", "North East", 53.3400, -6.2800, 3, 2.0),
        ("s2", "North West", 53.3400, -6.3000, 5, 1.0),
        ("s3", "East", 53.3350, -6.2700, 6, 2.0),
        ("s4", "West", 53.3350, -6.3100, 7, 1.0),
    ]
    return DeliveryInstance(
        name="fixture-four",
        depot=Depot(
            label="Depot",
            lat=53.3300,
            lon=-6.3000,
            node=0,
            source=LocationSource.LATLON,
        ),
        stops=tuple(
            Stop(
                id=stop_id,
                label=label,
                lat=lat,
                lon=lon,
                node=node,
                demand=demand,
                service_time_s=30.0,
                source=LocationSource.LATLON,
            )
            for stop_id, label, lat, lon, node, demand in locations
        ),
        fleet_size=1,
        vehicle_capacity=6.0,
        seed=42,
        created_at=datetime(2026, 8, 16, tzinfo=UTC),
    )
