"""Environment-driven project configuration and structured logging."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repository_root() -> Path:
    """Return the repository root inferred from this source file.

    Returns
    -------
    pathlib.Path
        Absolute path containing ``pyproject.toml``.
    """

    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Validated project settings loaded from ``DLM_*`` environment variables.

    Times are measured in seconds and distances in metres throughout the project unless an
    interface explicitly states otherwise.
    """

    model_config = SettingsConfigDict(
        env_prefix="DLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    project_root: Path = Field(default_factory=_repository_root)
    cache_dir: Path = Path("data/cache")
    results_dir: Path = Path("results")
    global_seed: int = Field(default=42, ge=0)
    max_snap_distance_m: float = Field(default=500.0, gt=0)
    log_level: str = "INFO"
    distance_unit: str = "metres"
    time_unit: str = "seconds"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Normalise and validate the configured Python logging level.

        Parameters
        ----------
        value
            Logging level name such as ``INFO`` or ``DEBUG``.

        Returns
        -------
        str
            Upper-case logging level.

        Raises
        ------
        ValueError
            If ``value`` is not a standard Python logging level.
        """

        normalised = value.upper()
        if normalised not in logging.getLevelNamesMapping():
            raise ValueError(f"Unknown logging level: {value!r}")
        return normalised

    @field_validator("distance_unit")
    @classmethod
    def validate_distance_unit(cls, value: str) -> str:
        """Require the project-wide distance unit to remain metres.

        Parameters
        ----------
        value
            Requested distance unit.

        Returns
        -------
        str
            The canonical value ``metres``.
        """

        if value.lower() not in {"metre", "metres", "meter", "meters"}:
            raise ValueError("DLM_DISTANCE_UNIT must be metres")
        return "metres"

    @field_validator("time_unit")
    @classmethod
    def validate_time_unit(cls, value: str) -> str:
        """Require the project-wide time unit to remain seconds.

        Parameters
        ----------
        value
            Requested time unit.

        Returns
        -------
        str
            The canonical value ``seconds``.
        """

        if value.lower() not in {"second", "seconds"}:
            raise ValueError("DLM_TIME_UNIT must be seconds")
        return "seconds"

    @field_validator("project_root", "cache_dir", "results_dir", mode="after")
    @classmethod
    def expand_path(cls, value: Path) -> Path:
        """Expand user markers without touching the filesystem.

        Parameters
        ----------
        value
            Configured filesystem path.

        Returns
        -------
        pathlib.Path
            Expanded path. Relative cache/results paths are resolved by their properties.
        """

        return value.expanduser()

    @property
    def resolved_cache_dir(self) -> Path:
        """Return the absolute cache directory for graph and matrix artefacts."""

        return self._resolve_from_root(self.cache_dir)

    @property
    def resolved_results_dir(self) -> Path:
        """Return the absolute output directory for experiment results."""

        return self._resolve_from_root(self.results_dir)

    def _resolve_from_root(self, value: Path) -> Path:
        """Resolve a project-relative path against ``project_root``."""

        return value if value.is_absolute() else self.project_root / value


class JsonFormatter(logging.Formatter):
    """Format standard-library log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise one log record.

        Parameters
        ----------
        record
            Standard Python log record.

        Returns
        -------
        str
            Deterministically ordered JSON containing timestamp, level, logger, and message.
        """

        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, self.datefmt),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache the validated project settings.

    Returns
    -------
    Settings
        Immutable-by-convention process configuration.
    """

    return Settings()


def configure_logging(settings: Settings | None = None) -> None:
    """Configure root logging with the environment-selected level and JSON output.

    Parameters
    ----------
    settings
        Settings to use. When omitted, :func:`get_settings` loads them from ``DLM_*`` variables.
    """

    active_settings = settings or get_settings()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(active_settings.log_level)
