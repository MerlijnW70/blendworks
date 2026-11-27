import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from view_helpers import look_down, render, white_world

from blendworks_bridge import exr_read, view_surfaces

CLOUD_RATIO_TOLERANCE = 0.03
CLOUD_SHADOW_DROP = 0.02
INSIDE_ALPHA = 0.99
OUTSIDE_ALPHA = 0.01
DISC = 0.35


def ground_under_clouds(bridge):
    bridge.ok("add_primitive", type="plane", name="Ground", size=9000.0)
    bridge.ok("add_material", name="Grey", base_color=[0.3, 0.3, 0.3], roughness=1.0)
    bridge.ok("assign_material", name="Ground", material="Grey")
    bridge.ok("add_camera", name="Top", location=[0.0, 0.0, 400.0], rotation=[0.0, 0.0, 0.0], orthographic_scale=6000.0)
    bpy.data.objects["Top"].data.clip_end = 100_000.0
    bridge.ok("sky", sun={"elevation": 70.0, "azimuth": 180.0}, exposure="keep")


def brightness(bridge, name, shading):
    image, _ = render(bridge, name, shading=shading, camera="Top", width=64, height=64, samples=8)
    return float(image.mean())


def test_clouds_shade_clay_ground_as_much_as_shaded_ground(bridge):
    ground_under_clouds(bridge)
    clear = {shading: brightness(bridge, f"clear_{shading}", shading) for shading in ("shaded", "clay")}
    bridge.ok("clouds", layers=[{"genus": "cumulus", "coverage": 0.5, "thickness": 600.0, "seed": 2}], form="sheet", radius=6000.0, bounces=1)
    shadows = [obj for obj in bpy.context.scene.objects if obj.get("blendworks_weather") == "cloud_shadow"]
    assert shadows and not shadows[0].visible_camera
    cloudy = {shading: brightness(bridge, f"cloudy_{shading}", shading) for shading in ("shaded", "clay")}
    ratios = {shading: cloudy[shading] / clear[shading] for shading in clear}
    assert ratios["shaded"] < 1.0 - CLOUD_SHADOW_DROP, ratios
    assert abs(ratios["clay"] - ratios["shaded"]) < CLOUD_RATIO_TOLERANCE, ratios


def leaf_card(bridge):
    """A card whose material cuts a disc out of it with an alpha mask, as leaf cards cut their leaf."""
    bridge.ok("add_primitive", type="plane", name="Card", size=2.0)
    material = bpy.data.materials.new("Leaf")
    tree = material.node_tree
    shader = tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (0.1, 0.6, 0.1, 1.0)
    coordinates = tree.nodes.new("ShaderNodeTexCoord")
    distance = tree.nodes.new("ShaderNodeVectorMath")
    distance.operation = "DISTANCE"
    distance.inputs[1].default_value = (0.5, 0.5, 0.0)
    inside = tree.nodes.new("ShaderNodeMath")
    inside.operation = "LESS_THAN"
    inside.inputs[1].default_value = DISC
    tree.links.new(coordinates.outputs["UV"], distance.inputs[0])
    tree.links.new(distance.outputs["Value"], inside.inputs[0])
    tree.links.new(inside.outputs[0], shader.inputs["Alpha"])
    bpy.data.objects["Card"].data.materials.append(material)
    white_world(bridge)
    look_down("Top", 5.0, 64, ortho_scale=2.0)


def test_an_alpha_masked_leaf_card_keeps_its_shape_in_every_view(bridge):
    leaf_card(bridge)
    size = 64
    pixels = (np.arange(size) + 0.5) / size
    x, y = np.meshgrid(pixels, pixels)
    radius = np.hypot(x - 0.5, y - 0.5)
    inside, outside = radius < DISC - 0.05, radius > DISC + 0.05
    for shading in ("shaded", "clay", "wireframe", "normals"):
        render(bridge, f"card_{shading}", shading=shading, width=size, height=size, samples=16, transparent=True)
        alpha = exr_read.read_exr(os.path.join(bridge.workspace, f"card_{shading}.exr")).channel("A")
        assert float(alpha[inside].min()) > INSIDE_ALPHA, (shading, float(alpha[inside].min()))
        assert float(alpha[outside].max()) < OUTSIDE_ALPHA, (shading, float(alpha[outside].max()))


def test_views_keep_volumes_as_they_are(bridge):
    bridge.ok("add_primitive", type="plane", name="Floor", size=12.0)
    bridge.ok("add_light", type="sun", name="Sun", rotation=[30.0, 0.0, 20.0], energy=3.0)
    look_down("Top", 6.0, 48)
    white_world(bridge, 0.5)
    plain = {shading: render(bridge, f"plain_{shading}", shading=shading, width=48, height=48)[0] for shading in ("shaded", "clay")}
    bridge.ok("add_primitive", type="cube", name="FogBox", size=4.0, location=[0.0, 0.0, 2.5])
    fog = bpy.data.materials.new("Fog")
    tree = fog.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    absorption = tree.nodes.new("ShaderNodeVolumeAbsorption")
    absorption.inputs["Density"].default_value = 0.4
    tree.links.new(absorption.outputs[0], output.inputs["Volume"])
    bpy.data.objects["FogBox"].data.materials.append(fog)
    assert view_surfaces.volume_only(fog)
    foggy = {shading: render(bridge, f"fog_{shading}", shading=shading, width=48, height=48)[0] for shading in ("shaded", "clay")}
    ratios = {shading: float(foggy[shading].mean() / plain[shading].mean()) for shading in plain}
    assert ratios["shaded"] < 0.7, ratios
    assert abs(ratios["clay"] - ratios["shaded"]) < CLOUD_RATIO_TOLERANCE, ratios


run(globals())
