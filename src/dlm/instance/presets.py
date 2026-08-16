"""Curated, versioned Dublin location presets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class PresetError(ValueError):
    """Raised when the preset catalogue is invalid or a name is unknown."""


@dataclass(frozen=True)
class DublinPreset:
    """Recognisable Dublin location in WGS84 decimal degrees."""

    name: str
    lat: float
    lon: float
    category: str
    source: str


def default_preset_path() -> Path:
    """Return the repository's committed preset catalogue path."""

    return Path(__file__).resolve().parents[3] / "data" / "presets" / "dublin_locations.yaml"


def load_presets(path: str | Path | None = None) -> dict[str, DublinPreset]:
    """Load the curated preset catalogue, keyed case-insensitively by name."""

    source = Path(path) if path is not None else default_preset_path()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise PresetError("Preset file must use schema_version: 1")
    raw_locations = payload.get("locations")
    if not isinstance(raw_locations, list) or not raw_locations:
        raise PresetError("Preset file must contain a non-empty locations list")
    result: dict[str, DublinPreset] = {}
    for raw in raw_locations:
        try:
            preset = DublinPreset(
                name=str(raw["name"]),
                lat=float(raw["lat"]),
                lon=float(raw["lon"]),
                category=str(raw["category"]),
                source=str(raw["source"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PresetError(f"Invalid preset entry: {raw!r}") from exc
        key = preset.name.casefold()
        if key in result:
            raise PresetError(f"Duplicate preset name: {preset.name}")
        result[key] = preset
    return result


def get_preset(name: str, path: str | Path | None = None) -> DublinPreset:
    """Return one named Dublin preset or list close available names in the error."""

    presets = load_presets(path)
    key = name.casefold().strip()
    if key not in presets:
        examples = ", ".join(p.name for p in list(presets.values())[:6])
        raise PresetError(f"Unknown Dublin preset {name!r}. Examples: {examples}")
    return presets[key]
