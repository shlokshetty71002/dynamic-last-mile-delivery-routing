# Changelog

All notable changes are recorded by project stage. The project follows Keep a Changelog structure
and uses semantic versioning for release identifiers.

## [Unreleased]

### Stage 10 — Barebones UI

- Added a three-step Streamlit/Folium client for map-click/address/preset/random locations,
  YAML or drawn disruptions, comparisons, maps, metrics, and downloadable result bundles.
- Enforced CLI/UI scientific parity through shared workflows and regression tests.

### Stage 9 — Hardening and reproduction

- Added the complete Typer CLI, pinned Python 3.11/3.12 lock, CI matrix, manual live M50
  acceptance workflow, `make reproduce`, portable canonical instances, and user/run guides.

### Stage 8 — Fleet and benchmark

- Added directed Clarke-Wright multi-vehicle routing, capacity validation, per-route metrics, and
  an OR-Tools benchmark adapter with K=1 regression protection.

### Stage 7 — Experiment harness

- Added parallel deterministic batch runs, seeded random closures, tidy CSV, bootstrap confidence
  intervals, helped/neutral/hurt fractions, and PNG/SVG report figures.

### Stage 6 — Experiment core

- Added explicit reactive/omniscient execution, frozen detours, first-discovery replanning,
  no-regret fallback, T1/T2/T3/T3-oracle, partial service, run hashing, and sustainability metrics.

### Stage 5 — Disruptions

- Added versioned YAML/GeoJSON edge, node, polygon, corridor, and slow-zone disruptions;
  non-mutating application/audit/revert; four transparent Dublin modelling scenarios.

### Stage 4 — Baseline routing

- Added nearest-neighbour construction, directed full-cost 2-opt/relocate improvement, expanded
  route legs/paths, degenerate-size handling, and drive/service/distance breakdowns.

### Stage 3 — Travel-time matrix

- Added asymmetric costs and full paths, deterministic caching, disrupted rebuilds, and genuine
  one-row/one-column incremental add/remove/move operations.

### Stage 2 — Dynamic instances

- Added immutable schema-versioned instances, mutable builder, five location input modes, cached
  ambiguity-safe geocoding, 46 presets, N=8/20/40 canonical instances, and lossless JSON.

### Stage 1 — Dublin road network

- Added explicit M50-catchment OSMnx acquisition, directed SCC extraction, hashed GraphML cache,
  safe snapping, versioned speed imputation, and travel-time provenance statistics.

### Stage 0 — Foundations

- Added src-layout packaging, settings, structured logs, pytest/Ruff/pre-commit, Make targets,
  GitHub Actions, repository skeleton, architecture documentation, and ADRs.
