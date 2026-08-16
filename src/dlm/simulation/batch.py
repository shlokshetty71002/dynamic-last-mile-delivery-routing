"""Deterministic batch execution, tidy CSV output, and bootstrap summaries."""

from __future__ import annotations

import csv
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np

from dlm.disruption.schema import Scenario
from dlm.instance.schema import DeliveryInstance
from dlm.simulation.metrics import Experiment


@dataclass(frozen=True)
class BatchCase:
    """One instance/scenario pair in a reproducible experiment sweep."""

    instance: DeliveryInstance
    scenario: Scenario


def run_batch(
    graph: nx.MultiDiGraph,
    cases: list[BatchCase],
    output_csv: str | Path,
    *,
    jobs: int = 1,
) -> list[dict[str, object]]:
    """Run cases, measure wall time separately, and write a deterministic tidy CSV."""

    def run_one(case: BatchCase) -> dict[str, object]:
        started = time.perf_counter()
        result = Experiment(graph, case.instance, case.scenario).run()
        row = result.summary_row()
        row["wall_time_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return row

    if jobs <= 1:
        rows = [run_one(case) for case in cases]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            rows = list(executor.map(run_one, cases))
    rows.sort(key=lambda row: (str(row["instance_name"]), str(row["scenario_name"])))
    destination = Path(output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})
    return rows


def load_rows(path: str | Path) -> list[dict[str, object]]:
    """Load a batch CSV while recovering numeric, boolean, list, and null values."""

    with Path(path).open(encoding="utf-8", newline="") as stream:
        return [
            {key: _parse_value(value) for key, value in row.items()}
            for row in csv.DictReader(stream)
        ]


def summarise_savings(
    rows: list[dict[str, object]],
    *,
    group_by: str = "scenario_name",
    bootstrap_samples: int = 2000,
    seed: int = 42,
) -> list[dict[str, object]]:
    """Return mean, median, IQR, bootstrap CI, and helped/neutral/hurt fractions."""

    groups: dict[str, list[float]] = {}
    for row in rows:
        value = row.get("saving_percent")
        if isinstance(value, int | float) and math.isfinite(float(value)):
            groups.setdefault(str(row[group_by]), []).append(float(value))
    summaries = []
    for group, values in sorted(groups.items()):
        low, high = bootstrap_mean_ci(values, samples=bootstrap_samples, seed=seed)
        quartiles = np.percentile(values, [25, 75])
        count = len(values)
        summaries.append(
            {
                group_by: group,
                "runs": count,
                "mean_saving_percent": round(statistics.fmean(values), 6),
                "median_saving_percent": round(statistics.median(values), 6),
                "iqr_saving_percent": round(float(quartiles[1] - quartiles[0]), 6),
                "bootstrap_ci_low": round(low, 6),
                "bootstrap_ci_high": round(high, 6),
                "helped_fraction": round(sum(value > 1e-9 for value in values) / count, 6),
                "neutral_fraction": round(sum(abs(value) <= 1e-9 for value in values) / count, 6),
                "hurt_fraction": round(sum(value < -1e-9 for value in values) / count, 6),
            }
        )
    return summaries


def bootstrap_mean_ci(
    values: list[float], *, samples: int = 2000, seed: int = 42
) -> tuple[float, float]:
    """Return a seeded percentile 95% bootstrap confidence interval for the mean."""

    if not values:
        raise ValueError("At least one finite saving value is required")
    if samples < 100:
        raise ValueError("Use at least 100 bootstrap samples")
    generator = np.random.default_rng(seed)
    data = np.asarray(values, dtype=float)
    draws = generator.choice(data, size=(samples, len(data)), replace=True).mean(axis=1)
    low, high = np.percentile(draws, [2.5, 97.5])
    return float(low), float(high)


def write_summary(path: str | Path, summaries: list[dict[str, object]]) -> Path:
    """Write deterministic aggregate statistics as JSON."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summaries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def _csv_value(value: object) -> object:
    if isinstance(value, tuple | list | dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def _parse_value(value: str) -> object:
    if value == "":
        return None
    if value in {"True", "False"}:
        return value == "True"
    if value.startswith(("[", "{")):
        return json.loads(value)
    try:
        return float(value) if any(character in value for character in ".eE") else int(value)
    except ValueError:
        return value
