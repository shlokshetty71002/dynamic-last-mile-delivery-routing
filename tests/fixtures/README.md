# Deterministic test fixtures

Tests construct a small hand-built directed graph in `tests/conftest.py`. Its edge times, lengths,
one-way asymmetry, shortest paths, optimal routes, and disruption outcomes are known exactly. This
keeps CI independent from OpenStreetMap availability and makes numeric regressions defensible by
hand. The manual live-network workflow separately checks current OSM acquisition and cache reload.
