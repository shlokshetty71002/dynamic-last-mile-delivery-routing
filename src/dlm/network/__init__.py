"""Road-network acquisition, annotation, and location snapping."""

from dlm.network.loader import (
    M50_CATCHMENT_BBOX,
    NetworkBuildError,
    NetworkBuildResult,
    NetworkSpec,
    NetworkStats,
    build_or_load_network,
    cache_key,
    network_stats,
)
from dlm.network.snapping import (
    GraphCoordinateError,
    InvalidCoordinateError,
    SnapResult,
    SnapTooFarError,
    snap_to_node,
)
from dlm.network.travel_time import (
    SpeedConfigurationError,
    SpeedDefaults,
    TravelTimeError,
    annotate_travel_times,
    load_speed_defaults,
)

__all__ = [
    "M50_CATCHMENT_BBOX",
    "GraphCoordinateError",
    "InvalidCoordinateError",
    "NetworkBuildError",
    "NetworkBuildResult",
    "NetworkSpec",
    "NetworkStats",
    "SnapResult",
    "SnapTooFarError",
    "SpeedConfigurationError",
    "SpeedDefaults",
    "TravelTimeError",
    "annotate_travel_times",
    "build_or_load_network",
    "cache_key",
    "load_speed_defaults",
    "network_stats",
    "snap_to_node",
]
