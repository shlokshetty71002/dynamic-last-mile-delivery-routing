"""Regenerate the committed coordinate-only small/medium/large report instances."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dlm.instance.presets import get_preset, load_presets
from dlm.instance.schema import DeliveryInstance, Depot, LocationSource, Stop

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "instances"
DEPOT_NAME = "Dublin Port"
CREATED_AT = datetime(2026, 8, 16, tzinfo=UTC)
SMALL_NAMES = [
    "UCD Belfield",
    "Trinity College Dublin",
    "Mater Misericordiae University Hospital",
    "Heuston Station",
    "Dundrum Town Centre",
    "St Vincent's University Hospital",
    "Connolly Station",
    "O'Connell Street GPO",
]


def build_instance(name: str, location_names: list[str]) -> DeliveryInstance:
    """Build one explicit-depot, coordinate-only instance for later graph snapping."""

    depot_preset = get_preset(DEPOT_NAME)
    stops = []
    for number, location_name in enumerate(location_names, start=1):
        preset = get_preset(location_name)
        stops.append(
            Stop(
                id=f"s{number}",
                label=preset.name,
                lat=preset.lat,
                lon=preset.lon,
                node=None,
                demand=1.0,
                service_time_s=180.0,
                source=LocationSource.PRESET,
            )
        )
    return DeliveryInstance(
        name=name,
        depot=Depot(
            label=depot_preset.name,
            lat=depot_preset.lat,
            lon=depot_preset.lon,
            node=None,
            source=LocationSource.PRESET,
        ),
        stops=tuple(stops),
        fleet_size=1,
        seed=42,
        created_at=CREATED_AT,
    )


def main() -> None:
    """Write N=8, N=20, and N=40 named-location instances deterministically."""

    available = [
        preset.name
        for preset in load_presets().values()
        if preset.name not in {DEPOT_NAME, *SMALL_NAMES}
    ]
    medium_names = [*SMALL_NAMES, *available[:12]]
    large_names = [*SMALL_NAMES, *available[:32]]
    definitions = {
        "small-n8": SMALL_NAMES,
        "medium-n20": medium_names,
        "large-n40": large_names,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, locations in definitions.items():
        build_instance(name, locations).save(OUTPUT / f"{name}.json")


if __name__ == "__main__":
    main()
