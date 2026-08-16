# Stage 03 — Travel-time matrix

## Goal

Provide constant-time directed cost/path lookup for the current depot and stops, while updating a
single changed point without recomputing every old source.

## Scope

In scope: shortest-time and distance matrices, full node paths, hashing/disk cache, add/remove/move,
disrupted rebuild, and asymmetry diagnostics. Stop-order optimisation begins in Stage 4.

## Design

Each source uses NetworkX single-source Dijkstra. Adding a node computes one forward search and
one search on the reversed graph, yielding exactly the new row/column. Removing slices storage;
moving composes remove/add. The graph signature and ordered node set protect cache correctness.

## Interfaces

- `build_matrix(graph, points, weight="travel_time", cache_dir=None) -> TravelMatrix`.
- `TravelMatrix.cost`, `distance`, `path` — directed O(1) lookup.
- `add_point`, `remove_point`, `move_point` — incremental immutable updates.
- `recompute_on(graph)` — same points on a disrupted graph.
- `asymmetry_rate()`, `triangle_inequality_violations()` — diagnostics.

## Data & assumptions

Costs are seconds, distances metres, paths graph node IDs. Infinite/unreachable pairs raise a
structured matrix-build error. Parallel edge choice minimises the requested weight.

## How to run

Matrix construction occurs within `dlm plan`, `dlm compare`, and `dlm batch`; set
`DLM_CACHE_DIR` to relocate the cache.

## Acceptance criteria

- ✅ Hand-computed fixture costs/paths and non-zero directed asymmetry are tested.
- ✅ Incremental add equals a complete rebuild cell-for-cell and preserves old cells.
- ✅ Remove/move and cache round-trip are tested.
- ✅ Disrupted recomputation uses the new graph signature rather than stale paths.

## Results / evidence

`tests/test_matrix.py` verifies all cells on a known asymmetric graph. Real N=20 build/cache timing
is emitted by execution logs and should be reported from the same OSM snapshot/hardware as results.

## Known limitations

Full path storage grows quadratically with point count and path length. Timing comparisons are
hardware/cache dependent. Directed shortest-path distances still obey triangle inequality when all
weights are non-negative; apparent violations indicate tolerance/data/implementation issues.

## Next

Stage 4 consumes matrix costs and paths to construct and expand the baseline route.
