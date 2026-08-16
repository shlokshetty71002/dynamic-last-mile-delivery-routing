# Stage 07 — Experiment harness and report results

## Goal

Replace an anecdotal comparison with deterministic batch rows, uncertainty summaries, sensitivity
to dynamic stop count, and regenerable report figures.

## Scope

In scope: case sweep, parallel execution, seeded random closures, tidy CSV, mean/median/IQR,
bootstrap CI, help/neutral/hurt fractions, runtime telemetry, PNG/SVG figures. Interpretation
beyond sampled scenarios is out of scope.

## Design

Cases are instance×scenario plus 64 seeded random scenarios for each canonical size: `3×(4+64)
=204` runs. Results sort by stable names before writing. A seeded percentile bootstrap samples
finite saving values 2,000 times. Wall time is stored separately because it is not deterministic.

## Interfaces

- `BatchCase`, `run_batch(graph, cases, output_csv, jobs=1)`.
- `summarise_savings(rows, group_by="scenario_name", ...)`.
- `bootstrap_mean_ci(values, samples=2000, seed=42)`.
- `saving_vs_stops_figure`, `case_comparison_figure`.
- `dlm batch`, `dlm figures`, `make experiment`, `make figures`.

## Data & assumptions

Random scenarios close three uniformly sampled sorted directed edges per seed. Only finite saving
percentages enter percentage summaries; raw infeasible cases stay in CSV. Tolerance ±1e-9 defines
neutral. Figures use a colourblind-safe palette and include SVG.

## How to run

```bash
make experiment
make figures
# Or everything, including tests and canonical-instance regeneration:
make reproduce
```

## Acceptance criteria

- ✅ Default Make target specifies exactly 204 runs.
- ✅ Batch order/output and random generator are seed-deterministic.
- ✅ Mean, median, IQR, 95% bootstrap CI, and fractions have controlled tests.
- ✅ N=8/20/40 provides the stop-count sensitivity axis.
- ✅ PNG and vector SVG derive from the tidy CSV.

## Results / evidence

Generated evidence belongs in `results/batch/summary.csv`, `statistics.json`, and
`docs/report/figures/saving-vs-stops.{png,svg}`. Numerical claims must be copied from those files
after the same live graph run; this document deliberately does not fabricate headline values.

## Known limitations

Random-edge sampling is not an empirical Dublin incident distribution. Parallel wall times depend
on cache contention and hardware. Three canonical N values do not establish a smooth causal law.

## Next

Stage 8 generalises one route to user-selected fleet/capacity and compares a solver benchmark.
