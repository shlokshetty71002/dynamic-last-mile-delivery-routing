"""Command-line interface for every scientific capability exposed by the UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from dlm import __version__
from dlm.config import configure_logging, get_settings
from dlm.disruption.generators import random_edge_closure
from dlm.disruption.schema import Scenario
from dlm.instance.builder import InstanceBuilder
from dlm.instance.geocode import CachedGeocoder
from dlm.instance.presets import load_presets
from dlm.instance.schema import DeliveryInstance
from dlm.network.loader import NetworkBuildError, NetworkSpec, build_or_load_network
from dlm.simulation import BatchCase, InformationModel, run_batch, summarise_savings
from dlm.simulation.batch import load_rows, write_summary
from dlm.viz import (
    case_comparison_figure,
    comparison_map,
    instance_map,
    save_map,
    saving_vs_stops_figure,
)
from dlm.workflows import compare_delivery, plan_delivery, resolve_instance

app = typer.Typer(
    name="dlm",
    help="Disruption-aware last-mile routing on Dublin's real road network.",
    no_args_is_help=True,
)
network_app = typer.Typer(help="Build and inspect the cached M50 driving network.")
instance_app = typer.Typer(help="Create, inspect, and map dynamic delivery instances.")
scenario_app = typer.Typer(help="Validate and inspect reproducible disruption scenarios.")
app.add_typer(network_app, name="network")
app.add_typer(instance_app, name="instance")
app.add_typer(scenario_app, name="scenario")


def version_callback(value: bool) -> None:
    """Print the package version and exit."""

    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show the package version and exit.",
    ),
) -> None:
    """Initialise validated configuration and structured logging."""

    del version
    configure_logging()


@app.command("config")
def show_config() -> None:
    """Print effective non-secret configuration as JSON."""

    settings = get_settings()
    payload = {
        "cache_dir": str(settings.resolved_cache_dir),
        "distance_unit": settings.distance_unit,
        "global_seed": settings.global_seed,
        "log_level": settings.log_level,
        "max_snap_distance_m": settings.max_snap_distance_m,
        "project_root": str(settings.project_root),
        "results_dir": str(settings.resolved_results_dir),
        "time_unit": settings.time_unit,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@network_app.command("build")
def network_build(
    force: Annotated[bool, typer.Option("--force", help="Ignore a matching cache.")] = False,
    place: Annotated[
        str | None,
        typer.Option("--place", help="Optional place query; M50 bbox is the fallback."),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option("--cache-dir", help="Override the configured GraphML cache."),
    ] = None,
) -> None:
    """Build or load the directed, strongly connected M50 driving graph."""

    result = _network_result(place=place, cache_dir=cache_dir, force=force)
    _echo_network_result(result)


@network_app.command("stats")
def network_statistics(
    cache_dir: Annotated[
        Path | None,
        typer.Option("--cache-dir", help="Override the configured GraphML cache."),
    ] = None,
) -> None:
    """Print connectivity, length, and speed-provenance statistics."""

    _echo_network_result(_network_result(place=None, cache_dir=cache_dir, force=False))


@instance_app.command("presets")
def instance_presets() -> None:
    """List the curated Dublin location catalogue."""

    payload = [
        {
            "name": preset.name,
            "category": preset.category,
            "lat": preset.lat,
            "lon": preset.lon,
        }
        for preset in load_presets().values()
    ]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@instance_app.command("create")
def instance_create(
    name: Annotated[str, typer.Option("--name", help="Stable instance name.")],
    depot_preset: Annotated[
        str, typer.Option("--depot-preset", help="Required curated depot name.")
    ],
    stop_preset: Annotated[
        list[str] | None,
        typer.Option("--stop-preset", help="Repeat for each curated delivery stop."),
    ] = None,
    stop_latlon: Annotated[
        list[str] | None,
        typer.Option("--stop-latlon", help="Repeat as 'lat,lon,label'."),
    ] = None,
    stop_address: Annotated[
        list[str] | None,
        typer.Option("--stop-address", help="Repeat for address input; ambiguous results fail."),
    ] = None,
    fleet_size: Annotated[int, typer.Option("--vehicles", min=1)] = 1,
    capacity: Annotated[float | None, typer.Option("--capacity", min=0.001)] = None,
    output: Annotated[Path, typer.Option("--output")] = Path("data/instances/instance.json"),
) -> None:
    """Create and save an instance from presets, coordinates, and/or addresses."""

    graph = _graph()
    settings = get_settings()
    builder = InstanceBuilder(
        graph,
        name=name,
        seed=settings.global_seed,
        max_snap_distance_m=settings.max_snap_distance_m,
        geocoder=CachedGeocoder(settings.resolved_cache_dir / "geocoding"),
    )
    builder.set_depot_from_preset(depot_preset)
    for preset in stop_preset or []:
        builder.add_stop_from_preset(preset)
    for raw in stop_latlon or []:
        lat, lon, label = _parse_latlon(raw)
        builder.add_stop_from_latlon(lat, lon, label=label)
    for address in stop_address or []:
        builder.add_stop_from_address(address)
    builder.fleet_size = fleet_size
    builder.vehicle_capacity = capacity
    instance = builder.build()
    instance.save(output)
    typer.echo(json.dumps(_instance_summary(instance, output), indent=2, sort_keys=True))


@instance_app.command("random")
def instance_random(
    name: Annotated[str, typer.Option("--name")],
    depot_preset: Annotated[str, typer.Option("--depot-preset")],
    n: Annotated[int, typer.Option("--n", min=1, max=50)],
    seed: Annotated[int, typer.Option("--seed", min=0)] = 42,
    output: Annotated[Path, typer.Option("--output")] = Path("data/instances/random.json"),
) -> None:
    """Create a seeded random-stop instance on the cached road graph."""

    graph = _graph()
    builder = InstanceBuilder(graph, name=name, seed=seed)
    builder.set_depot_from_preset(depot_preset)
    builder.add_random_stops(n, seed=seed)
    instance = builder.build()
    instance.save(output)
    typer.echo(json.dumps(_instance_summary(instance, output), indent=2, sort_keys=True))


@instance_app.command("show")
def instance_show(path: Path) -> None:
    """Validate and print a saved instance."""

    instance = DeliveryInstance.load(path)
    typer.echo(json.dumps(instance.model_dump(mode="json"), indent=2, sort_keys=True))


@instance_app.command("map")
def instance_map_command(
    path: Path,
    output: Annotated[Path, typer.Option("--output")] = Path("results/instance-map.html"),
) -> None:
    """Write a standalone map of a saved depot and its dynamic stops."""

    save_map(instance_map(DeliveryInstance.load(path)), output)
    typer.echo(str(output))


@scenario_app.command("validate")
def scenario_validate(path: Path) -> None:
    """Validate and print one YAML disruption scenario."""

    scenario = Scenario.load(path)
    typer.echo(scenario.to_yaml())


@app.command("plan")
def plan(
    instance_path: Annotated[Path, typer.Option("--instance")],
    output: Annotated[Path, typer.Option("--output")] = Path("results/plan.json"),
) -> None:
    """Solve a baseline route and write its complete cost breakdown."""

    instance = DeliveryInstance.load(instance_path)
    solution = plan_delivery(_graph(), instance, matrix_cache_dir=get_settings().resolved_cache_dir)
    payload = {
        "instance": instance.name,
        "solver": solution.solver,
        "total_time_s": solution.total_time_s,
        "driving_time_s": solution.total_driving_time_s,
        "service_time_s": solution.total_service_time_s,
        "distance_m": solution.total_distance_m,
        "routes": [
            {
                "vehicle": route.vehicle_id,
                "order": route.order,
                "time_s": route.total_time_s,
                "distance_m": route.distance_m,
                "load": route.load,
            }
            for route in solution.routes
        ],
        "meta": solution.meta,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("compare")
def compare(
    instance_path: Annotated[Path, typer.Option("--instance")],
    scenario_path: Annotated[Path, typer.Option("--scenario")],
    information_model: Annotated[
        InformationModel, typer.Option("--information-model")
    ] = InformationModel.REACTIVE,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("results/comparison"),
) -> None:
    """Run T1/T2/T3/T3-oracle and write JSON, map, and report figures."""

    graph = _graph()
    instance = DeliveryInstance.load(instance_path)
    scenario = Scenario.load(scenario_path)
    result = compare_delivery(
        graph,
        instance,
        scenario,
        information_model=information_model,
        matrix_cache_dir=get_settings().resolved_cache_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    save_map(comparison_map(graph, instance, result, scenario), output_dir / "comparison.html")
    case_comparison_figure(result, output_dir / "comparison")
    typer.echo(json.dumps(result.summary_row(), indent=2, sort_keys=True))


@app.command("batch")
def batch(
    instance_dir: Annotated[Path, typer.Option("--instances")] = Path("data/instances"),
    scenario_dir: Annotated[Path, typer.Option("--scenarios")] = Path("scenarios"),
    random_runs: Annotated[int, typer.Option("--random-runs", min=0)] = 0,
    random_edges: Annotated[int, typer.Option("--random-edges", min=1)] = 3,
    output: Annotated[Path, typer.Option("--output")] = Path("results/batch/summary.csv"),
    jobs: Annotated[int, typer.Option("--jobs", min=1)] = 1,
) -> None:
    """Run all committed instance/scenario pairs plus optional seeded random closures."""

    graph = _graph()
    instances = [
        resolve_instance(graph, DeliveryInstance.load(path))
        for path in sorted(instance_dir.glob("*.json"))
    ]
    scenarios = [Scenario.load(path) for path in sorted(scenario_dir.glob("*.yaml"))]
    if not instances or not scenarios:
        raise typer.BadParameter("Instance and scenario directories must both contain files")
    cases = [BatchCase(instance, scenario) for instance in instances for scenario in scenarios]
    for instance in instances:
        for seed in range(random_runs):
            cases.append(
                BatchCase(
                    instance,
                    random_edge_closure(
                        graph,
                        n_edges=random_edges,
                        seed=seed,
                        name=f"random_{random_edges}_seed_{seed}",
                    ),
                )
            )
    rows = run_batch(graph, cases, output, jobs=jobs)
    summary_path = output.with_name("statistics.json")
    write_summary(summary_path, summarise_savings(rows))
    typer.echo(json.dumps({"runs": len(rows), "csv": str(output), "summary": str(summary_path)}))


@app.command("figures")
def figures(
    csv_path: Annotated[Path, typer.Option("--csv")] = Path("results/batch/summary.csv"),
    output_base: Annotated[Path, typer.Option("--output")] = Path(
        "docs/report/figures/saving-vs-stops"
    ),
) -> None:
    """Regenerate report figures from tidy batch results."""

    png, svg = saving_vs_stops_figure(load_rows(csv_path), output_base)
    typer.echo(json.dumps({"png": str(png), "svg": str(svg)}))


def _graph():
    return _network_result(place=None, cache_dir=None, force=False).graph


def _network_result(*, place: str | None, cache_dir: Path | None, force: bool):
    spec = NetworkSpec(
        area_name="m50_catchment" if place is None else f"place:{place}", place_query=place
    )
    try:
        return build_or_load_network(spec, cache_dir=cache_dir, force_rebuild=force)
    except NetworkBuildError as exc:
        typer.echo(f"Network build failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _echo_network_result(result) -> None:
    typer.echo(
        json.dumps(
            {
                "cache_hit": result.cache_hit,
                "cache_path": str(result.cache_path),
                "elapsed_seconds": round(result.elapsed_seconds, 3),
                **result.stats.as_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )


def _parse_latlon(raw: str) -> tuple[float, float, str]:
    parts = [part.strip() for part in raw.split(",", maxsplit=2)]
    if len(parts) < 2:
        raise typer.BadParameter("--stop-latlon must be 'lat,lon' or 'lat,lon,label'")
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise typer.BadParameter("Latitude and longitude must be numeric") from exc
    return lat, lon, parts[2] if len(parts) == 3 else f"Stop at {lat:.5f},{lon:.5f}"


def _instance_summary(instance: DeliveryInstance, path: Path) -> dict[str, object]:
    return {
        "name": instance.name,
        "n_stops": instance.n_stops,
        "fleet_size": instance.fleet_size,
        "path": str(path),
        "hash": instance.content_hash(),
    }


if __name__ == "__main__":
    app()
