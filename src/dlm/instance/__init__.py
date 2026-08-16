"""Dynamic depot, delivery-stop, and matrix interfaces."""

from dlm.instance.builder import InstanceBuilder, MutationResult
from dlm.instance.matrix import PointRef, TravelMatrix, build_matrix, points_from_instance
from dlm.instance.schema import DeliveryInstance, Depot, LocationSource, Stop

__all__ = [
    "DeliveryInstance",
    "Depot",
    "InstanceBuilder",
    "LocationSource",
    "MutationResult",
    "PointRef",
    "Stop",
    "TravelMatrix",
    "build_matrix",
    "points_from_instance",
]
