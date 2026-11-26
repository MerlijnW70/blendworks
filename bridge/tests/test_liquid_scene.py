import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from liquid_helpers import attribute, cup, dimple, mesh_points, ortho
from sky_helpers import LUMINANCE, luminance, render

from blendworks_bridge import liquid_light, liquid_render, liquid_world

GREY = [0.5, 0.5, 0.5]


def grey_ground(bridge, name):
    bridge.ok("add_material", name="Grey", base_color=GREY, roughness=0.8)
    bridge.ok("assign_material", name=name, material="Grey")


def test_ground_cover_and_scatter_stay_out_of_the_water_and_shores_get_wet(bridge):
    dimple("Ground", 6.0, 120, 1.0, 2.0)
    grey_ground(bridge, "Ground")
    pond = bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[0.0, 0.0, 0.0], name="Pond")
    assert pond["shore"]["objects"] == ["Ground"] and pond["shore"]["materials"] == ["Grey"]
    wet = attribute("Ground", liquid_world.WET_ATTRIBUTE)
    depth = attribute("Ground", liquid_world.DEPTH_ATTRIBUTE)
    assert np.all(wet[depth > 0.0] == 1.0)
    points = mesh_points("Ground")
    radius = np.hypot(points[:, 0], points[:, 1])
    assert wet[(radius > 2.4)].max() == 0.0 and wet[(radius > 1.02) & (radius < 1.1)].min() > 0.5
    bridge.ok("ground_cover", target="Ground", populations=[{"name": "stones", "element": "pebble", "density": 40.0}, {"name": "reeds", "element": "sedge", "density": 30.0, "liquid": "shore", "shore": 0.4}], seed=2)
    water = liquid_world.Water([bpy.data.objects["Pond"]])
    stones = instance_points("GroundCover_stones")
    reeds = instance_points("GroundCover_reeds")
    assert len(stones) > 500 and len(reeds) > 20
    assert np.all(water.signed_depth(stones) < 0.0)
    reed_depth = water.signed_depth(reeds)
    assert np.all(reed_depth < 0.0) and np.all(reed_depth > -0.45)
    bridge.ok("add_primitive", type="ico_sphere", name="Rock", radius=0.05, subdivisions=1)
    scattered = bridge.ok("scatter", target="Ground", source="Rock", min_distance=0.15, density_mask=["liquid"], name="Rocks", realize=True)
    assert scattered["count"] > 50
    assert np.all(water.signed_depth(mesh_points("Rocks")) < 0.06)


def test_shore_rocks_keep_to_the_water_line_and_stand_wet_in_the_shallows(bridge):
    """The shore band holds past the reach liquid_body measured its wet band with (1 m for a pond): nothing lands far inland."""
    dimple("Ground", 12.0, 160, 1.5, 3.0)
    grey_ground(bridge, "Ground")
    bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[0.0, 0.0, 0.0], name="Pond")
    bridge.ok("add_primitive", type="ico_sphere", name="Rock", radius=0.05, subdivisions=1)
    placed = bridge.ok("scatter", target="Ground", source="Rock", min_distance=0.12, density_mask=["shore"], shore_width=2.0, shore_depth=0.15, name="ShoreRocks", realize=True, seed=3)
    assert placed["count"] > 100
    water = liquid_world.Water([bpy.data.objects["Pond"]])
    depth = water.signed_depth(mesh_points("ShoreRocks"), 20.0)
    assert depth.min() > -(2.0 + 0.15 + 0.1) and depth.max() < 0.15 + 0.05 + 0.1, (depth.min(), depth.max())
    assert (depth > 0.0).any() and (depth < -1.2).any(), "rocks stand in the shallows and reach past the old one-metre band"
    assert placed["wet"]["objects"] == ["ShoreRocks"]
    wet = attribute("ShoreRocks", liquid_world.WET_ATTRIBUTE)
    assert np.all(wet[depth > 0.0] == 1.0) and wet[depth < -1.0].max() < 0.05
    bridge.refuse("scatter", "bad_args", target="Ground", source="Rock", min_distance=0.12, shore_depth=0.1, name="Stray")


