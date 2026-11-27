import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy as np

from blendworks_bridge import exr_read, mist_depth, valley_mist
from blendworks_bridge.atmosphere_haze import extinction
from final_helpers import EXACT

SIDE = 2000.0
CELLS = 41


def floor(y):
    return -100.0 + 0.04 * y


def valley(bridge):
    xs = np.linspace(-SIDE / 2.0, SIDE / 2.0, CELLS)
    grid_x, grid_y = np.meshgrid(xs, xs)
    z = floor(grid_y) + 80.0 * (1.0 - np.exp(-(grid_x / 250.0) ** 2))
    vertices = np.column_stack([grid_x.ravel(), grid_y.ravel(), z.ravel()]).tolist()
    faces = []
    for row in range(CELLS - 1):
        for column in range(CELLS - 1):
            a = row * CELLS + column
            faces.append([a, a + 1, a + CELLS + 1, a + CELLS])
    bridge.ok("mesh_from_data", name="Valley", vertices=vertices, faces=faces)


def density_at(points):
    obj = bpy.data.objects["ValleyMist"]
    settings = json.loads(obj[valley_mist.PROPERTY])
    image = bpy.data.images["ValleyMist" + valley_mist.TOP_IMAGE_SUFFIX]
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    top = pixels.reshape(height, width, 4)[..., 0].astype(np.float64)
    points = np.asarray(points, dtype=np.float64)
    return valley_mist.density(settings, top, points[:, :2], points[:, 2])


def test_mist_follows_the_low_ground_up_and_down_the_valley(bridge):
    valley(bridge)
    result = bridge.ok("valley_mist", ground=["Valley"], centre=[0.0, 0.0], radius=900.0, cells=64, valley_width=300.0,
                       thickness=15.0, fade=5.0, visibility=200.0)
    sigma = extinction(200.0)
    ys = np.array([-700.0, -300.0, 0.0, 300.0, 700.0])
    in_valley = density_at([[0.0, y, floor(y) + 6.0] for y in ys])
    assert np.all(in_valley > 0.9 * sigma), in_valley / sigma
    above = density_at([[0.0, y, floor(y) + 40.0] for y in ys])
    assert np.all(above == 0.0), above
    on_ridges = density_at([[x, y, floor(y) + 80.0 * (1.0 - np.exp(-(x / 250.0) ** 2)) + 3.0] for x in (-800.0, 800.0) for y in ys])
    assert np.all(on_ridges == 0.0), on_ridges
    deep = density_at([[0.0, y, floor(y) - 50.0] for y in ys])
    assert np.allclose(deep, sigma), deep / sigma
    assert floor(700.0) - floor(-700.0) > 50.0
    assert 0.1 < result["coverage"] < 0.6, result["coverage"]
    assert bpy.data.objects["ValleyMist"].get("blendworks_atmosphere_domain")


def test_mist_renders_in_the_valley_and_goes_away(bridge):
    valley(bridge)
    bridge.ok("set_world", color=[0.3, 0.35, 0.4], strength=1.0)
    bridge.ok("add_light", type="sun", name="Sun", rotation=[50.0, 0.0, 30.0], energy=3.0)
    bridge.ok("add_camera", name="Cam", location=[0.0, -950.0, floor(-950.0) + 60.0], target=[0.0, 500.0, floor(500.0)], lens=30.0)

    def frame(path):
        bridge.ok("render_final", path=path, width=48, height=27, samples=16, **EXACT)
        return exr_read.read_exr(os.path.join(bridge.workspace, path)).stack("", "RGB").mean(axis=-1)

    clear = frame("clear.exr")
    middle = slice(14, 27), slice(18, 30)
    sky = slice(0, 3), slice(0, 48)
    bridge.ok("valley_mist", ground=["Valley"], centre=[0.0, 0.0], radius=1000.0, cells=48, thickness=20.0, visibility=150.0)
    misty = frame("misty.exr")
    assert [obj.name for obj in mist_depth.mist_objects(bpy.context.scene)] == ["ValleyMist"]
    bridge.ok("atmosphere", visibility=1e6, method="depth", airlight=[0.0, 0.0, 0.0])
    integrated = frame("integrated.exr")
    assert np.abs(integrated[middle] - clear[middle]).mean() / clear[middle].mean() > 0.25, (integrated[middle].mean(), clear[middle].mean(), misty[middle].mean())
    bridge.ok("atmosphere", remove=True)
    change = np.abs(misty[middle] - clear[middle]).mean() / clear[middle].mean()
    assert change > 0.25, change
    assert np.abs(misty[sky] - clear[sky]).mean() < 0.05 * clear[sky].mean()
    assert bridge.ok("valley_mist", remove=True)["removed"]
    assert "ValleyMist" not in bpy.data.objects
    assert "ValleyMist" not in bpy.data.materials
    assert "ValleyMist" + valley_mist.TOP_IMAGE_SUFFIX not in bpy.data.images
    again = frame("again.exr")
    assert np.allclose(again, clear, atol=1e-4)


def test_valley_mist_refusals(bridge):
    valley(bridge)
    bridge.refuse("valley_mist", "bad_args")
    bridge.refuse("valley_mist", "bad_args", ground=["Valley"])
    bridge.refuse("valley_mist", "bad_args", remove=True, ground=["Valley"])
    bridge.ok("add_primitive", type="cube", name="ValleyMist")
    bridge.refuse("valley_mist", "bad_args", ground=["Valley"], centre=[0.0, 0.0])


run(globals())
