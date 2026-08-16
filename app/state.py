"""Streamlit session-state initialisation; no routing or modelling logic lives here."""

from __future__ import annotations

from typing import Any


def initialise_state(state: Any, *, builder: Any) -> None:
    """Create the small set of UI state keys exactly once per browser session."""

    defaults = {
        "builder": builder,
        "scenario": None,
        "result": None,
        "last_error": None,
        "demo_candidates_evaluated": None,
    }
    for key, value in defaults.items():
        if key not in state:
            state[key] = value


def reset_run_state(state: Any) -> None:
    """Discard only derived scenario/result state after an instance edit."""

    state["result"] = None
    state["last_error"] = None
    state["demo_candidates_evaluated"] = None
