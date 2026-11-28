import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import run
from blendworks_bridge.tree_presets import SHRUBS
from blendworks_bridge.tree_skeleton import from_property
from blendworks_bridge.tree_species import SHRUB_NAMES

STEM_HEIGHT = 0.3
LEAST_STEMS = 3


def stems_at(skeleton, height):
    """Shoot segments that cross a level height above the base: the stems a cut there would show."""
    positions, parents = skeleton.positions, skeleton.parents
    base = positions[0, 2]
    crossing = 0
    for node in range(1, skeleton.count):
        low, high = positions[parents[node], 2] - base, positions[node, 2] - base
        if skeleton.kinds[node] == 0 and min(low, high) < height <= max(low, high):
            crossing += 1
    return crossing


def test_shrub_presets_grow_several_stems_from_the_base_and_trees_one_trunk(bridge):
    assert set(SHRUBS) == set(SHRUB_NAMES)
    for name in SHRUB_NAMES:
        bridge.ok("new_scene")
        grown = bridge.ok("grow_tree", name="Shrub", preset=name, seed=4, points=900, limit=0)
        assert grown["species"] == name
        stems = stems_at(from_property(bpy.data.objects["Shrub"]), STEM_HEIGHT)
        assert stems >= LEAST_STEMS, (name, stems)
        height = float(numpy.ptp(from_property(bpy.data.objects["Shrub"]).positions[:, 2]))
        assert height < 6.0, (name, height)
    bridge.ok("new_scene")
    bridge.ok("grow_tree", name="Tree", preset="oak", seed=4, points=900, limit=0)
    assert stems_at(from_property(bpy.data.objects["Tree"]), STEM_HEIGHT) == 1


run(globals())
