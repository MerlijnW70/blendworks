import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from blendworks_bridge.tree_strands import IRREGULAR, hanging_strands
from tree_helpers import plain, tree_of
from blendworks_bridge.tree_skeleton import PROPERTY, from_property

COMB = dict(length_variation=[0.0], down_angle_variation=[0.0], rotate_variation=[0.0], spacing_variation=[0.0], child_probability=[1.0, 1.0, 0.0], sway={"strength": 0.0}, hem={"variation": 0.0, "rise": 0.0}, kink_probability=0.0)


def strands(bridge, name, **args):
    return bridge.ok("grow_tree", name=name, limit=0, seed=7, **args)["growth"]["strands"]


def test_the_weeping_presets_hang_irregular_strands_that_fork(bridge):
    for preset in ("willow", "weeping_willow"):
        found = strands(bridge, preset, preset=preset)
        assert found["count"] >= 150, found
        assert found["irregular"], found
        for key, limit in IRREGULAR.items():
            assert found[key] >= limit, (preset, key, found)
        assert found["branched_share"] >= 0.1, found
        assert found["lean_spread"] >= 4.0, found
        assert found["radius_cv"] >= 0.1, found


def test_an_evenly_spaced_comb_of_equal_strands_falls_below_the_regularity_thresholds(bridge):
    found = strands(bridge, "Comb", preset="willow", **COMB)
    assert found["count"] >= 150, found
    assert not found["irregular"], found
    assert found["spacing_cv"] < 0.05, found
    assert found["neighbour_length_change"] < IRREGULAR["neighbour_length_change"], found
    assert found["branched_share"] == 0.0, found


def hem_ends(name):
    skeleton = from_property(bpy.data.objects[name])
    found, _, _ = hanging_strands(skeleton)
    spread = float(numpy.hypot(skeleton.positions[:, 0], skeleton.positions[:, 1]).max())
    rows = []
    for strand in found:
        if strand.order != 2:
            continue
        first = skeleton.positions[strand.nodes[0]]
        rows.append((math.hypot(first[0], first[1]) / spread, float(skeleton.positions[strand.nodes, 2].min())))
    return numpy.array(rows), skeleton


def test_strands_end_at_a_hem_that_rises_towards_the_trunk(bridge):
    hem = {"height": 0.5, "rise": 3.0, "variation": 0.2, "order": 2}
    bridge.ok("grow_tree", name="Hemmed", preset="willow", seed=3, hem=hem, limit=0)
    bridge.ok("grow_tree", name="Flat", preset="willow", seed=3, hem={**hem, "rise": 0.0}, limit=0)
    bridge.ok("grow_tree", name="Unhemmed", preset="willow", seed=3, hem={"height": 0.01, "rise": 0.0, "variation": 0.0}, limit=0)
    hemmed, _ = hem_ends("Hemmed")
    floors = hem["height"] * (1.0 - hem["variation"]) + hem["rise"] * (1.0 - numpy.minimum(hemmed[:, 0], 1.0)) ** 2
    assert (hemmed[:, 1] >= floors - 1e-9).all()
    flat, _ = hem_ends("Flat")
    inner = lambda rows: rows[rows[:, 0] < 0.5, 1].mean()
    assert inner(hemmed) > inner(flat) + 0.5, (inner(hemmed), inner(flat))
    _, loose = hem_ends("Unhemmed")
    assert loose.positions[loose.orders == 2, 2].min() < hem["height"] * (1.0 - hem["variation"])


def test_sway_leans_each_strand_its_own_way(bridge):
    still = strands(bridge, "Still", preset="willow", sway={"strength": 0.0})
    swaying = strands(bridge, "Swaying", preset="willow", sway={"strength": 1.0})
    assert swaying["lean_spread"] > still["lean_spread"] + 2.0, (still, swaying)


def test_children_move_within_their_slots_and_branch_by_chance(bridge):
    levels = dict(method="levels", envelope="cylindrical", height=10.0, trunk_height=2.0, levels=3, branches=[16, 6], down_angle=[60.0, 45.0], length_ratio=[0.4, 0.5], segments=[24, 8, 3], tip_radius=0.02)
    bridge.ok("grow_tree", name="Even", seed=5, limit=0, **levels)
    bridge.ok("grow_tree", name="Jittered", seed=5, limit=0, spacing_variation=[0.45], length_variation=[0.4], **levels)
    bridge.ok("grow_tree", name="Sparse", seed=5, limit=0, child_probability=[1.0, 0.0], **levels)
    gaps = {}
    for name in ("Even", "Jittered"):
        tree = tree_of(name)
        trunk = tree.stem_from(1)
        heights = sorted(float(tree.positions[tree.parents[child]][2]) for child in tree.laterals(trunk))
        assert len(heights) == 16
        slots = numpy.linspace(2.0, 10.0, 17)
        for index, height in enumerate(heights):
            assert slots[index] - 1e-6 <= height <= slots[index + 1] + 1e-6, (name, index, height)
        gaps[name] = numpy.diff(heights)
    assert gaps["Even"].std() / gaps["Even"].mean() < 0.02
    assert gaps["Jittered"].std() / gaps["Jittered"].mean() > 0.2
    assert not (tree_of("Sparse").orders == 2).any()
    assert (tree_of("Even").orders == 2).any()


def test_the_same_seed_grows_the_same_strands(bridge):
    for name, seed in (("First", 4), ("Second", 4), ("Other", 5)):
        bridge.ok("grow_tree", name=name, preset="willow", seed=seed, limit=0)
    first, second, other = (plain(bpy.data.objects[name][PROPERTY]) for name in ("First", "Second", "Other"))
    assert first == second
    assert first["position"] != other["position"]


run(globals())
