# Disruption scenario schema

Scenario YAML is a stable, versioned scientific input. Committed and map-drawn scenarios are
serialised through the same Pydantic models, so YAML → model → YAML is byte-stable.

```yaml
schema_version: 1
name: example_city_centre
description: Simulated corridor closure with surrounding delay.
source: Modelling scenario; not a live traffic notice.
created: 2026-08-16
disruptions:
  - id: corridor
    type: corridor_closure
    severity: full
    street: O'Connell Street Lower
    geometry: []
    edge_ids: []
    node_ids: []
    factor: 2.0
    buffer_m: 35.0
    start_s: null
    end_s: null
  - id: spillover
    type: slow_zone
    severity: partial
    street: null
    geometry:
      - [-6.2620, 53.3470]
      - [-6.2575, 53.3470]
      - [-6.2575, 53.3515]
      - [-6.2620, 53.3515]
      - [-6.2620, 53.3470]
    edge_ids: []
    node_ids: []
    factor: 2.0
    buffer_m: 35.0
    start_s: null
    end_s: null
```

## Fields

| Field | Contract |
|---|---|
| `schema_version` | Must be `1`. |
| `name` | Stable identifier used in run hashes/results. |
| `description`, `source`, `created` | Human provenance; source must not imply live truth. |
| `type` | `edge_closure`, `polygon_closure`, `corridor_closure`, `slow_zone`, or `node_closure`. |
| `severity` | `full` removes; `partial` slows and requires a factor greater than 1. |
| `edge_ids` | Explicit `[u, v, key]` directed edges. |
| `node_ids` | Explicit graph nodes for a node closure. |
| `street` | Case-insensitive name match for a corridor. |
| `geometry` | Flat YAML coordinate list in `[longitude, latitude]` order; polygon rings close by repeating the first point. |
| `buffer_m` | Corridor half-width approximation in metres (converted locally to degrees). |
| `factor` | Travel-time multiplier greater than 1 for slow/partial effects. |
| `start_s`, `end_s` | Optional seconds after route start; preserved in v1 schema. |

Application returns counts of removed/slowed edges and nodes plus removed metres. The base graph
is not mutated. Validate any file before running it:

```bash
dlm scenario validate scenarios/oconnell_march.yaml
dlm compare --instance data/instances/small-n8.json \
  --scenario scenarios/oconnell_march.yaml --output-dir results/example
```

The Streamlit Draw control converts Polygon or LineString GeoJSON into the flat YAML coordinates
through this same schema. A
round-trip regression test proves a drawn scenario replayed by the CLI produces byte-identical
YAML and identical metrics.
