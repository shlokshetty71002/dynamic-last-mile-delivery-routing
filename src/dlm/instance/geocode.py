"""Cached, ambiguity-aware address geocoding for Dublin locations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests


class GeocodingError(RuntimeError):
    """Raised when a query fails or returns no Dublin candidates."""


class AmbiguousAddressError(GeocodingError):
    """Raised when a query returns several candidates and selection is required."""

    def __init__(self, query: str, candidates: list[GeocodeCandidate]) -> None:
        self.query = query
        self.candidates = candidates
        labels = "; ".join(c.display_name for c in candidates[:5])
        super().__init__(f"Address {query!r} is ambiguous. Choose one candidate: {labels}")


@dataclass(frozen=True)
class GeocodeCandidate:
    """One address result in WGS84 decimal degrees."""

    display_name: str
    lat: float
    lon: float
    importance: float = 0.0


Provider = Callable[[str, int], list[GeocodeCandidate]]


class CachedGeocoder:
    """Nominatim geocoder with deterministic on-disk query caching."""

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        provider: Provider | None = None,
        user_agent: str = "dlm-acm40960/1.0 (academic routing project)",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.provider = provider or self._nominatim

    def candidates(self, query: str, *, limit: int = 5) -> list[GeocodeCandidate]:
        """Return cached Dublin candidates without silently choosing an ambiguous result."""

        normalised = " ".join(query.split())
        if not normalised:
            raise GeocodingError("Address query cannot be empty")
        key = hashlib.sha256(normalised.casefold().encode()).hexdigest()[:20]
        cache_path = self.cache_dir / f"geocode-{key}.json"
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            return [GeocodeCandidate(**item) for item in raw]
        try:
            found = self.provider(normalised, limit)
        except Exception as exc:
            raise GeocodingError(
                f"Could not geocode {normalised!r}. Check internet access and try again."
            ) from exc
        if not found:
            raise GeocodingError(f"No Dublin location matched {normalised!r}")
        cache_path.write_text(
            json.dumps([asdict(item) for item in found], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return found

    def resolve(self, query: str, *, choice: int | None = None) -> GeocodeCandidate:
        """Resolve one query, requiring an explicit choice when several results exist."""

        found = self.candidates(query)
        if choice is None and len(found) > 1:
            raise AmbiguousAddressError(query, found)
        index = 0 if choice is None else choice
        if not 0 <= index < len(found):
            raise GeocodingError(f"Candidate choice must be between 0 and {len(found) - 1}")
        return found[index]

    def _nominatim(self, query: str, limit: int) -> list[GeocodeCandidate]:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "jsonv2",
                "limit": limit,
                "countrycodes": "ie",
                "viewbox": "-6.50,53.47,-6.05,53.20",
                "bounded": 1,
            },
            headers={"User-Agent": self.user_agent},
            timeout=30,
        )
        response.raise_for_status()
        payload: list[dict[str, Any]] = response.json()
        return [
            GeocodeCandidate(
                display_name=str(item["display_name"]),
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                importance=float(item.get("importance", 0.0)),
            )
            for item in payload
        ]
