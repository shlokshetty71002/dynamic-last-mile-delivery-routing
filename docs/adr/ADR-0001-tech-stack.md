# ADR-0001 — Technology stack and boundary rules

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision owners:** Shlok Shetty and Rushikesh Mane

## Context

The project needs real Dublin roads, explainable routing heuristics, reproducible disruption
experiments, static report figures, and a simple interactive demonstration. A staged academic
workflow requires the scientific pipeline to remain usable even when the eventual UI is absent.

## Decision

- Python 3.11/3.12 is the supported runtime during development.
- OSMnx/OpenStreetMap and NetworkX will own graph acquisition and shortest paths from Stage 1.
- Pydantic settings validates environment-driven configuration under the `DLM_` prefix.
- Typer provides a CLI; Streamlit + Folium/Leaflet provides the Stage 10 UI.
- Matplotlib produces deterministic report figures.
- pytest verifies behaviour; Ruff handles linting and formatting; pre-commit runs local checks.
- Dependencies are locked in `requirements.txt`; the project package uses `pyproject.toml`.
- Structured logging uses the Python standard library with JSON output, avoiding an additional
  runtime dependency while still providing machine-readable diagnostics.
- Domain logic belongs only in `src/dlm/`. `app/` may call it but may not reimplement it.

## Alternatives considered

- **UI-first development:** rejected because it risks hiding scientific logic in callbacks and
  makes headless reproduction difficult.
- **OR-Tools as the primary solver:** rejected for v1 because NN + directed improvement is easier
  to explain; OR-Tools remains a Stage 8 benchmark oracle.
- **Live traffic APIs:** rejected because availability and historical state would make report
  results difficult to reproduce.
- **Unstructured print debugging:** rejected because stage evidence and long operations need
  stable, parseable logs.

## Consequences

The early stages remain command-line driven and testable. The UI is cheaper and safer to add after
the pipeline is complete. Exact pins increase reproducibility but must be deliberately updated and
re-tested. Real map acquisition still requires network access in Stage 1, so committed fixture
graphs and disk caches will protect tests and repeated demonstrations.
