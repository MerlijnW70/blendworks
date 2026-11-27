import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy as np

from blendworks_bridge import atmosphere_haze, exr_read
from final_helpers import EXACT, card, emissive
from land_helpers import region

LAND = {"detail": 24, "behind": 1.0}


def far_card(bridge, name, distance, material):
    bridge.ok("add_primitive", type="plane", name=name, size=distance, location=[0.0, distance, 0.0], rotation=[90.0, 0.0, 0.0])
    bridge.ok("assign_material", name=name, material=material)


def frame(bridge, path, passes=None):
    extra = {"passes": passes} if passes else {}
    bridge.ok("render_final", path=path, width=64, height=36, samples=4, **EXACT, **extra)
    return exr_read.read_exr(os.path.join(bridge.workspace, path)).stack("", "RGB")


def test_weather_haze_works_above_10_km_visibility(bridge):
    bridge.ok("add_primitive", type="plane", name="Ground", size=200.0)
    for visibility in (25_000.0, 60_000.0):
        result = bridge.ok("weather", preset="clear", visibility=visibility, form="sheet", seed=1)
        assert result["haze"] is not None, result["haze"]
        assert result["haze"]["visibility"] == visibility
        assert atmosphere_haze.stored(bpy.context.scene)["visibility"] == visibility
    assert bridge.ok("weather", preset="clear", form="sheet", haze=False)["haze"] is None


def test_nothing_is_cut_off_at_10_km(bridge):
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)
    far = 25_000.0
    far_card(bridge, "Far", far, emissive(bridge, "glow", 2.0))
    made = bridge.ok("add_camera", name="Cam", location=[0.0, 0.0, 0.0], rotation=[90.0, 0.0, 0.0])
    assert made["clip_end"] > far
    assert frame(bridge, "made.exr").mean() > 1.5
    bridge.ok("delete", names=["Far"])
    bridge.ok("camera_setup", name="Cam", clip_to_scene=True)
    farther = 60_000.0
    far_card(bridge, "Farther", farther, emissive(bridge, "glow", 2.0))
    clip = bpy.data.objects["Cam"].data.clip_end
    assert clip < farther
    result = bridge.ok("render_final", path="grown.exr", width=64, height=36, samples=4, **EXACT)
    assert result["clip_end_raised"]["to"] > farther
    assert exr_read.read_exr(os.path.join(bridge.workspace, "grown.exr")).stack("", "RGB").mean() > 1.5
    assert bpy.data.objects["Cam"].data.clip_end == clip
    bridge.ok("camera_setup", name="Cam", clip_end=1000.0)
    kept = bridge.ok("render_final", path="kept.exr", width=64, height=36, samples=4, **EXACT)
    assert "clip_end_raised" not in kept
    assert exr_read.read_exr(os.path.join(bridge.workspace, "kept.exr")).stack("", "RGB").mean() < 0.05


def test_ground_fog_below_zero_is_a_bounded_layer(bridge):
    depth = -42.0
    bridge.ok("set_world", color=[0.5, 0.5, 0.5], strength=1.0)
    bridge.ok("add_primitive", type="plane", name="Ground", size=4000.0, location=[0.0, 0.0, depth])
    bridge.ok("assign_material", name="Ground", material=emissive(bridge, "dark", 0.0))
    card(bridge, "Mast", (0.0, 300.0, depth + 40.0), 30.0, 80.0, emissive(bridge, "dark", 0.0))
    bridge.ok("add_camera", name="Cam", location=[0.0, 0.0, depth + 25.0], rotation=[85.0, 0.0, 0.0], lens=35.0)
    result = bridge.ok("atmosphere", visibility=8000.0, height_falloff=300.0, ground_fog={"visibility": 350.0, "height": 5.0},
                       method="depth", airlight=[0.5, 0.5, 0.5])
    fog = result["ground_fog"]
    assert abs(fog["base"] - depth) < 1e-3, fog
    settings = atmosphere_haze.stored(bpy.context.scene)
    sigma = atmosphere_haze.extinction(350.0)
    below = atmosphere_haze.density_at(settings, depth - 500.0) - atmosphere_haze.density_at(dict(settings, ground_fog=None), depth - 500.0)
    assert abs(below - sigma) < 1e-6 * sigma
    above = atmosphere_haze.density_at(settings, depth + 40.0) - atmosphere_haze.density_at(dict(settings, ground_fog=None), depth + 40.0)
    assert above < 1e-3 * sigma
    image = frame(bridge, "fog.exr").mean(axis=-1)
    ground = image[2 * image.shape[0] // 3 :]
    assert ground.mean() < 0.25, ground.mean()
    assert image[image.shape[0] // 3 : image.shape[0] // 2].mean() > ground.mean()


def test_far_land_fades_towards_the_sky_by_the_extinction(bridge):
    region(bridge)
    bridge.ok("sky", sun={"elevation": 30.0, "azimuth": 150.0})
    bridge.ok("add_camera", name="Cam", location=[0.0, -100.0, 300.0], target=[0.0, 20_000.0, 0.0], lens=24.0)
    bridge.ok("distant_land", terrain=["land"], **LAND)
    clear = frame(bridge, "clear.exr", ["depth"])
    depth = exr_read.read_exr(os.path.join(bridge.workspace, "clear.passes.exr")).channel("ViewLayer.Depth.Z")
    result = bridge.ok("atmosphere", visibility=12_000.0, method="depth", tint=[0.9, 0.95, 1.0])
    airlight = np.asarray(result["airlight"])
    hazed = frame(bridge, "hazed.exr")
    settings = atmosphere_haze.stored(bpy.context.scene)
    camera = bpy.data.objects["Cam"]
    rays = atmosphere_haze.pixel_rays(bpy.context.scene, camera, 64, 36)
    distance = depth * np.linalg.norm(rays, axis=-1)
    land = distance < 1e6
    sigma = 3.912 / 12_000.0
    through = np.exp(-sigma * distance[..., None] * np.asarray(settings["tint"]))
    expected = clear * through + airlight * (1.0 - through)
    gap = np.abs(hazed - expected)[land]
    assert gap.max() < 0.02 + 0.03 * np.abs(expected[land]).max(), gap.max()
    far = land & (distance > 10_000.0)
    near = land & (distance < 1_500.0)
    assert far.any() and near.any(), (np.nanmin(distance), np.nanmax(distance[land]), depth.min(), depth.max())
    assert np.abs(hazed[far] - airlight).mean() < 0.25 * np.abs(clear[far] - airlight).mean()
    assert np.abs(hazed[near] - airlight).mean() > 0.6 * np.abs(clear[near] - airlight).mean()
    assert distance[land].max() > 12_000.0, distance[land].max()
    assert math.isclose(settings["visibility"], 12_000.0)


run(globals())
