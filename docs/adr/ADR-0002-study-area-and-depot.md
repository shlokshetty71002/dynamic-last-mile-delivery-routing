# ADR-0002 — M50 study envelope and explicit depot

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision owners:** Project authors

## Context

The study area controls download size and which user locations are valid. A hidden default depot
would make demos faster but would weaken the requirement that a delivery instance is user-defined.

## Decision

Use explicit WGS84 bbox `(-6.50, 53.20, -6.05, 53.47)` as the reproducible M50-catchment
envelope. It is a rectangle, not a claim about the legal/physical M50 boundary. Require the user
to choose the depot on every run using the same address, coordinate, preset, or map-click paths as
delivery stops. No default depot is silently inserted.

## Consequences

Locations across the urban/suburban Dublin catchment are supported at the cost of a larger first
download and matrix paths. Canonical demos name Dublin Port as their selected depot, but the
software does not treat it as a universal default.
