# Stage 01 — Dublin road network

## Goal

Make a directed, routable, travel-time-annotated M50-catchment graph available once and reload it
from a reproducible cache on later commands.

## Scope

In scope: OSMnx drive download, explicit bbox/place option, largest strong component, versioned
speed imputation, travel seconds, GraphML/metadata cache, validated fast local sidecar, safe
snapping, and network CLI. Stop selection and all-pairs matrices arrive in Stages 2–3.

## Design

`NetworkSpec` is the complete cache input. OSMnx `drive` preserves one-way direction; only the
largest SCC is retained. The key includes OSMnx version and the full YAML speed policy. GraphML
is the portable source of truth; a validated project-generated binary sidecar accelerates reloads,
and both are written atomically. The accepted area/depot policy is
[ADR-0002](../adr/ADR-0002-study-area-and-depot.md).

## Interfaces

- `build_or_load_network(spec=None, ...) -> NetworkBuildResult` — graph, path, hit, time, stats.
- `network_stats(graph) -> NetworkStats` — connectivity, length, and speed provenance.
- `annotate_travel_times(graph, defaults) -> None` — edge km/h and seconds.
- `snap_to_node(graph, lat, lon, max_distance_m=500) -> SnapResult` — guarded road node.
- `dlm network build|stats` — acquisition and inspection.

## Data & assumptions

Bbox is `(-6.50,53.20,-6.05,53.47)` in WGS84. Edge length is metres. Explicit numeric OSM
`maxspeed` wins; missing values use the documented YAML table. No live traffic/signal delay is
added. See [data provenance](../data.md).

## How to run

```bash
dlm network build
dlm network stats
dlm network build --force
```

## Acceptance criteria

- ✅ Fixture tests prove deterministic cache miss/hit, SCC extraction, metadata, and speed mix.
- ✅ Directed asymmetry/one-way behaviour is retained by `test_network.py` and matrix tests.
- ✅ Excessive/sea-like snap distance raises typed `SnapDistanceError` with metres in the message.
- ✅ Manual GitHub workflow builds fresh OSM, reloads cache, asserts non-empty SCC, and uploads
  network statistics as an evidence artifact.
- ✅ Current node/edge counts, speed provenance, and reload time below are transcribed from the
  live acceptance artifact rather than invented by deterministic fixture tests.
- 🟨 A final human route comparison with a separate map tool remains a submission review task;
  third-party route results are traffic/profile dependent and are not asserted by CI.

## Results / evidence

The final local suite passes all network tests without network access. The verified live M50 run
on 2026-08-16 produced 39,983 nodes, 87,448 directed edges, 8,751,668.604 m of directed edge
length, and a strongly connected graph. Explicit OSM speeds covered 88.191% of edges; the
documented policy imputed 11.809%. Fresh acquisition/annotation/cache creation took 67.396 s on
the GitHub runner, and validated sidecar reload took 1.194 s. The N=8 full-service case completed;
the O'Connell stress case correctly returned a structured partial result (2 served, 6 missed)
after removing 8 edges and slowing 77. Evidence and maps are in
[live M50 acceptance run 31960850268](https://github.com/shlokshetty71002/dynamic-last-mile-delivery-routing/actions/runs/31960850268).

`.github/workflows/live-network-acceptance.yml` is the auditable, manually dispatched
external-data gate; cache metadata records UTC access.

## Known limitations

OSM changes, bbox is rectangular, speeds may be imputed, and signal/queue/parking effects are
absent. Strong-component filtering removes fragments instead of modelling ferries/private access.

## Next

Stage 2 uses the stable graph and guarded snapping to create user-defined instances.
