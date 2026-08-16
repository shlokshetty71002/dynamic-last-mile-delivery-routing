"""Versioned, validated disruption and scenario models."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from dlm.instance.schema import NodeId

SCENARIO_SCHEMA_VERSION = 1
Coordinate = tuple[float, float]
EdgeId = tuple[NodeId, NodeId, int | str]


class ScenarioValidationError(ValueError):
    """Raised when a disruption scenario violates its documented schema."""


class DisruptionType(StrEnum):
    """Supported graph modifications."""

    EDGE_CLOSURE = "edge_closure"
    POLYGON_CLOSURE = "polygon_closure"
    CORRIDOR_CLOSURE = "corridor_closure"
    SLOW_ZONE = "slow_zone"
    NODE_CLOSURE = "node_closure"


class Severity(StrEnum):
    """Whether a closure blocks travel or models restricted slow access."""

    FULL = "full"
    PARTIAL = "partial"


class Disruption(BaseModel):
    """One reproducible, optionally time-limited road-network disruption."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    type: DisruptionType
    severity: Severity = Severity.FULL
    edge_ids: tuple[EdgeId, ...] = ()
    node_ids: tuple[NodeId, ...] = ()
    street: str | None = None
    geometry: tuple[Coordinate, ...] = ()
    factor: float = Field(default=2.0, gt=1.0)
    buffer_m: float = Field(default=35.0, gt=0)
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_for_type(self) -> Disruption:
        """Require exactly the spatial fields needed by this disruption type."""

        if self.start_s is not None and self.end_s is not None and self.end_s <= self.start_s:
            raise ValueError("end_s must be greater than start_s")
        requirements = {
            DisruptionType.EDGE_CLOSURE: bool(self.edge_ids),
            DisruptionType.NODE_CLOSURE: bool(self.node_ids),
            DisruptionType.POLYGON_CLOSURE: len(self.geometry) >= 4,
            DisruptionType.SLOW_ZONE: len(self.geometry) >= 4,
            DisruptionType.CORRIDOR_CLOSURE: bool(self.street) or len(self.geometry) >= 2,
        }
        if not requirements[self.type]:
            raise ValueError(f"{self.type.value} is missing its required IDs or geometry")
        if self.type in {DisruptionType.POLYGON_CLOSURE, DisruptionType.SLOW_ZONE}:
            if self.geometry[0] != self.geometry[-1]:
                raise ValueError(f"{self.type.value} geometry must be a closed lon/lat ring")
        return self

    def active_at(self, elapsed_s: float) -> bool:
        """Return whether this disruption is active at elapsed route time in seconds."""

        return (self.start_s is None or elapsed_s >= self.start_s) and (
            self.end_s is None or elapsed_s <= self.end_s
        )


class Scenario(BaseModel):
    """Named, source-attributed collection of reproducible disruptions."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCENARIO_SCHEMA_VERSION
    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = Field(min_length=1)
    source: str = Field(min_length=1)
    created: date
    disruptions: tuple[Disruption, ...]

    @model_validator(mode="after")
    def validate_scenario(self) -> Scenario:
        """Require a supported schema, at least one disruption, and unique IDs."""

        if self.schema_version != SCENARIO_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported scenario schema_version={self.schema_version}; "
                f"expected {SCENARIO_SCHEMA_VERSION}"
            )
        if not self.disruptions:
            raise ValueError("A scenario must contain at least one disruption")
        ids = [disruption.id for disruption in self.disruptions]
        if len(ids) != len(set(ids)):
            raise ValueError("Disruption IDs must be unique within a scenario")
        return self

    def save(self, path: str | Path) -> Path:
        """Write canonical YAML that round-trips without semantic drift."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_yaml(), encoding="utf-8")
        return destination

    def to_yaml(self) -> str:
        """Return the canonical YAML representation for CLI/UI download parity."""

        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False, allow_unicode=True)

    @classmethod
    def load(cls, path: str | Path) -> Scenario:
        """Load a YAML scenario with field-specific Pydantic validation errors."""

        source = Path(path)
        try:
            payload = yaml.safe_load(source.read_text(encoding="utf-8"))
            return cls.model_validate(payload)
        except Exception as exc:
            if isinstance(exc, ScenarioValidationError):
                raise
            raise ScenarioValidationError(f"Invalid scenario file {source}: {exc}") from exc


def scenario_from_geojson(
    geometry: dict[str, object],
    *,
    name: str,
    disruption_type: DisruptionType,
    factor: float = 2.0,
) -> Scenario:
    """Convert a Folium/Leaflet drawn geometry into the stable scenario schema."""

    kind = str(geometry.get("type", ""))
    coordinates = geometry.get("coordinates")
    if kind == "Polygon" and isinstance(coordinates, list) and coordinates:
        raw = coordinates[0]
    elif kind == "LineString" and isinstance(coordinates, list):
        raw = coordinates
    else:
        raise ScenarioValidationError("Draw a GeoJSON Polygon or LineString")
    points = tuple((float(point[0]), float(point[1])) for point in raw)
    return Scenario(
        name=name,
        description="Scenario drawn interactively on the Dublin map.",
        source="User-drawn GeoJSON exported by the Streamlit interface.",
        created=date.today(),
        disruptions=(
            Disruption(
                id="drawn-1",
                type=disruption_type,
                geometry=points,
                factor=factor,
            ),
        ),
    )
