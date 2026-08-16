# ADR-0003 — Time objective, service assumption, and reactive headline

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision owners:** Project authors

## Context

T2 is undefined without saying when a driver learns about a disruption. The objective also needs
an explicit service-time treatment so route and report totals agree.

## Decision

Minimise travel seconds and report fixed service seconds in total operational time. Use 180
seconds per delivery as a configurable model assumption. Use `reactive` as the headline
information model: follow the planned edge path until a blocked edge is encountered. Replan once
at first discovery. Also implement `omniscient` frozen-order T2 and full-information-from-time-zero
`T3_oracle` as distinct comparisons.

## Alternatives considered

- Pure distance: rejected because road class and speed are central to disruption delay.
- Lateness penalties: deferred because no evidence-backed window/penalty data is supplied.
- Continuous replanning: deferred to keep the intervention interpretable and reproducible.

## Consequences

The headline reflects information latency and sunk travel. Service time does not change route
order when uniform, but remains in T1/T2/T3 and in every run configuration.
