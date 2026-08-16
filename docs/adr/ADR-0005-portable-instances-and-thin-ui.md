# ADR-0005 — Coordinate-portable instances and a thin UI

- **Status:** Accepted
- **Date:** 2026-08-16

## Context

OpenStreetMap node IDs and topology can change between snapshots. Committing those IDs would make
report instances brittle. Separately, implementing algorithms in Streamlit callbacks would make
headless reproduction and scientific tests diverge.

## Decision

Canonical JSON stores named WGS84 coordinates with null graph nodes. Shared workflows snap a
loaded instance against the graph used for that run and leave the file unchanged. Interactive
instances may store resolved nodes for the same cache. Streamlit may only manage widgets, session
state, caching, and calls into `src/dlm`; CLI and UI both use `plan_delivery`/`compare_delivery`.

## Consequences

Inputs survive OSM refreshes while the run metadata records which graph resolved them. Small path
changes between snapshots remain an honest external-data effect. CLI/UI parity is testable and a
broken front end cannot invalidate the modelling pipeline.
