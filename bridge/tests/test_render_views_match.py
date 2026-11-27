import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from view_helpers import QUICK, channels, render, white_world

from blendworks_bridge.commands import render_final

SIZE = 96
NORMALS_MEAN_TOLERANCE = 0.01
NORMALS_EDGE_SHARE = 0.03
TOP_FACE = (0.5, 0.5, 1.0)
EMISSION = (0.25, 0.5, 0.75)


def solids(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0, location=[0.0, 3.0, 0.0], rotation=[0.0, 0.0, 30.0])
    bridge.ok("add_primitive", type="sphere", name="Ball", radius=0.5, location=[1.3, 3.0, 0.0])
    bridge.ok("add_light", type="sun", name="Sun", rotation=[50.0, 0.0, 20.0], energy=3.0)
    bridge.ok("add_camera", name="Cam", location=[0.0, -1.0, 3.0], rotation=[60.0, 0.0, 0.0])
    bridge.ok("camera_setup", name="Cam", focal_length=50.0)
    white_world(bridge, 0.5)


def preview_pixels(bridge, shading):
    result = bridge.ok("render_preview", camera="Cam", shading=shading, resolution=SIZE, samples=16, device="cpu")
    path = os.path.join(tempfile.mkdtemp(prefix="blendworks-views-"), "preview.png")
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(result["images"][0]["data"]))
    image = bpy.data.images.load(path, check_existing=False)
    try:
        image.colorspace_settings.name = "Non-Color"
        values = np.empty(SIZE * SIZE * 4, dtype=np.float32)
        image.pixels.foreach_get(values)
    finally:
        bpy.data.images.remove(image)
    return np.flipud(values.reshape(SIZE, SIZE, 4))[..., :3]


def test_normals_match_the_preview_and_the_known_colour_of_an_upward_face(bridge):
    solids(bridge)
    bridge.ok("transform", name="Box", rotation=[0.0, 0.0, 0.0], location=[0.0, 3.0, 0.0])
    previewed = preview_pixels(bridge, "normals")
    final = bridge.ok("render_final", path="normals.png", shading="normals", **dict(QUICK, width=SIZE, height=SIZE, samples=16))
    assert final["shading"] == "normals" and final["denoise"] is None
    image = bpy.data.images.load(os.path.join(bridge.workspace, "normals.png"), check_existing=False)
    try:
        image.colorspace_settings.name = "Non-Color"
        values = np.empty(SIZE * SIZE * 4, dtype=np.float32)
        image.pixels.foreach_get(values)
    finally:
        bpy.data.images.remove(image)
    rendered = np.flipud(values.reshape(SIZE, SIZE, 4))[..., :3]
    difference = np.abs(rendered - previewed)
    assert float(difference.mean()) < NORMALS_MEAN_TOLERANCE, float(difference.mean())
    assert float((difference.max(axis=-1) > 0.1).mean()) < NORMALS_EDGE_SHARE
    assert float(rendered.std()) > 0.05
    linear, _ = render(bridge, "normals_linear", shading="normals", width=SIZE, height=SIZE)
    upward = linear[linear[..., 2] > 0.999]
    assert len(upward) > 20
    assert float(np.abs(upward.mean(axis=0) - np.array(TOP_FACE)).max()) < 0.04


def emissive_card(bridge):
    bridge.ok("add_primitive", type="plane", name="Card", size=40.0, location=[0.0, 5.0, 0.0], rotation=[90.0, 0.0, 0.0])
    bridge.ok("add_material", name="Lamp", base_color=[0.0, 0.0, 0.0], roughness=1.0, emission_color=list(EMISSION), emission_strength=1.0)
    bridge.ok("assign_material", name="Card", material="Lamp")
    bridge.ok("add_camera", name="Cam", location=[0.0, 0.0, 0.0], rotation=[90.0, 0.0, 0.0])
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)
    bridge.ok("camera_setup", name="Cam", view_transform="Standard")


def png_pixels(path):
    image = bpy.data.images.load(path, check_existing=False)
    try:
        values = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(values)
    finally:
        bpy.data.images.remove(image)
    return values


def shaded_outputs(bridge, name):
    """What a shaded render writes: the scene-linear .exr, the display-referred .png and the view it reports."""
    exr = bridge.ok("render_final", path=f"{name}.exr", **dict(QUICK, width=SIZE, height=SIZE))
    png = bridge.ok("render_final", path=f"{name}.png", **dict(QUICK, width=SIZE, height=SIZE))
    assert exr["shading"] == png["shading"] == "shaded"
    view = bpy.context.scene.view_settings
    settings = (view.view_transform, view.look, view.exposure, view.gamma)
    return channels(bridge, f"{name}.exr"), png_pixels(os.path.join(bridge.workspace, f"{name}.png")), png["view"], settings


def test_shaded_is_what_it_was_and_clay_replaces_it(bridge):
    emissive_card(bridge)
    view = bpy.context.scene.view_settings
    view.view_transform, view.look, view.exposure, view.gamma = "AgX", "AgX - Punchy", 0.25, 1.125
    default = shaded_outputs(bridge, "plain")
    assert np.abs(default[0] - np.array(EMISSION)).max() < 1e-3
    assert float(default[1].std()) > 0.0
    explicit, _ = render(bridge, "explicit", shading="shaded", width=SIZE, height=SIZE)
    assert np.array_equal(default[0], explicit)

    original = render_final.render_view.RenderView

    class Absent:
        """render_final as it was before views: nothing around the render."""

        def __init__(self, *arguments, **keywords):
            self.report = {}

        def __enter__(self):
            return self

        def __exit__(self, kind, error, trace):
            return False

    render_final.render_view.RenderView = Absent
    try:
        reference = shaded_outputs(bridge, "reference")
    finally:
        render_final.render_view.RenderView = original
    assert np.array_equal(default[0], reference[0])
    assert np.array_equal(default[1], reference[1])
    assert default[2] == reference[2] and default[3] == reference[3] == ("AgX", "AgX - Punchy", 0.25, 1.125)
    clay, _ = render(bridge, "clay", shading="clay", width=SIZE, height=SIZE)
    assert float(clay.max()) < 1e-3


run(globals())
