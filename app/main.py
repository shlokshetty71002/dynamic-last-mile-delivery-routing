"""Barebones Streamlit client over the tested ``src/dlm`` pipeline."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import folium
import streamlit as st
import yaml
from folium.plugins import Draw
from streamlit_folium import st_folium

from app.state import initialise_state, reset_run_state
from dlm.config import get_settings
from dlm.disruption.schema import DisruptionType, Scenario, scenario_from_geojson
from dlm.instance.builder import InstanceBuilder
from dlm.instance.geocode import CachedGeocoder
from dlm.instance.presets import load_presets
from dlm.instance.schema import DeliveryInstance, LocationSource
from dlm.network.loader import build_or_load_network
from dlm.simulation import InformationModel
from dlm.viz import case_comparison_figure, comparison_map, instance_map
from dlm.workflows import compare_delivery, comparison_configuration

st.set_page_config(page_title="Dublin Last-Mile Routing", layout="wide")
st.title("Disruption-Aware Dublin Last-Mile Routing")
st.caption("Choose a depot and any number of stops, model a disruption, then compare T1/T2/T3.")


@st.cache_resource(show_spinner="Loading the cached M50 road network…")
def load_graph():
    """Load the road graph once per app process."""

    return build_or_load_network().graph


graph = load_graph()
settings = get_settings()
new_builder = InstanceBuilder(
    graph,
    name="interactive-run",
    seed=settings.global_seed,
    max_snap_distance_m=settings.max_snap_distance_m,
    geocoder=CachedGeocoder(settings.resolved_cache_dir / "geocoding"),
)
initialise_state(st.session_state, builder=new_builder)
builder: InstanceBuilder = st.session_state.builder
presets = load_presets()
preset_names = [preset.name for preset in presets.values()]

st.header("Step 1 — Build your delivery run")
left, right = st.columns([2, 1])
with left:
    active_map = (
        instance_map(builder.build())
        if builder.depot is not None and builder.stops
        else folium.Map(location=(53.3498, -6.2603), zoom_start=11, control_scale=True)
    )
    map_state = st_folium(
        active_map,
        height=480,
        use_container_width=True,
        returned_objects=["last_clicked"],
        key="location-map",
    )
    last_clicked = map_state.get("last_clicked") if map_state else None
    click_label = st.text_input("Label for the last map click", value="Map location")
    click_depot, click_stop = st.columns(2)
    if click_depot.button("Use last click as depot", disabled=not last_clicked):
        try:
            builder.set_depot_from_latlon(
                last_clicked["lat"],
                last_clicked["lng"],
                label=click_label,
                source=LocationSource.MAP_CLICK,
            )
            reset_run_state(st.session_state)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if click_stop.button("Add last click as stop", disabled=not last_clicked):
        try:
            builder.add_stop_from_latlon(
                last_clicked["lat"],
                last_clicked["lng"],
                label=click_label,
                source=LocationSource.MAP_CLICK,
            )
            reset_run_state(st.session_state)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

with right:
    depot_preset = st.selectbox("Choose depot preset", ["Choose…", *preset_names])
    if st.button("Set selected depot", disabled=depot_preset == "Choose…"):
        try:
            builder.set_depot_from_preset(depot_preset)
            reset_run_state(st.session_state)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    stop_preset = st.selectbox("Add stop preset", ["Choose…", *preset_names])
    if st.button("Add selected preset", disabled=stop_preset == "Choose…"):
        try:
            builder.add_stop_from_preset(stop_preset)
            reset_run_state(st.session_state)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    address = st.text_input("Add by Dublin address/place")
    if st.button("Geocode and add", disabled=not address):
        try:
            builder.add_stop_from_address(address)
            reset_run_state(st.session_state)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    random_count = st.number_input("Random stops to add", min_value=1, max_value=20, value=3)
    random_seed = st.number_input("Random seed", min_value=0, value=42)
    if st.button("Add seeded random stops"):
        try:
            builder.add_random_stops(int(random_count), seed=int(random_seed))
            reset_run_state(st.session_state)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

st.write(f"Selected delivery stops: **{len(builder.stops)}**")
if builder.stops:
    st.dataframe(
        [
            {
                "id": stop.id,
                "label": stop.label,
                "latitude": stop.lat,
                "longitude": stop.lon,
                "source": stop.source.value,
            }
            for stop in builder.stops
        ],
        use_container_width=True,
        hide_index=True,
    )
    remove_id = st.selectbox("Stop to delete", [stop.id for stop in builder.stops])
    if st.button("Delete selected stop"):
        builder.remove_stop(remove_id)
        reset_run_state(st.session_state)
        st.rerun()

fleet_size = st.number_input(
    "Fleet size K",
    min_value=1,
    max_value=max(1, len(builder.stops)),
    value=min(builder.fleet_size, max(1, len(builder.stops))),
)
builder.fleet_size = int(fleet_size)
instance_name = st.text_input("Instance name", value=builder.name)
builder.name = instance_name
save_col, load_col = st.columns(2)
with save_col:
    if st.button("Save instance", disabled=builder.depot is None or not builder.stops):
        try:
            saved = builder.build().save(Path("data/instances") / f"{instance_name}.json")
            st.success(f"Saved {saved}")
        except Exception as exc:
            st.error(str(exc))
with load_col:
    available_instances = sorted(Path("data/instances").glob("*.json"))
    selected_instance = st.selectbox(
        "Load saved instance",
        ["Choose…", *(str(path) for path in available_instances)],
    )
    if st.button("Load instance", disabled=selected_instance == "Choose…"):
        try:
            loaded = DeliveryInstance.load(selected_instance)
            st.session_state.builder = InstanceBuilder.from_instance(
                graph,
                loaded,
                geocoder=CachedGeocoder(settings.resolved_cache_dir / "geocoding"),
            )
            reset_run_state(st.session_state)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

st.header("Step 2 — Add a disruption")
scenario_paths = sorted(Path("scenarios").glob("*.yaml"))
scenario_choice = st.selectbox(
    "Load a committed Dublin scenario",
    ["Choose…", *(str(path) for path in scenario_paths)],
)
if st.button("Load selected scenario", disabled=scenario_choice == "Choose…"):
    try:
        st.session_state.scenario = Scenario.load(scenario_choice)
        st.session_state.result = None
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

draw_map = (
    instance_map(builder.build())
    if builder.depot is not None and builder.stops
    else folium.Map(location=(53.3498, -6.2603), zoom_start=11)
)
Draw(
    export=False,
    draw_options={
        "polyline": True,
        "polygon": True,
        "rectangle": False,
        "circle": False,
        "marker": False,
        "circlemarker": False,
    },
).add_to(draw_map)
draw_state = st_folium(
    draw_map,
    height=480,
    use_container_width=True,
    returned_objects=["all_drawings"],
    key="disruption-map",
)
draw_type = st.selectbox(
    "Drawn disruption type",
    [
        DisruptionType.POLYGON_CLOSURE,
        DisruptionType.CORRIDOR_CLOSURE,
        DisruptionType.SLOW_ZONE,
    ],
    format_func=lambda value: value.value,
)
slow_factor = st.slider("Slow/partial travel-time factor", 1.1, 5.0, 2.0, 0.1)
drawings = draw_state.get("all_drawings", []) if draw_state else []
if st.button("Use most recent drawing", disabled=not drawings):
    try:
        geometry = drawings[-1]["geometry"]
        st.session_state.scenario = scenario_from_geojson(
            geometry,
            name="interactive_disruption",
            disruption_type=draw_type,
            factor=slow_factor,
        )
        st.session_state.result = None
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

active_scenario: Scenario | None = st.session_state.scenario
if active_scenario is not None:
    st.success(f"Active scenario: {active_scenario.name}")
    st.download_button(
        "Export scenario to YAML",
        active_scenario.to_yaml(),
        file_name=f"{active_scenario.name}.yaml",
        mime="application/yaml",
    )

st.header("Step 3 — Compare")
information_model = st.radio(
    "Driver information model",
    [InformationModel.REACTIVE, InformationModel.OMNISCIENT],
    format_func=lambda value: (
        "Reactive — discovers a closure on arrival"
        if value is InformationModel.REACTIVE
        else "Omniscient — knows closures at route start but keeps stop order"
    ),
)
if st.button(
    "Run comparison",
    type="primary",
    disabled=builder.depot is None or not builder.stops or active_scenario is None,
):
    try:
        with st.spinner("Solving T1, executing T2, and re-optimising T3…"):
            active_instance = builder.build()
            st.session_state.result = compare_delivery(
                graph,
                active_instance,
                active_scenario,
                information_model=information_model,
                matrix_cache_dir=settings.resolved_cache_dir,
            )
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

result = st.session_state.result
if result is not None and active_scenario is not None:
    metric_columns = st.columns(4)
    metric_columns[0].metric("T1 planned", f"{result.t1_s:.1f} s")
    metric_columns[1].metric(
        "T2 disrupted", "Infeasible" if result.t2_s is None else f"{result.t2_s:.1f} s"
    )
    metric_columns[2].metric(
        "T3 replanned", "Infeasible" if result.t3_s is None else f"{result.t3_s:.1f} s"
    )
    metric_columns[3].metric(
        "Saving",
        "N/A" if result.saving_percent is None else f"{result.saving_percent:.2f}%",
    )
    st.dataframe(
        {
            "case": ["T1", "T2", "T3"],
            "distance_km": [
                result.t1_environment.distance_km,
                result.t2_environment.distance_km,
                result.t3_environment.distance_km,
            ],
            "fuel_l": [
                result.t1_environment.fuel_l,
                result.t2_environment.fuel_l,
                result.t3_environment.fuel_l,
            ],
            "co2_kg": [
                result.t1_environment.co2_kg,
                result.t2_environment.co2_kg,
                result.t3_environment.co2_kg,
            ],
        },
        use_container_width=True,
        hide_index=True,
    )
    active_instance = builder.build()
    st_folium(
        comparison_map(graph, active_instance, result, active_scenario),
        height=560,
        use_container_width=True,
        key="comparison-result-map",
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "result.json",
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        )
        archive.writestr(
            "config.yaml",
            yaml.safe_dump(
                comparison_configuration(
                    graph,
                    active_instance,
                    active_scenario,
                    result,
                    information_model=result.information_model,
                ),
                sort_keys=True,
                allow_unicode=True,
            ),
        )
        archive.writestr(f"{active_scenario.name}.yaml", active_scenario.to_yaml())
        archive.writestr(
            f"{active_instance.name}.json",
            json.dumps(active_instance.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        )
        archive.writestr(
            "comparison-map.html",
            comparison_map(graph, active_instance, result, active_scenario).get_root().render(),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            png, svg = case_comparison_figure(
                result,
                Path(temporary_directory) / "comparison",
            )
            archive.write(png, "comparison.png")
            archive.write(svg, "comparison.svg")
    st.download_button(
        "Download results bundle",
        buffer.getvalue(),
        file_name=f"{result.run_id}-results.zip",
        mime="application/zip",
    )
