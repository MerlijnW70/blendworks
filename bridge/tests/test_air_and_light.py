"""Air by meteorology and light by the sun's height: visibility by condition, valley mist only under its conditions and
thinning as the sun rises, direct and sky light in the published ratio, crisp sun shadows through the default haze."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from final_helpers import EXACT
from harness import close, run

from blendworks_bridge import exr_read, sky_measure, valley_mist, weather_continuum
from blendworks_bridge.atmosphere_haze import extinction

CLEAR_RANGE = (20_000.0, 50_000.0)
ASHRAE_C = (0.058, 0.136)
SHADOW_RATIO = 4.0
SIDE = 600.0
CELLS = 31


def test_default_air_has_the_visibility_of_its_condition(bridge):
    assert weather_continuum.VISIBILITY_CLASSES == {"fog": (50.0, 1000.0), "mist": (1000.0, 5000.0), "hazy": (5000.0, 10000.0),
                                                   "clear": CLEAR_RANGE}
    clear = weather_continuum.state(0.0)["visibility"]
    assert CLEAR_RANGE[0] <= clear <= CLEAR_RANGE[1], clear
    assert weather_continuum.condition_of(clear) == "clear"
    hazy = weather_continuum.PRESETS["hazy"]["visibility"]
    assert weather_continuum.condition_of(hazy) == "hazy"
    bridge.ok("add_primitive", type="cube", name="Thing", size=2.0)
    made = bridge.ok("atmosphere")
    assert CLEAR_RANGE[0] <= made["visibility"] <= CLEAR_RANGE[1] and made["visibility_source"] == "condition clear", made
    for condition, (low, high) in weather_continuum.VISIBILITY_CLASSES.items():
        visibility = bridge.ok("atmosphere", condition=condition)["visibility"]
        assert low <= visibility <= high, (condition, visibility)
    bridge.ok("weather", preset="hazy", form="sheet", haze=False)
    following = bridge.ok("atmosphere")
    assert following["visibility_source"] == "weather" and following["condition"] == "hazy", following
    assert bridge.ok("atmosphere", visibility=1234.0)["visibility"] == 1234.0


def basin(bridge):
    xs = np.linspace(-SIDE / 2.0, SIDE / 2.0, CELLS)
    grid_x, grid_y = np.meshgrid(xs, xs)
    z = 40.0 * (1.0 - np.exp(-(grid_x ** 2 + grid_y ** 2) / 150.0 ** 2))
    vertices = np.column_stack([grid_x.ravel(), grid_y.ravel(), z.ravel()]).tolist()
    faces = [[row * CELLS + column, row * CELLS + column + 1, (row + 1) * CELLS + column + 1, (row + 1) * CELLS + column]
             for row in range(CELLS - 1) for column in range(CELLS - 1)]
    bridge.ok("mesh_from_data", name="Basin", vertices=vertices, faces=faces)


def mist(bridge, **conditions):
    return bridge.ok("valley_mist", ground=["Basin"], centre=[0.0, 0.0], radius=280.0, cells=32, valley_width=100.0, fade=2.0,
                     conditions=conditions)


def floor_density(conditions_report_name="ValleyMist", height=1.0):
    obj = bpy.data.objects.get(conditions_report_name)
    if obj is None:
        return 0.0
    settings = json.loads(obj[valley_mist.PROPERTY])
    image = bpy.data.images[conditions_report_name + valley_mist.TOP_IMAGE_SUFFIX]
    width, rows = image.size
    pixels = np.empty(width * rows * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    grid = pixels.reshape(rows, width, 4)[..., :2].astype(np.float64)
    return float(valley_mist.density(settings, grid, np.array([[0.0, 0.0]]), np.array([height]))[0])


def test_mist_forms_only_under_its_conditions(bridge):
    basin(bridge)
    dawn = {"sun_elevation": 0.0, "sun_azimuth": 90.0, "wind": 1.0, "humidity": 0.98, "cover": 0.1}
    formed = mist(bridge, **dawn)
    assert formed["formed"]["forms"] and formed["name"] == "ValleyMist", formed["formed"]
    full = extinction(valley_mist.DEFAULT_VISIBILITY)
    close(floor_density(), full, 1e-6)
    assert valley_mist.THICKNESS_RANGE[0] <= formed["thickness"] <= valley_mist.THICKNESS_RANGE[1]
    assert valley_mist.VISIBILITY_RANGE[0] <= formed["visibility"] <= valley_mist.VISIBILITY_RANGE[1]
    failing = {"wind": 6.0, "humidity": 0.8, "cover": 0.9, "sun_azimuth": 250.0}
    for key, value in failing.items():
        changed = dict(dawn, **{key: value})
        if key == "sun_azimuth":
            changed["sun_elevation"] = 10.0
        result = mist(bridge, **changed)
        assert not result["formed"]["forms"] and result["name"] is None, (key, result["formed"])
        assert bpy.data.objects.get("ValleyMist") is None
    ridge = mist(bridge, **dawn)
    top = bpy.data.objects["ValleyMist"]
    assert ridge["coverage"] < 0.6 and top.dimensions.z < 60.0, ridge


def test_mist_thins_and_lifts_as_the_sun_rises(bridge):
    basin(bridge)
    densities, lifts = [], []
    for elevation in (0.0, 8.0, 16.0, 24.0):
        made = mist(bridge, sun_elevation=elevation, sun_azimuth=100.0, wind=1.0, humidity=0.98, cover=0.0)
        lift = json.loads(bpy.data.objects["ValleyMist"][valley_mist.PROPERTY])["lift"]
        densities.append(floor_density(height=lift + made["thickness"] / 2.0))
        lifts.append(lift)
        if lift > 2.0 * 2.0:
            assert floor_density(height=0.5) == 0.0, elevation
        close(made["formed"]["burnt"], elevation / valley_mist.BURN_OFF_ELEVATION, 1e-5)
    assert all(a > b for a, b in zip(densities, densities[1:])), densities
    assert all(a < b for a, b in zip(lifts, lifts[1:])), lifts
    close(valley_mist.BURN_OFF_ELEVATION, 27.04, 0.01)
    gone = mist(bridge, sun_elevation=30.0, sun_azimuth=120.0, wind=1.0, humidity=0.98, cover=0.0)
    assert not gone["formed"]["forms"]


def test_direct_and_diffuse_light_are_in_the_clear_sky_ratio(bridge):
    """ASHRAE clear-day model: diffuse horizontal = C times direct normal, C from 0.058 (January) to 0.136 (July); the ratio
    of direct horizontal to diffuse is then sin(h) / C."""
    for elevation in (10.0, 30.0, 60.0):
        sky = bridge.ok("sky", sun={"elevation": elevation, "azimuth": 180.0}, exposure="keep")["sky"]
        direct = sky_measure.luminance(sky["sun_irradiance"]) * math.sin(math.radians(elevation))
        diffuse = sky_measure.luminance(sky["horizontal_irradiance"])
        ratio = direct / diffuse
        low, high = (math.sin(math.radians(elevation)) / c for c in (ASHRAE_C[1], ASHRAE_C[0]))
        assert low <= ratio <= high, (elevation, ratio, low, high)


def test_sun_shadows_stay_crisp_through_the_default_haze(bridge):
    bridge.ok("add_primitive", type="plane", name="Ground", size=60.0)
    bridge.ok("add_material", name="Grey", base_color=[0.18, 0.18, 0.18], roughness=1.0)
    bridge.ok("assign_material", name="Ground", material="Grey")
    bridge.ok("add_primitive", type="cube", name="Block", size=4.0, location=[0.0, 0.0, 8.0])
    bridge.ok("add_camera", name="Cam", location=[0.0, 0.0, 40.0], rotation=[0.0, 0.0, 0.0], lens=35.0)
    result = bridge.ok("weather", preset="clear", sun={"elevation": 60.0, "azimuth": 180.0})
    assert result["haze"] is not None and CLEAR_RANGE[0] <= result["haze"]["visibility"] <= CLEAR_RANGE[1], result["haze"]
    bridge.ok("render_final", path="shadow.exr", **dict(EXACT, width=96, height=96, samples=32))
    image = exr_read.read_exr(os.path.join(bridge.workspace, "shadow.exr")).stack("", "RGB").mean(axis=-1)
    block = bpy.data.objects["Block"]
    offset = 8.0 / math.tan(math.radians(60.0))
    shadow_centre = np.array([0.0, offset])
    size = image.shape[0]
    half = 40.0 * math.tan(bpy.data.objects["Cam"].data.angle / 2.0)
    rows, columns = np.mgrid[0:size, 0:size]
    x = (columns + 0.5) / size * 2.0 * half - half
    y = half - (rows + 0.5) / size * 2.0 * half
    in_shadow = (np.abs(x - shadow_centre[0]) < 1.0) & (np.abs(y - shadow_centre[1]) < 1.0)
    open_ground = np.hypot(x, y - offset) > 8.0
    assert block is not None and in_shadow.any()
    ratio = float(image[open_ground].mean() / image[in_shadow].mean())
    assert ratio > SHADOW_RATIO, ratio


def horizon_rows(bridge, name):
    image = exr_read.read_exr(os.path.join(bridge.workspace, f"{name}.exr")).stack("", "RGB")
    return image.mean(axis=1)


def test_clear_day_has_no_white_band_along_the_horizon(bridge):
    """Land to 60 km under the clear day's depth haze: the sky above the horizon stays as the sky model made it, and the
    far land fades towards the sky's own horizon colour, never past it."""
    bridge.ok("add_primitive", type="plane", name="Land", size=120_000.0)
    bridge.ok("add_material", name="Field", base_color=[0.08, 0.14, 0.05], roughness=1.0)
    bridge.ok("assign_material", name="Land", material="Field")
    bridge.ok("add_camera", name="Cam", location=[0.0, 0.0, 30.0], rotation=[90.0, 0.0, 0.0], lens=35.0)
    bridge.ok("camera_setup", name="Cam", clip_end=200_000.0)
    bridge.ok("weather", preset="clear", sun={"elevation": 40.0, "azimuth": 150.0}, haze=False)
    quick = dict(EXACT, width=48, height=96, samples=16)
    bridge.ok("render_final", path="bare.exr", **quick)
    haze = bridge.ok("atmosphere", height_falloff=1200.0, method="depth")
    assert CLEAR_RANGE[0] <= haze["visibility"] <= CLEAR_RANGE[1]
    bridge.ok("render_final", path="hazed.exr", **quick)
    bare, hazed = horizon_rows(bridge, "bare"), horizon_rows(bridge, "hazed")
    luminance = hazed @ np.array([0.2126, 0.7152, 0.0722])
    bare_luminance = bare @ np.array([0.2126, 0.7152, 0.0722])
    horizon = int(np.argmax(np.abs(np.diff(bare_luminance))))
    sky = slice(0, horizon - 1)
    change = np.abs(hazed[sky] - bare[sky]) / np.maximum(bare[sky], 1e-6)
    assert float(change.max()) < 0.05, change.max()
    land = luminance[horizon + 2:]
    assert float(land.max()) <= float(luminance[horizon - 2]) * 1.02, (land.max(), luminance[horizon - 2])
    assert np.all(np.diff(land) <= 1e-4 + 0.02 * land[:-1]), land
    far = hazed[horizon + 2] / hazed[horizon + 2].sum()
    near = hazed[-1] / hazed[-1].sum()
    assert far[2] > near[2], (far, near)


run(globals())
