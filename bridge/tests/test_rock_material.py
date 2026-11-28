import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from rock_render_helpers import LUMINANCE, mineral_statistics, ortho_camera, render_passes

from blendworks_bridge import liquid_world, rock_lithology, weather_wet

GRANITE = {"grain_mm": (1.0, 5.0), "colour_index": (0.05, 0.2), "contrast": (3.0, 100.0)}
LITHOLOGY_LUMINANCE = {"sandstone": (0.15, 0.45), "limestone": (0.3, 0.55), "basalt": (0.03, 0.1)}
WET_DARKER_AT_MOST = 0.65
WET_GLOSSIER_AT_LEAST = 4.0
TOP_OVER_BOTTOM = 4.0
BEDDING_AT_LEAST = 2.0


def slab(bridge, params, size=0.4):
    bridge.ok("add_primitive", type="plane", name="Slab", size=size)
    bridge.ok("material_procedural", name="Rock", stone=dict({"rind": 0.0, "lichen": 0.0, "moss": 0.0}, **params))
    bridge.ok("assign_material", name="Slab", material="Rock")


def albedo(channels):
    return np.stack([channels[f"Diffuse Color.{axis}"] for axis in "RGB"], axis=-1)


def test_granite_has_the_grain_size_colour_index_and_contrast_of_granite(bridge):
    """The colour of fresh granite seen from above at 0.39 mm per pixel, measured as a petrographer would: its grain size
    (1.5 times the mean lineal intercept) lies in the IUGS medium-grained class, 1 to 5 mm; its colour index (share of dark
    minerals) in the 5 to 20 % of a leucocratic granite (Le Maitre et al. 2002); and its pale feldspar stands at least three
    times as bright as its dark biotite (90th over 5th percentile), as their reflectances differ (Kokaly et al. 2017).
    Proven by doubling both grain sizes (the grain then reads above 5 mm) and by a biotite share of 0.7 (colour index
    above 20 %)."""
    slab(bridge, {"lithology": "granite"})
    ortho_camera("Top", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 0.2, 512)
    measured = mineral_statistics(albedo(render_passes(bridge.workspace, "granite", diffuse_color=True)), 200.0 / 512)
    for key, (low, high) in GRANITE.items():
        assert low <= measured[key] <= high, (key, measured)


def side_slab(bridge, params):
    bridge.ok("mesh_from_data", name="Slab", vertices=[[-0.2, 0.0, -0.2], [0.2, 0.0, -0.2], [0.2, 0.0, 0.2], [-0.2, 0.0, 0.2]], faces=[[0, 1, 2, 3]])
    bridge.ok("material_procedural", name="Rock", stone=dict({"rind": 0.0, "lichen": 0.0, "moss": 0.0}, **params))
    bridge.ok("assign_material", name="Slab", material="Rock")


def test_each_lithology_has_its_brightness_and_sandstone_its_beds(bridge):
    """Mean albedo of each rock type within its cited range (docs/research/rock-realism.md), and sandstone seen from the side banded along its
    beds: the rows (along the bedding) vary at least BEDDING_AT_LEAST times as much as the columns. Proven by giving basalt
    the granite colour and by turning the beds off (bed and lamina terms at zero)."""
    for lithology, (low, high) in LITHOLOGY_LUMINANCE.items():
        bridge.ok("new_scene")
        side_slab(bridge, {"lithology": lithology})
        ortho_camera("Side", (0.0, -1.0, 0.0), (90.0, 0.0, 0.0), 0.3, 192)
        colour = albedo(render_passes(bridge.workspace, lithology, diffuse_color=True))
        luminance = colour @ LUMINANCE
        assert low <= luminance.mean() <= high, (lithology, luminance.mean())
        if lithology == "sandstone":
            rows, columns = luminance.mean(axis=1), luminance.mean(axis=0)
            assert rows.std() > BEDDING_AT_LEAST * columns.std(), (rows.std(), columns.std())


def test_lichen_covers_exposed_tops_and_spares_undersides(bridge):
    """A sphere of granite with lichen 0.5, seen from the side: the lichen AOV over the upper fifth is at least TOP_OVER_BOTTOM
    times its mean over the lower half and there is lichen on the top. Proven by dropping the exposure from the founding
    chance (the halves then match)."""
    bridge.ok("add_primitive", type="sphere", name="Boulder", radius=0.5, segments=64, rings=32)
    bridge.ok("material_procedural", name="Rock", stone={"lithology": "granite", "lichen": 0.5, "moss": 0.0})
    bridge.ok("assign_material", name="Boulder", material="Rock")
    bridge.ok("shade_smooth", name="Boulder")
    ortho_camera("Side", (0.0, -3.0, 0.0), (90.0, 0.0, 0.0), 1.1, 160)
    lichen = render_passes(bridge.workspace, "lichen", aovs=("rock_lichen",))["rock_lichen.X"]
    rows = lichen.shape[0]
    image_top = lichen[: int(0.4 * rows)]
    image_bottom = lichen[int(0.6 * rows):]
    assert image_top.mean() > 0.03, image_top.mean()
    assert image_top.mean() > TOP_OVER_BOTTOM * image_bottom.mean(), (image_top.mean(), image_bottom.mean())


