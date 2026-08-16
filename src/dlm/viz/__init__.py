"""Static, interactive, and report-ready visualisations."""

from dlm.viz.figures import case_comparison_figure, saving_vs_stops_figure
from dlm.viz.folium_map import comparison_map, instance_map, save_map

__all__ = [
    "case_comparison_figure",
    "comparison_map",
    "instance_map",
    "save_map",
    "saving_vs_stops_figure",
]
