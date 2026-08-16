# Stage 05 — Disruption engine

## Goal

Turn an explicit YAML or drawn GeoJSON description into a reproducible changed graph and audit
record without mutating the normal road graph.

## Scope

In scope: schema, edge/node/polygon/corridor closure, slow/partial effects, timing fields,
YAML/GeoJSON round-trip, audit/revert, reachability, random generator, and four Dublin scenarios.
Execution timing semantics land in Stage 6.

## Design

Pydantic discriminates types and validates geometry/factors. The engine copies the graph, finds
matching edges/nodes, removes or multiplies travel seconds, and records every change. Scenario
files are model inputs, never represented as live notices.

## Interfaces

- `Scenario.load/save/to_yaml`, `scenario_from_geojson` — canonical serialisation.
- `apply_scenario(graph, scenario) -> DisruptedGraph` — changed graph plus audit.
- `DisruptedGraph.revert()`, `unreachable_points(...)` — restoration/check.
- `random_edge_closure(graph, n_edges, seed, name) -> Scenario` — seeded generator.
- `dlm scenario validate` — schema/provenance inspection.

## Data & assumptions

GeoJSON uses `[longitude, latitude]`. Full effects remove edges/nodes; slow/partial effects require
factor >1. Timing is seconds from route start and preserved. Street matching relies on OSM names.

## How to run

```bash
dlm scenario validate scenarios/oconnell_march.yaml
```

See [the full schema](../../scenarios/README.md).

## Acceptance criteria

- ✅ YAML round-trips byte-identically; drawn GeoJSON replay is identical.
- ✅ Base graph remains unchanged and revert matches its edge attributes.
- ✅ Edge, node, named corridor, polygon, slow zone, and brutal disconnection are tested.
- ✅ Audit counts removed/slowed edges/nodes and removed metres.
- ✅ Four committed scenarios validate and carry non-live modelling provenance.

## Results / evidence

`tests/test_disruption.py` spot-checks exact affected fixture streets and reachability. Real affected
counts depend on the current OSM snapshot and are saved in each comparison result.

## Known limitations

Geometry/name matching reflects OSM tag quality. Temporal activation is schema-preserved but v1
applies the selected scenario for the experiment. No endogenous queue spillback is simulated.

## Next

Stage 6 executes the baseline edge-by-edge against the disrupted graph and replans at discovery.
