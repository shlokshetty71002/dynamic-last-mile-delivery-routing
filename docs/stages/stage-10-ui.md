# Stage 10 — Barebones Streamlit/Folium UI

## Goal

Let a non-programmer build a dynamic delivery run, draw/load a disruption, and read/download the
complete comparison without adding a second modelling implementation.

## Scope

In scope: three-step Streamlit page, cached graph, map clicks, address/preset/random selection,
delete/save/load, fleet size, Draw GeoJSON, YAML export, information model, metrics, map, and ZIP
download. Custom theming, authentication, hosting, and dispatch operations are out of scope.

## Design

`app/main.py` contains widgets and calls `InstanceBuilder`, `Scenario`, `compare_delivery`, and
visualisation functions. `app/state.py` owns session state. `@st.cache_resource` keeps one graph
per process. [ADR-0005](../adr/ADR-0005-portable-instances-and-thin-ui.md) defines the boundary.

## Interfaces

- `make app` / `streamlit run app/main.py` — launch.
- Step 1 — select depot, mutable stops, K, JSON save/load.
- Step 2 — load YAML or draw Polygon/LineString and export canonical YAML.
- Step 3 — choose reactive/omniscient, compare, inspect layers/metrics, download bundle.
- `initialise_state`, `reset_run_state` — UI-state plumbing only.

## Data & assumptions

Map coordinates are WGS84 and pass through the 500 m snap guard. The graph loads once per app
process. Downloaded result ZIP contains JSON and HTML produced from the exact displayed result.

## How to run

```bash
make app
# Windows:
.\.venv\Scripts\streamlit.exe run app\main.py
```

## Acceptance criteria

- ✅ Builder supports click, address, preset, random, deletion, save/load, and dynamic N.
- ✅ Drawn GeoJSON→YAML→CLI replay is byte/numerically identical in parity tests.
- ✅ App uses shared workflows; forbidden routing/NetworkX algorithm tokens are absent from `app/`.
- ✅ Errors are caught and shown as readable Streamlit messages.
- ✅ Result view presents T1/T2/T3/Saving, operational/environment table, layered map, ZIP download.
- 🟨 Three final screenshots require a live cached graph and are a human acceptance artifact; they
  must be captured from the published branch rather than mocked fixture imagery.

## Results / evidence

`tests/test_cli_ui_parity.py` proves shared-function equality and scenario replay. Streamlit and
CLI entry points pass smoke tests. The final manual walkthrough is: choose depot, add six mixed
stops, draw a polygon, run reactive comparison, inspect map/metrics, download results.

## Known limitations

Streamlit reruns the script on interactions and the app is single-session academic software. Stop
editing is delete/re-add rather than a spreadsheet cell editor. No hosted authentication, storage
quota, or navigation guidance is provided.

## Next

After live CI and manual UI evidence, reviewers can approve the draft PR. Merge and a v1.0 tag
remain explicit owner decisions.