def test_ground_under_water_loses_the_wet_gloss_and_takes_a_silt_film(bridge):
    """Wet ground above the water line glints like a puddle; the same ground under half a metre of water does not (water
    hides a wet surface's gloss) and turns towards the colour of wet silt."""
    from blendworks_bridge import weather_wet

    bridge.ok("add_primitive", type="plane", name="Bed", size=2.0)
    grey_ground(bridge, "Bed")
    mesh = bpy.data.objects["Bed"].data
    xs = np.array([vertex.co.x for vertex in mesh.vertices])
    for key, values in ((liquid_world.WET_ATTRIBUTE, np.ones(len(xs))), (liquid_world.DEPTH_ATTRIBUTE, np.where(xs > 0.0, 0.6, -0.1))):
        layer = mesh.attributes.new(key, "FLOAT", "POINT")
        layer.data.foreach_set("value", values.astype(np.float32))
    assert weather_wet.apply_shore(bpy.data.materials["Grey"], liquid_world.WET_ATTRIBUTE, liquid_world.DEPTH_ATTRIBUTE)
    bridge.ok("add_light", type="sun", name="Sun", rotation=[0.0, 0.0, 0.0], energy=3.0)
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)
    ortho(bridge, "Top", (0.0, 0.0, 5.0), (0.0, 0.0, 0.0), 2.0)
    pixels = render(bridge, "silt", 64, 16, "Top")
    above, under = pixels[16:48, 4:28].reshape(-1, 3).mean(axis=0), pixels[16:48, 36:60].reshape(-1, 3).mean(axis=0)
    assert luminance(above) > 2.0 * luminance(under), ("the sun's glint off wet ground, none under water", above, under)
    bpy.data.objects["Sun"].rotation_euler = (math.radians(40.0), 0.0, 0.0)
    pixels = render(bridge, "silt_colour", 64, 16, "Top")
    under = pixels[16:48, 44:60].reshape(-1, 3).mean(axis=0)
    assert under[0] > 1.15 * under[2], ("silt brown under water, where wet grey ground stays grey (1.0)", under)


def test_a_liquid_mask_measures_again_after_the_ground_is_joined_with_more(bridge):
    """Joining fills liquid_depth with zeros for the new part (the water line); the masks see the change and measure again."""
    dimple("Ground", 6.0, 60, 1.0, 2.0)
    bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[0.0, 0.0, 0.0], name="Pond", shore_width=2.0)
    bridge.ok("add_primitive", type="plane", name="Field", size=4.0, location=[8.0, 0.0, 0.0])
    bridge.ok("join", names=["Ground", "Field"])
    bridge.ok("add_primitive", type="ico_sphere", name="Rock", radius=0.05, subdivisions=1)
    bridge.ok("scatter", target="Ground", source="Rock", min_distance=0.25, density_mask=["liquid"], name="Stones", realize=True, seed=1)
    points = mesh_points("Stones")
    assert (points[:, 0] > 6.5).sum() > 100, "stones on the joined field"
    assert np.all(liquid_world.Water([bpy.data.objects["Pond"]]).signed_depth(points) < 0.06)


def instance_points(name):
    return mesh_points(name)


def test_the_shore_renders_darker_and_stays_wet_through_the_weather(bridge):
    dimple("Ground", 6.0, 120, 1.0, 2.0)
    grey_ground(bridge, "Ground")
    bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[0.0, 0.0, 0.0], name="Pond")
    bridge.ok("add_light", type="sun", name="Lamp", rotation=[50.0, 0.0, 30.0], energy=3.0)
    bridge.ok("set_world", color=[0.2, 0.2, 0.2], strength=1.0)
    ortho(bridge, "Top", (0.0, 0.0, 10.0), (0.0, 0.0, 0.0), 6.0)

    def ring_and_far(label):
        pixels = luminance(render(bridge, label, 96, 8, "Top"))
        centres = (np.arange(96) + 0.5) / 96 * 6.0 - 3.0
        x, y = np.meshgrid(centres, -centres)
        radius = np.hypot(x, y)
        return pixels[(radius > 1.06) & (radius < 1.16)].mean(), pixels[radius > 2.6].mean()

    ring, far = ring_and_far("shore")
    assert ring < 0.75 * far, (ring, far)
    bridge.ok("weather", preset="heavy_rain", form="sheet", haze=False, exposure="keep", rain_foreground=False)
    nodes = bpy.data.materials["Grey"].node_tree.nodes
    assert any(node.name.startswith("wx_wet_") for node in nodes) and any(node.name.startswith("wx_shore_") for node in nodes)
    assert not any(node.name.startswith("wx_wet_") for node in bpy.data.materials["Pond"].node_tree.nodes)
    bridge.ok("weather", remove=True)
    nodes = bpy.data.materials["Grey"].node_tree.nodes
    assert not any(node.name.startswith("wx_wet_") for node in nodes) and any(node.name.startswith("wx_shore_") for node in nodes)
    bridge.ok("set_world", color=[0.2, 0.2, 0.2], strength=1.0)
    ring_after, far_after = ring_and_far("after")
    assert abs(ring_after / far_after - ring / far) < 0.05, (ring_after / far_after, ring / far)


def flat_lake(bridge, radius, depth, size):
    dimple("Land", size, 160, radius, radius * radius / (2.0 * depth))
    grey_ground(bridge, "Land")


