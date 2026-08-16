# Documentation map

The repository is the executable evidence for the model. Generated results are not committed as
facts: source, inputs, seeds, assumptions, and commands are committed so evidence can be rebuilt.

## Start here

- [Architecture](architecture.md) — real data flow, module boundaries, and cache ownership.
- [Mathematical model](modelling.md) — objective, constraints, T1/T2/T3, information models.
- [Data and provenance](data.md) — OSM, M50 envelope, speeds, presets, scenarios, sustainability.
- [Limitations](limitations.md) — what the model does not establish.
- [CLI reference](cli.md) — every headless capability and its UI equivalent.
- [Windows run and Git guide](WINDOWS_RUN_AND_GIT_GUIDE.md) — clean-clone setup through push.
- [Glossary](glossary.md) — notation and project terms.
- [Architecture decisions](adr/) — choices and trade-offs.
- [Stage evidence](stages/) — design, interfaces, acceptance tests, and next dependency per stage.
- [Scenario schema](../scenarios/README.md) — copyable YAML and geometry rules.

## Reproduction order

1. `make setup` creates and installs the pinned environment.
2. `make ci` runs static checks, 59 deterministic tests, and dependency integrity checks.
3. `dlm network build` downloads the real Dublin graph once and writes a hashed cache.
4. `make experiment` executes 204 deterministic real-network cases.
5. `make figures` derives the report figure from the tidy CSV.
6. `make app` opens the same workflows through Streamlit.

`make reproduce` executes steps 2–5 after regenerating the canonical instance JSON. The real
network remains external, time-varying source data; cache metadata records access time and the
exact build specification.
