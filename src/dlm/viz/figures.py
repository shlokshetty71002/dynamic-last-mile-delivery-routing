"""Colourblind-safe, deterministic report figures in PNG and SVG formats."""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from dlm.simulation.batch import bootstrap_mean_ci
from dlm.simulation.metrics import ExperimentResult
from dlm.viz.folium_map import VisualisationDependencyError

COLOURS = ("#0072B2", "#E69F00", "#009E73", "#CC79A7")


def case_comparison_figure(result: ExperimentResult, output_base: str | Path) -> tuple[Path, Path]:
    """Plot T1/T2/T3/T3-oracle time and routed-distance comparisons."""

    plt = _pyplot()
    labels = ["T1\nplanned", "T2\nfrozen", "T3\nreplanned", "T3 oracle"]
    times = [result.t1_s, result.t2_s, result.t3_s, result.t3_oracle_s]
    distances = [
        result.t1_environment.distance_km,
        result.t2_environment.distance_km,
        result.t3_environment.distance_km,
        None if result.t3_oracle_environment is None else result.t3_oracle_environment.distance_km,
    ]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5), constrained_layout=True)
    for axis, values, title, unit in (
        (axes[0], times, "Route cost", "Time (seconds)"),
        (axes[1], distances, "Routed distance", "Distance (km)"),
    ):
        plotted = [float("nan") if value is None else value for value in values]
        axis.bar(labels, plotted, color=COLOURS)
        axis.set_title(title)
        axis.set_ylabel(unit)
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle(f"{result.instance_name} — {result.scenario_name}")
    return _save_both(figure, output_base)


def saving_vs_stops_figure(
    rows: list[dict[str, object]], output_base: str | Path
) -> tuple[Path, Path]:
    """Plot mean saving and seeded 95% bootstrap intervals against dynamic stop count."""

    plt = _pyplot()
    grouped: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        saving = row.get("saving_percent")
        n_stops = row.get("n_stops")
        if isinstance(saving, int | float) and isinstance(n_stops, int | float):
            grouped[int(n_stops)].append(float(saving))
    if not grouped:
        raise ValueError("No finite saving_percent/n_stops rows are available")
    x = sorted(grouped)
    means = [statistics.fmean(grouped[value]) for value in x]
    intervals = [bootstrap_mean_ci(grouped[value], samples=2000, seed=42) for value in x]
    lower = [mean - interval[0] for mean, interval in zip(means, intervals, strict=True)]
    upper = [interval[1] - mean for mean, interval in zip(means, intervals, strict=True)]
    figure, axis = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    axis.errorbar(x, means, yerr=[lower, upper], marker="o", color=COLOURS[0], capsize=4)
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_xlabel("Number of delivery stops (N)")
    axis.set_ylabel("Saving (%)")
    axis.set_title("Re-optimisation saving versus instance size")
    axis.grid(alpha=0.25)
    return _save_both(figure, output_base)


def _save_both(figure: Any, output_base: str | Path) -> tuple[Path, Path]:
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    png = base.with_suffix(".png")
    svg = base.with_suffix(".svg")
    figure.savefig(png, dpi=180, metadata={"Software": "dynamic-last-mile-delivery-routing"})
    figure.savefig(svg, metadata={"Creator": "dynamic-last-mile-delivery-routing"})
    return png, svg


def _pyplot():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise VisualisationDependencyError(
            "Matplotlib is unavailable; install the project visualisation dependencies"
        ) from exc
    plt.rcParams.update(
        {
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 10,
            "figure.dpi": 120,
        }
    )
    return plt
