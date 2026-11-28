"""Exposure and colour like a camera: metering, EV against the published tables, the tone response against the
ColorChecker, white balance, and explicit settings that stay."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from final_helpers import EXACT
from harness import close, run

from blendworks_bridge import camera_exposure, exr_read, sky_world

QUICK = dict(EXACT, width=64, height=48, samples=8)
GREY = 0.18
METER_TOLERANCE = 0.1
SUNNY_SIXTEEN = camera_exposure.ev100(16.0, 1.0 / 125.0, 100.0)
SUNNY_TOLERANCE = 2.0 / 3.0
TABLE_TOLERANCE = 0.5
COLOR_CHECKER_NEUTRALS = ((243, 243, 242), (200, 200, 200), (160, 160, 160), (122, 122, 121), (85, 85, 85), (52, 52, 52))
TONE_RMS = 0.07
TONE_WORST = 0.13
HIGHLIGHT_STOPS = 4.0
HIGHLIGHT_LEVEL = 0.9
NEUTRAL_TOLERANCE = 0.01
TINTED = 0.03


def decode(value):
    value = value / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def encode(value):
    value = np.clip(value, 0.0, 1.0)
    return np.where(value <= 0.0031308, value * 12.92, 1.055 * value ** (1.0 / 2.4) - 0.055)


def grey_ground(bridge):
    bridge.ok("add_primitive", type="plane", name="Ground", size=400.0)
    bridge.ok("add_material", name="Grey", base_color=[GREY, GREY, GREY], roughness=1.0)
    bridge.ok("assign_material", name="Ground", material="Grey")
    bridge.ok("add_camera", name="Cam", location=[0.0, 0.0, 1.0], rotation=[0.0, 0.0, 0.0], lens=50.0)


def final(bridge, name, **extra):
    return bridge.ok("render_final", path=f"{name}.exr", **dict(QUICK, **extra))


def scene_linear(bridge, name):
    return exr_read.read_exr(os.path.join(bridge.workspace, f"{name}.exr")).stack("", "RGB")


def displayed(values):
    """Scene-linear colours through the scene's view and look, back as display-linear values, as a PNG holds them."""
    scene = bpy.context.scene
    values = np.asarray(values, dtype=np.float32)
    image = bpy.data.images.new("tone probe", len(values), 1, float_buffer=True, alpha=False)
    path = os.path.join(bpy.app.tempdir, "tone_probe.png")
    settings = scene.render.image_settings
    kept = (settings.file_format, settings.color_depth, settings.color_mode)
    try:
        pixels = np.ones((len(values), 4), dtype=np.float32)
        pixels[:, :3] = values
        image.pixels.foreach_set(pixels.ravel())
        settings.file_format, settings.color_depth, settings.color_mode = "PNG", "16", "RGB"
        image.save_render(path, scene=scene)
        loaded = bpy.data.images.load(path, check_existing=False)
        out = np.array(loaded.pixels[:]).reshape(len(values), 4)[:, :3]
        bpy.data.images.remove(loaded)
    finally:
        settings.file_format, settings.color_depth, settings.color_mode = kept
        bpy.data.images.remove(image)
    return out


def tone_error(transform, look):
    view = bpy.context.scene.view_settings
    view.use_white_balance = False
    view.exposure = 0.0
    camera_exposure.apply_view(view, transform, look)
    linear = np.array([[decode(channel) for channel in patch] for patch in COLOR_CHECKER_NEUTRALS])
    reference = linear.mean(axis=1)
    shown = displayed(linear).mean(axis=1)
    difference = encode(shown) - encode(reference)
    return float(np.sqrt(np.mean(difference ** 2))), float(np.abs(difference).max())


def test_metering_puts_a_grey_card_at_middle_grey(bridge):
    grey_ground(bridge)
    bridge.ok("sky", sun={"elevation": 40.0, "azimuth": 180.0})
    result = final(bridge, "card")
    exposure = result["exposure"]
    assert exposure["mode"] == "auto" and exposure["metering"] == "centre_weighted", exposure
    shown = float(scene_linear(bridge, "card").mean(axis=(0, 1)) @ camera_exposure.LUMINANCE) * 2.0 ** exposure["exposure"]
    assert abs(shown / GREY - 1.0) < METER_TOLERANCE, shown
    close(result["view"]["exposure"], exposure["exposure"], 1e-5)
    assert abs(bpy.context.scene.view_settings.exposure - exposure["exposure"]) > 1e-3


def test_metering_patterns_weigh_the_centre(bridge):
    weights = camera_exposure.metering_weights(240, 360, "centre_weighted")
    close(float(weights.sum()), 1.0, 1e-9)
    rows, columns = np.mgrid[0:240, 0:360]
    centre = np.hypot(rows + 0.5 - 120.0, columns + 0.5 - 180.0) <= 60.0
    close(float(weights[centre].sum()), camera_exposure.CENTRE_SHARE, 1e-9)
    frame = np.full((240, 360, 3), 0.05)
    frame[centre] = 0.8
    centre_key = camera_exposure.meter(frame, "centre_weighted")
    average_key = camera_exposure.meter(frame, "average")
    spot_key = camera_exposure.meter(frame, "spot")
    assert spot_key > centre_key > average_key
    close(spot_key, 0.8, 1e-3)


