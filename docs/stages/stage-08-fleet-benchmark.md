# Stage 08 — Fleet, capacity, and solver benchmark

## Goal

Support runtime fleet size `K`, enforce homogeneous vehicle capacity, replan affected routes, and
compare the explainable heuristic with an interchangeable OR-Tools routing adapter.

## Scope

In scope: directed Clarke-Wright, capacity, multi-route solution, K guards, K=1 compatibility,
OR-Tools adapter, fleet experiments. Time-window optimisation and heterogeneous fleets are deferred.

## Design

Clarke-Wright begins with one depot-customer-depot route per stop, ranks directed savings, and
merges endpoint-compatible routes when capacity and fleet targets permit. K=1 delegates to the
baseline pipeline exactly. OR-Tools receives the same integer travel-time matrix and schema.

## Interfaces

- `ClarkeWrightSolver.solve(instance, matrix) -> Solution`.
- `ORToolsSolver.solve(instance, matrix) -> Solution`.
- `default_solver(fleet_size) -> Solver` — baseline for K=1, Clarke-Wright otherwise.
- `VehicleRoute.load`, route coverage and capacity helpers.

## Data & assumptions

All vehicles share capacity; stop demand is non-negative. `K≤N`, individual demand may not exceed
capacity, and every stop is served once. OR-Tools uses a deterministic bounded search configuration.

## How to run

Create an instance with `--vehicles 3 --capacity VALUE`, then use the unchanged commands:

```bash
dlm plan --instance data/instances/fleet.json --output results/fleet-plan.json
dlm compare --instance data/instances/fleet.json \
  --scenario scenarios/quays_bridge_closure.yaml --output-dir results/fleet-compare
```

## Acceptance criteria

- ✅ K=1 route/order/cost remains the Stage 4 result.
- ✅ Tests verify exact coverage, route count, load, and no capacity violation.
- ✅ OR-Tools adapter imports and solves through the same protocol.
- ✅ Multi-vehicle experiment uses the unchanged disruption/metrics workflow.

## Results / evidence

`tests/test_solvers.py` executes primary and OR-Tools solvers on the known fixture and capacity
cases. Real quality gaps and wall times should be exported from a fixed graph/instance benchmark,
not generalised from the fixture.

## Known limitations

OR-Tools may return a high-quality feasible route without proving optimality within its time limit.
There are no vehicle skills, shifts, heterogeneous costs/capacities, or split deliveries.

## Next

Stage 9 audits reproducibility, the complete CLI surface, and clean-clone quality gates.