def wet_scene(bridge, wet):
    bridge.ok("new_scene")
    slab(bridge, {"lithology": "granite"}, size=1.0)
    mesh = bpy.data.objects["Slab"].data
    for name, value in ((liquid_world.WET_ATTRIBUTE, wet), (liquid_world.DEPTH_ATTRIBUTE, -0.2)):
        attribute = mesh.attributes.new(name, "FLOAT", "POINT")
        attribute.data.foreach_set("value", np.full(len(mesh.vertices), value, dtype=np.float32))
    weather_wet.apply_shore(bpy.data.materials["Rock"], liquid_world.WET_ATTRIBUTE, liquid_world.DEPTH_ATTRIBUTE)
    bridge.ok("add_light", type="sun", name="Sun", rotation=[45.0, 0.0, 0.0], energy=3.0)
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)
    ortho_camera("Mirror", (0.0, 1.0, 1.0), (45.0, 0.0, 180.0), 0.5, 64)
    layer = bpy.context.view_layer
    layer.use_pass_glossy_direct = layer.use_pass_diffuse_direct = True
    channels = render_passes(bridge.workspace, f"wet{wet}", diffuse_color=True, samples=16)
    glossy = np.stack([channels[f"Glossy Direct.{axis}"] for axis in "RGB"], axis=-1) @ LUMINANCE
    diffuse = np.stack([channels[f"Diffuse Direct.{axis}"] for axis in "RGB"], axis=-1) @ LUMINANCE
    return float((albedo(channels) @ LUMINANCE).mean()), float(glossy.mean()), float(diffuse.mean())


def test_wet_rock_is_darker_and_glossier_and_dry_rock_is_matte(bridge):
    """The same granite dry and wet through the shore wetting (liquid_wet 1) under a sun seen at the mirror angle: wet albedo
    at most WET_DARKER_AT_MOST of dry (Lekner and Dorf: rock of albedo 0.25 under a water film keeps about 0.56 of it) and wet
    specular light at least WET_GLOSSIER_AT_LEAST times dry, so the specular highlight is high only where the rock is wet.
    Proven by giving dry rock a roughness of 0.3 (it then shines as much as wet rock)."""
    dry_albedo, dry_gloss, _ = wet_scene(bridge, 0.0)
    wet_albedo, wet_gloss, _ = wet_scene(bridge, 1.0)
    assert rock_lithology.wet_albedo(0.25) / 0.25 < WET_DARKER_AT_MOST
    assert wet_albedo <= WET_DARKER_AT_MOST * dry_albedo, (wet_albedo, dry_albedo)
    assert wet_gloss >= WET_GLOSSIER_AT_LEAST * dry_gloss, (wet_gloss, dry_gloss)


def test_algae_grow_under_the_water_line_and_a_mark_lies_just_above_it(bridge):
    """A slab whose liquid_depth runs from 0.3 m under water to 0.3 m above: the algae AOV is high in the deeper part and
    nil above the water, the water mark lies in the band just above the line, and a slab without liquid attributes has
    neither. Proven by dropping the presence test (the dry slab then shows a water mark everywhere)."""
    slab(bridge, {"lithology": "granite"}, size=1.0)
    bridge.ok("subdivide", name="Slab", cuts=10)
    mesh = bpy.data.objects["Slab"].data
    depth = np.array([vertex.co.y * 0.6 for vertex in mesh.vertices], dtype=np.float32)
    for name, values in ((liquid_world.DEPTH_ATTRIBUTE, depth), (liquid_world.WET_ATTRIBUTE, np.clip(1.0 + depth / 0.3, 0.0, 1.0))):
        attribute = mesh.attributes.new(name, "FLOAT", "POINT")
        attribute.data.foreach_set("value", values.astype(np.float32))
    ortho_camera("Top", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 1.0, 120)
    channels = render_passes(bridge.workspace, "water", aovs=("rock_algae", "rock_mark"))
    algae, mark = np.flipud(channels["rock_algae.X"]), np.flipud(channels["rock_mark.X"])
    along = (np.arange(120) + 0.5) / 120.0 - 0.5
    level = along * 0.6
    assert algae[level > 0.1].mean() > 0.4 and algae[level < 0.0].max() == 0.0, (algae[level > 0.1].mean(), algae[level < 0.0].max())
    band = (level < -0.005) & (level > -0.03)
    assert mark[band].mean() > 0.5 and mark[level < -0.08].max() == 0.0 and mark[level > 0.01].max() == 0.0
    bridge.ok("new_scene")
    slab(bridge, {"lithology": "granite"}, size=1.0)
    ortho_camera("Top", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 1.0, 60)
    dry = render_passes(bridge.workspace, "dry", aovs=("rock_algae", "rock_mark"))
    assert dry["rock_algae.X"].max() == 0.0 and dry["rock_mark.X"].max() == 0.0


run(globals())
