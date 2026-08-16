"""Validated, schema-versioned delivery-instance models with dynamic stop counts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1
MIN_STOPS = 1
MAX_STOPS = 50
DEFAULT_SERVICE_TIME_S = 180.0
NodeId = int | str


class InstanceValidationError(ValueError):
    """Raised when an instance is incomplete or operationally inconsistent."""


class LocationSource(StrEnum):
    """Supported ways a user can choose a depot or delivery stop."""

    ADDRESS = "address"
    LATLON = "latlon"
    PRESET = "preset"
    RANDOM = "random"
    MAP_CLICK = "map_click"


class TimeWindow(BaseModel):
    """Optional delivery time window measured from route start, in seconds."""

    model_config = ConfigDict(frozen=True)

    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> TimeWindow:
        """Require the window end to occur after its start."""

        if self.end_s <= self.start_s:
            raise ValueError("time-window end_s must be greater than start_s")
        return self


class Stop(BaseModel):
    """One user-selected delivery location snapped to a routable graph node."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    node: NodeId | None = None
    demand: float = Field(default=0.0, ge=0)
    service_time_s: float = Field(default=DEFAULT_SERVICE_TIME_S, ge=0)
    time_window: TimeWindow | None = None
    source: LocationSource = LocationSource.LATLON


class Depot(Stop):
    """User-selected route origin and destination, modelled as a special stop."""

    id: str = "depot"
    service_time_s: float = 0.0


class DeliveryInstance(BaseModel):
    """Immutable routing instance whose number of stops is always derived at runtime."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=100)
    depot: Depot
    stops: tuple[Stop, ...]
    fleet_size: int = Field(default=1, ge=1)
    vehicle_capacity: float | None = Field(default=None, gt=0)
    seed: int = Field(default=42, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def n_stops(self) -> int:
        """Return the live delivery-stop count; it is never stored separately."""

        return len(self.stops)

    @property
    def points(self) -> tuple[Depot | Stop, ...]:
        """Return depot followed by delivery stops in stable matrix order."""

        return (self.depot, *self.stops)

    @property
    def node_ids(self) -> tuple[NodeId, ...]:
        """Return all resolved graph nodes or fail with a readable message."""

        unresolved = [point.label for point in self.points if point.node is None]
        if unresolved:
            raise InstanceValidationError(
                "Instance contains locations not snapped to the road graph: "
                + ", ".join(unresolved)
            )
        return tuple(point.node for point in self.points if point.node is not None)

    @model_validator(mode="after")
    def validate_instance(self) -> DeliveryInstance:
        """Enforce dynamic-size, identity, fleet, and capacity invariants."""

        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                "Unsupported instance schema_version="
                f"{self.schema_version}; expected {SCHEMA_VERSION}"
            )
        if not MIN_STOPS <= len(self.stops) <= MAX_STOPS:
            raise ValueError(f"An instance must contain between {MIN_STOPS} and {MAX_STOPS} stops")
        ids = [point.id for point in self.points]
        if len(ids) != len(set(ids)):
            raise ValueError("Depot and stop IDs must be unique")
        resolved = [point.node for point in self.points if point.node is not None]
        if len(resolved) != len(set(resolved)):
            raise ValueError("Two locations resolve to the same road node; move or merge one")
        if self.fleet_size > len(self.stops):
            raise ValueError("fleet_size cannot exceed the number of delivery stops")
        if self.vehicle_capacity is not None:
            excessive = [s.label for s in self.stops if s.demand > self.vehicle_capacity]
            if excessive:
                raise ValueError(
                    "Individual stop demand exceeds vehicle capacity: " + ", ".join(excessive)
                )
        return self

    def content_hash(self) -> str:
        """Return a stable hash of scientifically relevant instance inputs."""

        payload = self.model_dump(mode="json", exclude={"created_at"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]

    def save(self, path: str | Path) -> Path:
        """Write a deterministic, losslessly reloadable JSON representation."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return destination

    @classmethod
    def load(cls, path: str | Path) -> DeliveryInstance:
        """Load and validate an instance JSON file."""

        source = Path(path)
        return cls.model_validate_json(source.read_text(encoding="utf-8"))
