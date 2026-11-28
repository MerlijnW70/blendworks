import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import run
from blendworks_bridge import forest_place
from blendworks_bridge.commands.distant_forest import FIELD_PROPERTY
from blendworks_bridge.cover_nodes import TRANSFORM
from blendworks_bridge.woodland_shapes import forest_field
from land_helpers import region

SIZE = 300.0
BORDER_BAND = 30.0
LEAST_AGREEMENT = 0.9
FOREST = {"species": ["oak"], "tree_detail": 0.2, "frames": 2, "frame_pixels": 16, "cover": 0.5, "patch_size": 260.0, "max_slope": 89.0, "water_margin": 1.0, "near": 150.0, "far": 500.0, "seed": 3}
WOOD = {"species": ["oak"], "shrubs": ["hazel"], "variants": 1, "points_share": 0.05, "detail": "low", "understorey": False, "shade_ground": False, "parallel": False, "rim_wander": 0.0}


def stems(name):
    obj = bpy.data.objects[name]
    values = numpy.zeros(len(obj.data.vertices) * 16, dtype=numpy.float32)
    obj.data.attributes[TRANSFORM].data.foreach_get("value", values)
    return values.reshape(-1, 4, 4)[:, 3, :2].astype(numpy.float64)


def test_near_stands_take_the_patches_of_the_distant_forest_across_the_border(bridge):
    region(bridge, size=SIZE, resolution=61, height=3.0)
    bridge.ok("sky", sun={"elevation": 35.0, "azimuth": 160.0})
    bridge.ok("add_camera", name="Cam", location=[0.0, -100.0, 20.0], target=[0.0, 300.0, 0.0], lens=35.0)
    bridge.ok("distant_land", terrain=["land"], detail=16, behind=1.0)
    bridge.ok("distant_forest", land="DistantLand", **FOREST)
    settings = json.loads(bpy.data.objects["DistantForest"][FIELD_PROPERTY])
    field = forest_field(settings)
    land = bpy.data.objects["DistantLand"]
    tree, points, faces = forest_place.land_tree(land)
    far_share = forest_place.forest_share(points, numpy.tile([0.0, 0.0, 1.0], (len(points), 1)), numpy.zeros(len(points)), numpy.ones(len(points)), FOREST, FOREST["patch_size"])[0]
    reach = numpy.abs(points[:, :2]).max(axis=1)
    beside = (reach > SIZE / 2.0) & (reach < SIZE / 2.0 + BORDER_BAND)
    agreement = float(((far_share[beside] >= 0.5) == (field(points[beside, :2]) >= 0.5)).mean())
    assert beside.sum() > 20 and agreement >= LEAST_AGREEMENT, (int(beside.sum()), agreement)
    result = bridge.ok("woodland", ground=["land"], stands=[{"kind": "forest", "field": "DistantForest"}], seed=2, **WOOD)
    assert result["stands"][0]["field"] == "DistantForest" and 0.1 < result["stands"][0]["field_share"] < 0.9
    near = stems(result["layers"]["trees"]["object"])
    inside = field(near) >= 0.5
    assert len(near) > 20 and inside.mean() >= LEAST_AGREEMENT, (len(near), float(inside.mean()))
    rim = numpy.abs(near).max(axis=1) > SIZE / 2.0 - BORDER_BAND
    assert rim.sum() > 0, "no near trees run up to the border"
    outside_forest = field(numpy.column_stack([near[rim, 0] * 1.15, near[rim, 1] * 1.15])) >= 0.5
    assert outside_forest.mean() >= 0.5, float(outside_forest.mean())


run(globals())