def test_still_water_mirrors_the_sky_by_fresnel_and_haze_lies_over_it(bridge):
    flat_lake(bridge, 300.0, 40.0, 800.0)
    bridge.ok("sky", sun={"elevation": 40.0, "azimuth": 180.0})
    bridge.ok("liquid_body", kind="lake", ground=["Land"], point=[0.0, 0.0, 0.0], name="Lake", wind={"speed": 0.0}, resolution=4.0)
    bridge.ok("add_camera", name="Eye", location=[0.0, -250.0, 1.5], rotation=[90.0, 0.0, 0.0], lens=24.0)
    size = 160
    pixels = luminance(render(bridge, "mirror", size, 16, "Eye"))
    focal = 24.0 / 36.0 * size
    for degrees in (2.0, 4.0, 7.0):
        offset = math.tan(math.radians(degrees)) * focal
        above = pixels[int(round(size / 2 - offset)), :].mean()
        below = pixels[int(round(size / 2 + offset - 1)), :].mean()
        wanted = liquid_light.fresnel(math.sin(math.radians(degrees)), 1.333)
        assert abs(below / above - wanted) < 0.2 * wanted + 0.02, (degrees, below / above, wanted)
    row = int(round(size / 2 + math.tan(math.radians(0.5)) * focal))
    clear = pixels[row].mean()
    airlight = 0.3 * clear
    bridge.ok("atmosphere", visibility=600.0, method="depth", airlight=[airlight] * 3)
    hazy = luminance(render(bridge, "hazy", size, 16, "Eye"))[row].mean()
    assert abs(hazy - airlight) < 0.5 * abs(clear - airlight), (hazy, clear, airlight)


def test_cloud_shadows_fall_on_the_water(bridge):
    flat_lake(bridge, 1400.0, 1.5, 3000.0)
    bridge.ok("add_camera", name="Eye", location=[0.0, -1300.0, 2.0], rotation=[90.0, 0.0, 0.0])
    bridge.ok("liquid_body", kind="lake", ground=["Land"], point=[0.0, 0.0, 0.0], name="Lake", wind={"speed": 2.0}, wet_shore=False)
    ortho(bridge, "Top", (0.0, 0.0, 5000.0), (0.0, 0.0, 0.0), 1800.0)
    bpy.data.objects["Top"].data.clip_end = 100_000.0
    bridge.ok("sky", sun={"elevation": 60.0, "azimuth": 180.0})
    clear = luminance(render(bridge, "clear", 64, 32, "Top"))
    bridge.ok("clouds", layers=[{"genus": "cumulus", "coverage": 0.45, "seed": 3}], form="sheet")
    shaded = luminance(render(bridge, "clouds", 64, 32, "Top"))
    def dark_share(pixels):
        blocks = pixels.reshape(16, 4, 16, 4).mean(axis=(1, 3))
        return float((blocks < 0.5 * np.median(blocks)).mean())
    assert dark_share(clear) < 0.02, dark_share(clear)
    assert dark_share(shaded) > 0.1, dark_share(shaded)


def fireflies(pixels):
    padded = np.pad(pixels, 2, mode="edge")
    windows = np.stack([padded[i:i + pixels.shape[0], j:j + pixels.shape[1]] for i in range(5) for j in range(5)])
    median = np.median(windows, axis=0)
    return int(((pixels > 2.0 * median + 0.05)).sum())


def test_render_final_renders_liquids_without_fireflies(bridge):
    bridge.ok("add_primitive", type="plane", name="Table", size=2.0)
    bridge.ok("material_procedural", name="Wood", wood={})
    bridge.ok("assign_material", name="Table", material="Wood")
    cup(bridge, "Glass", 0.035, 0.1, wall=0.002)
    bridge.ok("liquid_fill", container="Glass", preset="water_fresh", fill=0.7, name="Water", glass=True)
    bridge.ok("sky", sun={"elevation": 35.0, "azimuth": 200.0})
    bridge.ok("add_camera", name="Eye", location=[0.0, -0.45, 0.2], target=[0.0, 0.0, 0.04])
    settings = {"width": 160, "height": 160, "samples": 64, "camera": "Eye", "device": "cpu", "preview": False}
    result = bridge.ok("render_final", path="glass.exr", denoise=False, noise_threshold=0.0, **settings)
    assert result["liquids"]["caustics"] is False and "Water" in result["liquids"]["objects"]
    assert bpy.context.scene.cycles.caustics_refractive is True
    tamed = fireflies(read(bridge, "glass.exr"))
    original = liquid_render.configure
    liquid_render.configure = lambda scope, scene: None
    try:
        bridge.ok("render_final", path="raw.exr", denoise=False, noise_threshold=0.0, **settings)
    finally:
        liquid_render.configure = original
    raw = fireflies(read(bridge, "raw.exr"))
    assert raw > 2 * max(tamed, 1), (raw, tamed)
    bridge.ok("render_final", path="final.exr", **settings)
    assert fireflies(read(bridge, "final.exr")) <= 3


def read(bridge, path):
    from blendworks_bridge import exr_read

    pixels = exr_read.read_exr(os.path.join(bridge.workspace, path)).stack("", "RGB")
    return np.asarray(pixels, dtype=np.float64) @ LUMINANCE


run(globals())
