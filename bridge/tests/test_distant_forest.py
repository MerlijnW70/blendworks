import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy as np

from blendworks_bridge import exr_read, forest_canopy, forest_cards, forest_grove, forest_inplace, forest_place, impostors
from final_helpers import EXACT
from land_helpers import region

IOU = 0.7
IOU_ANYWHERE = 0.6
LUMINANCE_STEP = 0.1
COVER_TOLERANCE = 0.03
FOREST = {"species": ["oak"], "tree_detail": 0.3, "frames": 6, "frame_pixels": 64, "cover": 1.0, "max_slope": 89.0, "patch_size": 400.0}
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])


def scene(bridge):
    region(bridge, size=200.0, resolution=41, height=4.0)
    bridge.ok("sky", sun={"elevation": 35.0, "azimuth": 160.0})
    bridge.ok("add_camera", name="Cam", location=[0.0, 80.0, 25.0], target=[0.0, 400.0, 0.0], lens=35.0)
    bridge.ok("distant_land", terrain=["land"], detail=24, behind=1.0)


def frame(bridge, path):
    bridge.ok("render_final", path=path, width=96, height=54, samples=16, **EXACT)
    return exr_read.read_exr(os.path.join(bridge.workspace, path)).stack("", "RGB")


def direction(elevation, azimuth):
    elevation, azimuth = math.radians(elevation), math.radians(azimuth)
    return np.array([math.cos(elevation) * math.sin(azimuth), math.cos(elevation) * math.cos(azimuth), math.sin(elevation)])


def test_impostor_silhouettes_match_their_trees(bridge):
    scene(bridge)
    result = bridge.ok("distant_forest", land="DistantLand", near=150.0, far=600.0, **dict(FOREST, frames=8))
    tree = bpy.data.objects[result["variants"][0]]
    collection = bpy.data.collections["DistantForest_bake_00"]
    material = bpy.data.materials[result["impostor"]["material"]]
    calibration = forest_cards.Calibration(bpy.context.scene, [collection], [impostors.bounds_sphere([tree])], 8, pixels=64)
    for elevation, azimuth, least in ((10.0, 0.0, IOU), (10.0, 11.0, IOU), (5.0, 37.0, IOU), (40.0, 22.0, IOU_ANYWHERE)):
        measured = calibration.run(material, -direction(elevation, azimuth), 300.0)
        assert measured["iou"] >= least, (elevation, azimuth, measured)


def test_no_luminance_step_where_trees_turn_into_cards(bridge):
    scene(bridge)
    real_forest = bridge.ok("distant_forest", name="Real", land="DistantLand", near=900.0, far=1000.0, **FOREST)
    assert real_forest["counts"]["near"] > 50, real_forest["counts"]
    bridge.ok("render_final", path="real.exr", width=96, height=54, samples=16, passes=["depth"], **EXACT)
    real = exr_read.read_exr(os.path.join(bridge.workspace, "real.exr")).stack("", "RGB")
    depth = exr_read.read_exr(os.path.join(bridge.workspace, "real.passes.exr")).channel("ViewLayer.Depth.Z")
    for suffix in ("", "_near", "_cards", "_shadows"):
        if bpy.data.objects.get("Real" + suffix) is not None:
            bpy.data.objects["Real" + suffix].hide_render = True
    switched = bridge.ok("distant_forest", name="Switched", land="DistantLand", near=300.0, far=1000.0, **FOREST)
    assert switched["counts"]["near"] > 0 and switched["counts"]["cards"] > 50, switched["counts"]
    cards = frame(bridge, "cards.exr")
    beyond = (depth > 380.0) & (depth < 800.0)
    assert beyond.sum() > 100, beyond.sum()
    real_light = float((real[beyond] @ LUMINANCE).mean())
    card_light = float((cards[beyond] @ LUMINANCE).mean())
    step = abs(card_light / real_light - 1.0)
    assert step < LUMINANCE_STEP, (step, real_light, card_light, switched["calibration"])
    assert switched["calibration"]["in_scene"]["pixels"] >= forest_inplace.LEAST_PIXELS
    assert set(switched["calibration"]["coverage"]) == {"trees", "cards"} and forest_grove.ROWS * forest_grove.COLUMNS == 24
    lift = bpy.data.objects["DistantLand"].data.attributes.get(forest_canopy.LIFT_ATTRIBUTE)
    assert lift is not None


def test_forest_follows_its_rules_and_cover(bridge):
    points = np.array([[x, 0.0, z] for x in range(10) for z in (0.0, 50.0)], dtype=float)
    normals = np.tile([0.0, 0.0, 1.0], (len(points), 1))
    normals[0] = [math.sin(math.radians(50.0)), 0.0, math.cos(math.radians(50.0))]
    water = np.zeros(len(points))
    water[2] = 1.0
    args = {"max_slope": 30.0, "height_range": [-10.0, 20.0], "water_margin": 0.0, "seed": 1, "cover": 1.0}
    allowed = forest_place.rules(points, normals, water, args)
    assert allowed[0] == 0.0 and allowed[2] == 0.0
    assert np.all(allowed[1::2] == 0.0)
    assert allowed[4] == 1.0
    rng = np.random.default_rng(3)
    many = np.column_stack([rng.uniform(0, 5000, 4000), rng.uniform(0, 5000, 4000), np.zeros(4000)])
    flat = np.tile([0.0, 0.0, 1.0], (4000, 1))
    for cover in (0.2, 0.5):
        share, covered = forest_place.forest_share(many, flat, np.zeros(4000), np.ones(4000), dict(args, cover=cover, height_range=[-1.0, 1.0]), 800.0)
        assert abs(covered - cover) < COVER_TOLERANCE, (cover, covered)
        assert abs(share.mean() - cover) < COVER_TOLERANCE


def test_forest_budget_and_same_seed(bridge):
    scene(bridge)
    result = bridge.ok("distant_forest", land="DistantLand", near=100.0, far=3000.0, budget=300, **FOREST)
    assert result["counts"]["near"] + result["counts"]["cards"] <= 300
    assert result["switches"]["far"] < 3000.0
    cards = bpy.data.objects.get("DistantForest_cards")
    assert cards is None or len(cards.data.polygons) == result["counts"]["cards"]
    cells = np.array([[3.0, 4.0], [-7.0, 2.0]])
    assert np.array_equal(forest_place.cell_random(cells, 5, 1), forest_place.cell_random(cells, 5, 1))
    assert not np.array_equal(forest_place.cell_random(cells, 5, 1), forest_place.cell_random(cells, 6, 1))
    first = forest_place.candidates(np.array([0.0, 0.0, 10.0]), np.array([0.0, 1.0]), 0.5, 500.0, 8.0, 4, True)[0]
    again = forest_place.candidates(np.array([0.0, 0.0, 10.0]), np.array([0.0, 1.0]), 0.5, 500.0, 8.0, 4, True)[0]
    assert np.array_equal(first, again)
    bridge.refuse("distant_forest", "bad_args", name="Other", land="land", **FOREST)
    bridge.refuse("distant_forest", "bad_args", name="Other", land="DistantLand", near=500.0, far=400.0, **FOREST)


run(globals())
