# ADR-0004 — Operational no-regret replanning

- **Status:** Accepted
- **Date:** 2026-08-16

## Context

Nearest-neighbour/local search is heuristic. A candidate replan can occasionally be worse than
keeping the frozen order even though the disrupted graph is known at discovery. Reporting such a
candidate as the operational decision would violate the intended meaning of a useful re-routing
system and the `T3≤T2` acceptance invariant.

## Decision

At disruption discovery, compute both the frozen remaining detour and candidate reordered plan.
Adopt the candidate only when its complete directed cost is no greater; otherwise preserve the
frozen detour and set `fallback_used=true`. Assert finite `T3≤T2` in the experiment layer.

## Consequences

Saving is never negative for the deployed policy. Researchers can identify heuristic fallback
frequency explicitly. This is a policy comparison, not evidence that unconstrained local search
dominates a fixed sequence in every instance.
