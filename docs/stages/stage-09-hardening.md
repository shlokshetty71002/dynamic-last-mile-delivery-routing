# Stage 09 — Hardening and reproducibility

## Goal

Make the full scientific pipeline testable and driveable from a clean command line before relying
on the user interface.

## Scope

In scope: end-to-end fixture tests, lockfile, full CLI, shared workflows, deterministic output,
clean reproduction target, docs/limitations, CI matrix, live-network acceptance, and secret/path
audit. Hosting and production operations are out of scope.

## Design

Normal CI uses a hand-built directed road graph so third-party uptime cannot cause false failures.
A manual workflow separately downloads the live graph, proves a cache hit/SCC, runs N=8 T1/T2/T3,
checks no-regret, and uploads evidence. `requirements.txt` contains transitive pins.

## Interfaces

- `plan_delivery`, `compare_delivery`, `resolve_instance` — interface-independent use cases.
- `make ci`, `make experiment`, `make figures`, `make reproduce` — stable operator targets.
- [CLI reference](../cli.md) — command/UI capability mapping.
- `.github/workflows/ci.yml`, `live-network-acceptance.yml` — deterministic and external gates.

## Data & assumptions

Same configuration and graph cache yield byte-identical scientific outputs. Wall-clock timing and
fresh OSM snapshots are explicitly variable. Generated caches/results and secrets are ignored.

## How to run

```bash
make setup
make reproduce
git diff --check
```

## Acceptance criteria

- ✅ End-to-end tests build instance→matrix→plan→disrupt→execute→replan→metrics.
- ✅ 59-test suite, Ruff, format, and `pip check` pass locally.
- ✅ CLI covers network, locations, scenarios, planning, comparison, batch, and figures.
- ✅ Canonical files regenerate deterministically; no absolute paths/secrets are committed.
- ✅ CI tests Python 3.11/3.12; live external evidence is a separate manual workflow.

## Results / evidence

Final local gate on 2026-08-16: 60 passed; all Ruff checks passed; 73 Python files formatted;
dependency integrity passed. Remote workflow links belong on the draft PR after publication.

## Known limitations

`make reproduce` requires a usable current/matching cached OSM graph and can be computationally
expensive. Exact fresh-graph byte identity is impossible for a living upstream database.

## Next

Stage 10 exposes the already-tested workflows as a deliberately barebones interactive client.
