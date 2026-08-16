# Stage 04 — Baseline solver and T1

## Goal

Construct an explainable delivery route for any validated instance and report its normal-condition
time, distance, service, order, legs, and full road path.

## Scope

In scope: solver protocol, nearest neighbour, directed full-cost 2-opt/relocate, route expansion,
degenerate sizes, T1, and baseline plan CLI. Disruption execution begins in Stage 6.

## Design

Nearest neighbour provides a transparent deterministic start. Local search evaluates every
complete directed candidate, avoiding invalid symmetric 2-opt deltas, and accepts only strict
improvements. Iterations are capped and the improvement trajectory is stored.

## Interfaces

- `Solver.solve(instance, matrix) -> Solution` — shared solver contract.
- `NearestNeighbourSolver`, `DirectedLocalSearchSolver` — primary K=1 pipeline.
- `RouteLeg`, `VehicleRoute`, `Solution` — complete orders, costs, paths, load, metadata.
- `plan_delivery(...) -> Solution`, `dlm plan` — shared use case and CLI.

## Data & assumptions

Objective is drive seconds plus service seconds. Distance is reported but not separately weighted.
Uniform default service is 180 seconds. No lateness penalty. Tie-breaking follows stable point IDs.

## How to run

```bash
dlm plan --instance data/instances/small-n8.json --output results/small-plan.json
```

## Acceptance criteria

- ✅ Known-optimum fixture is found by NN plus improvement.
- ✅ Improvement trajectory is monotone; no accepted move increases directed cost.
- ✅ N=1, N=2, and larger dynamic sizes return valid depot-closed routes.
- ✅ Plan JSON separates drive, service, distance, per-vehicle order/load, and solver metadata.
- ✅ Equal input/matrix produces byte-stable numeric output.

## Results / evidence

`tests/test_solvers.py` includes exact fixture costs, route coverage, monotonicity, and degenerate
sizes. Real street geometry is written by `dlm compare` and inspected in live acceptance output.

## Known limitations

Heuristics do not certify global optimality. Nearest-neighbour is sensitive to early ties; local
search can stop in a local optimum. Uniform service does not affect order.

## Next

Stage 5 defines reproducible changes to the graph against which the baseline can be executed.
