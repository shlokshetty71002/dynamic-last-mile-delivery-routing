# Stage 00 — Foundations

## Goal

Provide an installable, testable, documented Python project with deterministic configuration and
continuous integration before domain features depend on it.

## Scope

In scope: src-layout packaging, settings, logs, pinned dependencies, Make targets, pytest, Ruff,
pre-commit, CI, docs skeleton, and module boundaries. Routing behaviour begins at Stage 1.

## Design

Python 3.11/3.12 is packaged with Hatchling. `DLM_*` Pydantic settings centralise paths, seed,
snap guard, and SI units. JSON logs use the standard library. Ruff owns lint/format; pytest owns
behaviour. [ADR-0001](../adr/ADR-0001-tech-stack.md) records alternatives.

## Interfaces

- `Settings` — validated environment configuration.
- `get_settings() -> Settings` — process-cached settings.
- `configure_logging(settings=None) -> None` — deterministic JSON log setup.
- `dlm config`, `dlm --version` — inspect the installed program.

## Data & assumptions

Default seed is 42; internal time is seconds and distance is metres. Cache and result paths are
repository-relative and ignored. No secret or absolute author-machine path is committed.

## How to run

```bash
make setup
make ci
.venv/bin/dlm config
```

Windows equivalents are in [the PowerShell guide](../WINDOWS_RUN_AND_GIT_GUIDE.md).

## Acceptance criteria

- ✅ Clean environment install is encoded in `make setup` and both CI matrix jobs.
- ✅ Ruff lint/format, pytest, and `pip check` form `make ci`.
- ✅ CI workflow targets Python 3.11 and 3.12 and smoke-tests CLI/Streamlit entry points.
- ✅ Repository map, ADR, documentation contract, `.env.example`, and pre-commit are present.

## Results / evidence

Local final gate on 2026-08-16: 59 tests passed; Ruff check passed; 73 Python files were already
formatted; `pip check` reported no broken requirements. Remote run links are recorded on the PR.

## Known limitations

Pinned dependencies improve repeatability but do not freeze the external OSM database. GNU Make
is optional; Windows uses explicit Python/entry-point commands.

## Next

Stage 1 consumes paths, dependency pins, logs, and tests to build the cached real network.
