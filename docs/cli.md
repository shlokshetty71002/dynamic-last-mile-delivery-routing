# Command-line reference

Run `dlm --help` (Unix: `.venv/bin/dlm`; Windows: `.\.venv\Scripts\dlm.exe`) for the installed
version. Every command below invokes the same `src/dlm` domain functions used by Streamlit.

| Capability | Command | Streamlit equivalent |
|---|---|---|
| Show settings/version | `dlm config`, `dlm --version` | Process configuration |
| Build or load graph | `dlm network build [--force]` | Cached app startup |
| Inspect graph | `dlm network stats` | Scenario summary backend |
| List curated places | `dlm instance presets` | Preset dropdowns |
| Mixed-input instance | `dlm instance create ...` | Step 1 inputs |
| Seeded instance | `dlm instance random ...` | Add random stops |
| Validate/display JSON | `dlm instance show PATH` | Load saved instance |
| Map selected locations | `dlm instance map PATH` | Step 1 map |
| Validate/canonicalise YAML | `dlm scenario validate PATH` | Load/export scenario |
| Baseline plan | `dlm plan ...` | Pre-comparison solve |
| T1/T2/T3 comparison | `dlm compare ...` | Run comparison |
| Batch sweep | `dlm batch ...` | Headless/report only |
| Regenerate figure | `dlm figures ...` | Headless/report only |

## Common commands

```bash
dlm network build
dlm network stats
dlm instance presets

dlm instance create \
  --name demo \
  --depot-preset "Dublin Port" \
  --stop-preset "Trinity College Dublin" \
  --stop-preset "UCD Belfield" \
  --stop-latlon "53.3390,-6.2600,Rathmines customer" \
  --vehicles 1 \
  --output data/instances/demo.json

dlm instance random \
  --name random20 --depot-preset "Dublin Port" --n 20 --seed 42 \
  --output data/instances/random20.json

dlm instance show data/instances/small-n8.json
dlm instance map data/instances/small-n8.json --output results/small-map.html
dlm scenario validate scenarios/oconnell_march.yaml

dlm plan --instance data/instances/small-n8.json --output results/plan.json
dlm compare \
  --instance data/instances/small-n8.json \
  --scenario scenarios/oconnell_march.yaml \
  --information-model reactive \
  --output-dir results/comparison

dlm batch --random-runs 64 --random-edges 3 --jobs 4
dlm figures
```

The CLI accepts address, preset, coordinate, and seeded-random inputs. Map click, stop deletion,
renaming, moving, and drawn GeoJSON are public builder/schema APIs exposed interactively by the
app; their deterministic JSON/YAML files can then be passed back to all CLI commands. This is a
file-based workflow rather than hidden UI-only scientific state.

## Outputs and exit behaviour

- `network` commands print JSON including cache status, time, counts, SCC, length, and speed
  provenance.
- `plan` writes/prints complete time and distance breakdowns.
- `compare` writes replayable `config.yaml`, `result.json`, `comparison.html`,
  `comparison.png`, and `comparison.svg`.
- `batch` writes a tidy CSV plus `statistics.json`; `figures` writes PNG and SVG.
- Validation problems exit non-zero with a readable message. Unreachable delivery service is a
  valid structured experiment outcome, not a process crash.