def horizon_camera(azimuth):
    """A camera at eye height looking level towards a compass azimuth: half sky, half ground, a typical scene."""
    scene = bpy.context.scene
    camera = bpy.data.objects["Cam"]
    camera.location = (0.0, 0.0, 1.6)
    camera.rotation_euler = (math.radians(90.0), 0.0, -math.radians(azimuth))
    scene.camera = camera


def test_full_sun_matches_sunny_sixteen_and_the_ev_tables(bridge):
    """The tables give the exposure of the subject in each light; just after sunset it is the glowing western sky."""
    grey_ground(bridge)
    found = {}
    for name, sun in (("full sun", {"elevation": 55.0, "azimuth": 180.0}), ("before sunset", {"elevation": 6.0, "azimuth": 265.0})):
        bridge.ok("sky", sun=sun)
        found[name] = final(bridge, name.replace(" ", "_"))["exposure"]["ev100"]
    bridge.ok("weather", preset="overcast", form="sheet", haze=False)
    found["overcast"] = final(bridge, "overcast")["exposure"]["ev100"]
    bridge.ok("weather", preset="clear", sun={"elevation": -1.5, "azimuth": 275.0}, haze=False)
    horizon_camera(275.0)
    found["after sunset"] = final(bridge, "after_sunset")["exposure"]["ev100"]
    assert abs(found["full sun"] - SUNNY_SIXTEEN) <= SUNNY_TOLERANCE, found
    tables = {"full sun": (15.0, 15.0), "overcast": (12.0, 13.0), "before sunset": (12.0, 14.0), "after sunset": (9.0, 11.0)}
    for name, (low, high) in tables.items():
        assert low - TABLE_TOLERANCE <= found[name] <= high + TABLE_TOLERANCE, (name, found)


def test_tone_response_matches_the_color_checker(bridge):
    rms, worst = tone_error(camera_exposure.CAMERA_VIEW_TRANSFORM, camera_exposure.CAMERA_LOOK)
    assert rms < TONE_RMS and worst < TONE_WORST, (rms, worst)
    flat, _ = tone_error("AgX", "none")
    assert flat > TONE_RMS, flat
    others = {look: tone_error("AgX", look)[0] for look in ("very_high_contrast", "medium_high_contrast", "base_contrast", "punchy")}
    assert all(rms <= value for value in others.values()), (rms, others)
    camera_exposure.apply_view(bpy.context.scene.view_settings, camera_exposure.CAMERA_VIEW_TRANSFORM, camera_exposure.CAMERA_LOOK)
    ramp = displayed([[GREY * 2.0 ** stops] * 3 for stops in (2.0, HIGHLIGHT_STOPS)]).mean(axis=1)
    assert ramp[0] < 0.99 and ramp[1] > HIGHLIGHT_LEVEL, ramp


def test_white_balance_neutralises_a_grey_card(bridge):
    grey_ground(bridge)
    scene = bpy.context.scene
    for name, call in (("sun", ("sky", {"sun": {"elevation": 55.0, "azimuth": 180.0}})),
                       ("low sun", ("sky", {"sun": {"elevation": 4.0, "azimuth": 265.0}})),
                       ("overcast", ("weather", {"preset": "overcast", "form": "sheet", "haze": False}))):
        bridge.ok(call[0], **call[1])
        light = sky_world.illuminant(scene)
        card = GREY * np.asarray(light["rgb"]) / float(np.asarray(light["rgb"]) @ camera_exposure.LUMINANCE)
        view = scene.view_settings
        view.exposure = 0.0
        balanced = displayed([card])[0]
        assert np.ptp(balanced) / balanced.mean() < NEUTRAL_TOLERANCE, (name, balanced)
        if name == "low sun":
            view.use_white_balance = False
            unbalanced = displayed([card])[0]
            assert np.ptp(unbalanced) / unbalanced.mean() > TINTED, unbalanced
            view.use_white_balance = True
    cct = camera_exposure.correlated_temperature([1.0, 1.0, 1.0])
    assert abs(cct - 6504.0) < 50.0, cct


def test_explicit_settings_override_the_camera(bridge):
    grey_ground(bridge)
    bridge.ok("sky", sun={"elevation": 40.0, "azimuth": 180.0})
    bridge.ok("camera_setup", name="Cam", exposure=1.25, view_transform="Standard", white_balance="tungsten")
    result = final(bridge, "manual")
    assert result["exposure"] == camera_exposure.manual_report(1.25), result["exposure"]
    assert result["view"]["view_transform"] == "Standard" and result["view"]["look"] == "None", result["view"]
    close(result["white_balance"]["temperature"], camera_exposure.WHITE_BALANCE_PRESETS["tungsten"], 1.0)
    view = bpy.context.scene.view_settings
    view.view_transform, view.look = "AgX", "AgX - Punchy"
    camera_exposure.set_explicit(bpy.context.scene, white_balance={"mode": "off"})
    bridge.ok("camera_setup", name="Cam", metering="spot", exposure_compensation=0.5)
    metered = final(bridge, "spot")["exposure"]
    assert metered["metering"] == "spot" and metered["compensation"] == 0.5, metered
    assert (view.view_transform, view.look) == ("AgX", "AgX - Punchy")
    bridge.refuse("camera_setup", "bad_args", name="Cam", exposure=0.0, metering="average")


run(globals())
