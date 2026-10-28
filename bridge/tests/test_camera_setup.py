import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from final_helpers import EXACT, camera_on_y, card, edge_sharpness, emissive, linear, png_linear, split_card
from harness import close, run

from blendworks_bridge import camera_exposure

NEAR = 2.0
FAR = 8.0
LENS = 85.0
VIEW = 36.0 / LENS
SIZE = 128


def two_edges(bridge):
    near_width = VIEW * NEAR
    far_width = VIEW * FAR
    split_card(bridge, "Near", NEAR, near_width * 1.2, z=near_width / 4.0)
    for part in ("Near_white", "Near_black"):
        bridge.ok("transform", name=part, scale=[near_width * 0.6, near_width / 2.0, 1.0])
    split_card(bridge, "Far", FAR, far_width * 1.2, z=-far_width / 4.0)
    for part in ("Far_white", "Far_black"):
        bridge.ok("transform", name=part, scale=[far_width * 0.6, far_width / 2.0, 1.0])
    camera_on_y(bridge, lens=LENS)


def sharpness(bridge, name, **camera):
    if camera:
        bridge.ok("camera_setup", name="Cam", **camera)
    bridge.ok("render_final", path=f"{name}.exr", width=SIZE, height=SIZE, samples=64, **EXACT)
    image = linear(bridge, f"{name}.exr")
    near = edge_sharpness(image[SIZE // 16 : SIZE * 3 // 8])
    far = edge_sharpness(image[SIZE * 5 // 8 : SIZE * 15 // 16])
    return near, far


def test_depth_of_field_keeps_the_focus_sharp_and_blurs_the_rest(bridge):
    two_edges(bridge)
    plain_near, plain_far = sharpness(bridge, "plain")
    near_focus = sharpness(bridge, "near_focus", fstop=1.2, focus_distance=NEAR)
    far_focus = sharpness(bridge, "far_focus", fstop=1.2, focus_object="Far_white")
    print(f"edge sharpness: no dof {plain_near:.3f}/{plain_far:.3f}, focus near {near_focus[0]:.3f}/{near_focus[1]:.3f}, "
          f"focus far {far_focus[0]:.3f}/{far_focus[1]:.3f}")
    assert abs(plain_near / plain_far - 1.0) < 0.15, (plain_near, plain_far)
    assert near_focus[0] / near_focus[1] > 3.0, near_focus
    assert far_focus[1] / far_focus[0] > 3.0, far_focus
    assert near_focus[0] > 0.8 * plain_near and far_focus[1] > 0.8 * plain_far
    bridge.ok("camera_setup", name="Cam", depth_of_field=False)
    assert sharpness(bridge, "off")[1] > 0.8 * plain_far


def test_the_camera_report_gives_the_sharp_range_by_hand(bridge):
    camera_on_y(bridge, lens=50.0)
    result = bridge.ok("camera_setup", name="Cam", fstop=2.0, focus_distance=10.0, sensor_width=36.0)
    dof = result["depth_of_field"]
    circle = 0.036 / 1500.0
    hyperfocal = 0.05 * 0.05 / (2.0 * circle) + 0.05
    close(dof["sharp_range"]["hyperfocal"], hyperfocal, 1e-5)
    close(dof["sharp_range"]["near"], 10.0 * (hyperfocal - 0.05) / (hyperfocal + 10.0 - 0.1), 1e-5)
    close(dof["sharp_range"]["far"], 10.0 * (hyperfocal - 0.05) / (hyperfocal - 10.0), 1e-5)
    data = bpy.data.objects["Cam"].data
    assert data.dof.use_dof and data.dof.focus_object is None and data.dof.aperture_fstop == 2.0
    moved = bridge.ok("camera_setup", name="Cam", focal_length=35.0, shift_x=0.1, aperture_blades=6, aperture_rotation=30.0)
    assert moved["focal_length"] == 35.0 and moved["shift"] == [0.1, 0.0] and moved["depth_of_field"]["blades"] == 6
    close(math.degrees(data.dof.aperture_rotation), 30.0)


def exposure_scene(bridge):
    card(bridge, "Wall", (0.0, 3.0, 0.0), 4.0, 4.0, emissive(bridge, "grey", 0.18))
    camera_on_y(bridge)
    bridge.ok("camera_setup", name="Cam", view_transform="Standard", look="none")


def mean_luminance(bridge, name, **settings):
    bridge.ok("camera_setup", name="Cam", **settings)
    bridge.ok("render_final", path=f"{name}.png", width=32, height=32, samples=4, depth=16, **EXACT)
    return float(png_linear(bridge, f"{name}.png")[4:28, 4:28].mean())


def test_exposure_changes_the_luminance_by_the_predicted_factor_per_ev(bridge):
    exposure_scene(bridge)
    base = {"shutter": 1.0 / 125.0, "iso": 100.0, "aperture": 4.0, "reference_ev": 10.0}
    reference = mean_luminance(bridge, "base", physical=base)
    cases = {
        "shutter": dict(base, shutter=1.0 / 250.0),
        "iso": dict(base, iso=200.0),
        "aperture": dict(base, aperture=5.6),
    }
    start = camera_exposure.ev100(4.0, 1.0 / 125.0, 100.0)
    for name, physical in cases.items():
        measured = mean_luminance(bridge, name, physical=physical) / reference
        predicted = 2.0 ** (start - camera_exposure.ev100(physical["aperture"], physical["shutter"], physical["iso"]))
        print(f"luminance per EV, {name}: measured {measured:.4f}, predicted {predicted:.4f}")
        assert abs(measured / predicted - 1.0) < 0.02, (name, measured, predicted)
    stops = bridge.ok("camera_setup", name="Cam", exposure=0.0)["view"]["exposure"]
    assert stops == 0.0
    plus_one = mean_luminance(bridge, "plus_one", exposure=1.0) / mean_luminance(bridge, "zero", exposure=0.0)
    assert abs(plus_one - 2.0) < 0.04, plus_one


def test_physical_exposure_follows_ev100(bridge):
    close(camera_exposure.ev100(16.0, 1.0 / 100.0, 100.0), math.log2(25600.0))
    close(camera_exposure.ev100(2.0, 1.0, 400.0), 0.0)
    camera_on_y(bridge)
    result = bridge.ok("camera_setup", name="Cam", fstop=2.8, physical={"shutter": 1.0 / 500.0, "iso": 200.0})
    expected = 15.0 - (math.log2(2.8 * 2.8 * 500.0) - 1.0)
    close(result["physical"]["exposure"], expected, 1e-5)
    close(bpy.context.scene.view_settings.exposure, expected, 1e-5)


def framed_square(bridge):
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)
    card(bridge, "Square", (0.0, 6.0, 0.0), 1.0, 1.0, emissive(bridge, "light", 1.0))
    camera_on_y(bridge)


def extent(bridge, name, **camera):
    """Width, height and centre (column, row) in pixels of the lit square."""
    if camera:
        bridge.ok("camera_setup", name="Cam", **camera)
    bridge.ok("render_final", path=f"{name}.exr", width=64, height=64, samples=16, **EXACT)
    image = linear(bridge, f"{name}.exr")
    level = image.max()
    columns = image.sum(axis=0) / level
    rows = image.sum(axis=1) / level
    centre = lambda profile: float((np.arange(profile.size) + 0.5) @ profile / profile.sum())
    return float(image[32].sum() / level), float(image[:, 32].sum() / level), centre(columns), centre(rows)


def test_focal_length_scales_the_image_of_an_object(bridge):
    framed_square(bridge)
    wide = extent(bridge, "wide", focal_length=50.0)
    tele = extent(bridge, "tele", focal_length=100.0)
    print(f"square width in pixels: 50 mm {wide[0]:.2f}, 100 mm {tele[0]:.2f}")
    close(wide[0], 64.0 * 1.0 / (36.0 / 50.0 * 6.0), 0.5)
    close(tele[0] / wide[0], 2.0, 0.06)
    close(tele[1] / wide[1], 2.0, 0.06)


def test_sensor_size_sets_the_field_of_view_and_leaves_the_other_side_alone(bridge):
    framed_square(bridge)
    data = bpy.data.objects["Cam"].data
    full = extent(bridge, "full", focal_length=50.0, sensor_width=36.0)
    height_before = data.sensor_height
    small = extent(bridge, "small", sensor_width=24.0)
    print(f"square width in pixels: 36 mm sensor {full[0]:.2f}, 24 mm sensor {small[0]:.2f}")
    close(small[0] / full[0], 36.0 / 24.0, 0.06)
    close(small[0], 64.0 / (24.0 / 50.0 * 6.0), 0.5)
    assert data.sensor_height == height_before
    vertical = extent(bridge, "vertical", sensor_fit="vertical", sensor_height=12.0)
    close(vertical[1], 64.0 / (12.0 / 50.0 * 6.0), 0.5)
    again = extent(bridge, "vertical_wide", sensor_width=40.0)
    close(again[1], vertical[1], 0.3)
    assert data.sensor_height == 12.0 and bridge.ok("camera_setup", name="Cam", focal_length=50.0)["sensor_height"] == 12.0


def test_lens_shift_moves_the_image_by_frame_widths(bridge):
    framed_square(bridge)
    centred = extent(bridge, "centred", focal_length=50.0)
    shifted = extent(bridge, "shifted", shift_x=0.25, shift_y=-0.125)
    print(f"square centre: {centred[2:]} -> {shifted[2:]}")
    close(centred[2], 32.0, 0.3)
    close(centred[3], 32.0, 0.3)
    close(shifted[2] - centred[2], -0.25 * 64.0, 0.5)
    close(shifted[3] - centred[3], -0.125 * 64.0, 0.5)


def test_physical_exposure_uses_the_camera_fstop_also_with_depth_of_field_off(bridge):
    camera_on_y(bridge)
    bridge.ok("camera_setup", name="Cam", fstop=4.0)
    bridge.ok("camera_setup", name="Cam", depth_of_field=False)
    assert not bpy.data.objects["Cam"].data.dof.use_dof
    result = bridge.ok("camera_setup", name="Cam", physical={"shutter": 1.0 / 125.0, "iso": 100.0})
    expected = 15.0 - camera_exposure.ev100(4.0, 1.0 / 125.0, 100.0)
    close(result["physical"]["exposure"], expected, 1e-5)
    close(result["physical"]["aperture"], 4.0, 1e-9)
    close(bpy.context.scene.view_settings.exposure, expected, 1e-5)


def test_view_transform_and_look_default_and_validate(bridge):
    camera_on_y(bridge)
    fresh = bpy.data.scenes.new("fresh")
    try:
        defaults = (fresh.view_settings.view_transform, fresh.view_settings.look, fresh.view_settings.exposure)
    finally:
        bpy.data.scenes.remove(fresh)
    assert defaults == (camera_exposure.DEFAULT_VIEW_TRANSFORM, "None", 0.0)
    view = bpy.context.scene.view_settings
    result = bridge.ok("camera_setup", name="Cam", view_transform="AgX", look="punchy")
    assert result["view"]["look"] == "AgX - Punchy"
    bridge.ok("camera_setup", name="Cam", view_transform="Standard", look="none")
    assert (view.view_transform, view.look) == ("Standard", "None")
    bridge.refuse("camera_setup", "bad_args", name="Cam", view_transform="Standard", look="high_contrast")
    assert (view.view_transform, view.look) == ("Standard", "None")


def test_camera_setup_refuses_bad_settings(bridge):
    camera_on_y(bridge)
    bridge.ok("add_light", type="point", name="Lamp")
    bridge.refuse("camera_setup", "bad_args", name="Cam")
    bridge.refuse("camera_setup", "bad_args", name="Lamp", fstop=2.0)
    bridge.refuse("camera_setup", "not_found", name="Ghost", fstop=2.0)
    bridge.refuse("camera_setup", "bad_args", name="Cam", focus_distance=2.0, focus_object="Lamp")
    bridge.refuse("camera_setup", "bad_args", name="Cam", exposure=1.0, physical={"shutter": 0.01})
    bridge.refuse("camera_setup", "bad_args", name="Cam", depth_of_field=False, fstop=2.0)
    bridge.refuse("camera_setup", "bad_args", name="Cam", aperture_blades=2)
    bridge.refuse("camera_setup", "bad_args", name="Cam", clip_start=5.0, clip_end=1.0)


run(globals())
