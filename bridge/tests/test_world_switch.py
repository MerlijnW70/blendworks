import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import close, run
from sky_helpers import fisheye_directions, fisheye_up, render

SIZE = 48
UNIFORM_SPREAD = 1e-3


def rgbe(red, green, blue):
    brightest = max(red, green, blue)
    mantissa, exponent = math.frexp(brightest)
    scale = mantissa * 256.0 / brightest
    return bytes((int(red * scale), int(green * scale), int(blue * scale), exponent + 128))


def striped_hdr(path):
    width, height = 16, 8
    header = f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {height} +X {width}\n".encode("ascii")
    rows = [b"".join(rgbe(*((4.0, 0.5, 0.2) if column % 4 < 2 else (0.1, 0.4, 3.0))) for column in range(width)) for _ in range(height)]
    with open(path, "wb") as handle:
        handle.write(header + b"".join(rows))


def background(bridge, name):
    pixels = render(bridge, name, SIZE, 1, "Up")
    _, _, inside = fisheye_directions(SIZE)
    return pixels[inside]


def assert_uniform(pixels, colour):
    spread = float(np.abs(pixels - pixels.mean(axis=0)).max())
    assert spread <= UNIFORM_SPREAD, spread
    close(list(pixels.mean(axis=0)), colour, 1e-3)


def assert_varied(pixels):
    assert float(pixels.std(axis=0).max()) > 0.01, pixels.std(axis=0)


def test_set_world_after_an_hdri_or_a_sky_shows_only_its_colour(bridge):
    fisheye_up(bridge)
    striped_hdr(os.path.join(bridge.workspace, "stripes.hdr"))
    bridge.ok("set_world_hdri", path="stripes.hdr")
    assert_varied(background(bridge, "hdri"))
    result = bridge.ok("set_world", color=[0.2, 0.3, 0.4], strength=1.0)
    assert result["replaced"]["background"] == "image" and result["replaced"]["images"] == ["stripes.hdr"]
    assert_uniform(background(bridge, "after_hdri"), [0.2, 0.3, 0.4])
    bridge.ok("sky", sun={"elevation": 30.0, "azimuth": 90.0}, exposure="keep")
    assert_varied(background(bridge, "sky"))
    result = bridge.ok("set_world", color=[0.5, 0.1, 0.1], strength=2.0)
    assert result["replaced"]["background"] == "sky" and result["replaced"]["objects"] == ["Sun"]
    assert_uniform(background(bridge, "after_sky"), [1.0, 0.2, 0.2])
    assert not any(obj.type == "LIGHT" for obj in bpy.context.scene.objects)


def test_set_world_keeps_the_colour_when_given_only_strength(bridge):
    bridge.ok("set_world", color=[0.1, 0.2, 0.3], strength=0.5)
    result = bridge.ok("set_world", strength=2.0)
    close(result["color"], [0.1, 0.2, 0.3])
    assert result["replaced"]["background"] == "colour"


def test_switching_in_any_order_shows_only_the_last(bridge):
    fisheye_up(bridge)
    striped_hdr(os.path.join(bridge.workspace, "stripes.hdr"))
    bridge.ok("sky", sun={"elevation": 30.0, "azimuth": 90.0}, exposure="keep")
    sky_alone = background(bridge, "sky_alone")
    result = bridge.ok("set_world_hdri", path="stripes.hdr")
    assert result["replaced"]["background"] == "sky"
    hdri = background(bridge, "hdri_after_sky")
    nodes = {node.type for node in bpy.context.scene.world.node_tree.nodes}
    assert "TEX_SKY" not in nodes and "TEX_ENVIRONMENT" in nodes
    assert not any(obj.type == "LIGHT" for obj in bpy.context.scene.objects)
    result = bridge.ok("sky", sun={"elevation": 30.0, "azimuth": 90.0}, exposure="keep")
    assert result["replaced"]["background"] == "image"
    again = background(bridge, "sky_after_hdri")
    nodes = {node.type for node in bpy.context.scene.world.node_tree.nodes}
    assert "TEX_ENVIRONMENT" not in nodes
    close(list(again.mean(axis=0)), list(sky_alone.mean(axis=0)), 1e-4)
    assert float(np.abs(again.mean(axis=0) - hdri.mean(axis=0)).max()) > 0.01


def test_world_switches_keep_the_atmosphere_volume(bridge):
    bridge.ok("set_world", color=[0.2, 0.2, 0.2], strength=1.0)
    bridge.ok("atmosphere", visibility=500.0, domain="world")
    bridge.ok("sky", sun={"elevation": 30.0, "azimuth": 90.0}, exposure="keep")
    tree = bpy.context.scene.world.node_tree
    assert tree.nodes.get("Atmosphere Scatter") is not None
    output = next(node for node in tree.nodes if node.type == "OUTPUT_WORLD")
    assert output.inputs["Volume"].is_linked


def test_new_scene_leaves_a_clean_default_world(bridge):
    striped_hdr(os.path.join(bridge.workspace, "stripes.hdr"))
    bridge.ok("set_world_hdri", path="stripes.hdr")
    bridge.ok("sky", sun={"elevation": 10.0, "azimuth": 90.0})
    bridge.ok("clouds", layers=[{"genus": "cumulus"}], form="sheet")
    result = bridge.ok("new_scene")
    assert result["replaced"]["background"] == "sky_clouds"
    world = bpy.context.scene.world
    assert world.name == "World" and len(bpy.data.worlds) == 1
    assert world.get("blendworks_sky") is None and world.get("blendworks_clouds") is None
    types = sorted(node.type for node in world.node_tree.nodes)
    assert types == ["BACKGROUND", "OUTPUT_WORLD"], types
    background_node = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    close(list(background_node.inputs["Color"].default_value[:3]), [0.050876] * 3, 1e-5)
    assert background_node.inputs["Strength"].default_value == 1.0
    assert bpy.context.scene.view_settings.exposure == 0.0
    assert len(bpy.context.scene.objects) == 0
    assert not any(image.name == "stripes.hdr" for image in bpy.data.images)
    fisheye_up(bridge)
    assert_uniform(background(bridge, "fresh"), [0.050876] * 3)


run(globals())
