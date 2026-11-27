import math
import os
import random
import sys
from contextlib import contextmanager
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run
from tree_mesh_helpers import SMALL, SMALL_ROOTS

from blendworks_bridge import chain, cutters, extrusion, modifier_growth, surfaces, util
from blendworks_bridge import tree_leaves as leaf_engine
from blendworks_bridge.commands import mesh_edit, modifiers, roller_chain, scales

PITCH = 0.0127


@contextmanager
def swapped(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield original
    finally:
        setattr(module, name, original)


def capped(module, name, value):
    original = getattr(module, name)
    return swapped(module, name, type(original)._make(value, original.key, original.unit, original.kind, original.reason))


def refuse_work(*_args, **_kwargs):
    raise AssertionError("the work started before the count was checked")


def test_side_leaf_count_matches_the_placed_leaves(_bridge):
    rng = random.Random(7)
    cases = [(rng.uniform(0.0, 5.0), rng.uniform(0.1, 50.0)) for _ in range(20000)]
    cases += [((index + 0.5) / density, density) for density in (0.3, 1.0, 3.0, 7.1) for index in range(40)]
    for total, density in cases:
        old = len([index for index in range(int(math.floor(total * density + 0.5))) if (index + 0.5) / density < total])
        assert leaf_engine.side_leaf_count(total, density) == old, (total, density)


def test_single_leaves_at_and_over_the_instance_limit(bridge):
    bridge.ok("grow_tree", name="Grown", roots=SMALL_ROOTS, limit=0, **SMALL)
    count = bridge.ok("tree_leaves", name="Grown", leaves_name="Free", layout="single", density=6.0)["leaves"]
    with capped(leaf_engine, "MAX_INSTANCES", count):
        assert bridge.ok("tree_leaves", name="Grown", leaves_name="AtCap", layout="single", density=6.0)["leaves"] == count
    with capped(leaf_engine, "MAX_INSTANCES", count - 1), swapped(leaf_engine, "chain_leaves", refuse_work):
        message = bridge.refuse("tree_leaves", "bad_args", name="Grown", leaves_name="Over", layout="single", density=6.0)
    assert f"{count} leaves" in message and "Over" not in bpy.data.objects, message


def test_scale_marks_at_and_over_the_mark_limit(bridge):
    bridge.ok("add_primitive", type="cylinder", name="Dial", radius=0.2, depth=0.02, segments=64)
    ring = {"centre": [0, 0, 0.01], "radius": 0.15}
    with capped(scales, "MAX_MARKS", 100):
        assert bridge.ok("engrave_scale", name="Dial", ring=ring, start=0, end=99, step=1, depth=0.0004)["marks"] == 100
        with swapped(scales, "add_solid", refuse_work):
            message = bridge.refuse("engrave_scale", "bad_args", name="Dial", ring=ring, start=0, end=100, step=1, depth=0.0004)
    assert "101 marks" in message, message


def test_fold_counts_match_the_fold_lists(_bridge):
    rng = random.Random(3)
    for _ in range(300):
        low = rng.uniform(-5.0, 5.0)
        high = low + rng.uniform(0.0, 6.0)
        starts = sorted([0.0] + [rng.uniform(0.0, 1.3) for _ in range(rng.randint(0, 6))])
        for lines in (surfaces.EvenFolds(low, high, rng.uniform(0.01, 0.7)), surfaces.LapFolds(starts, 1.3 + rng.uniform(0.0, 0.2), low, high)):
            values = lines.values()
            assert lines.count() == len(values)
            a = rng.uniform(low - 1.0, high)
            b = a + rng.uniform(0.0, 1.0)
            assert lines.count(a, b) >= sum(1 for value in values if a <= value <= b)


def wide_mark(bridge, name):
    return bridge.call("engrave_scale", name=name, cylinder={"radius": 1.0, "centre": [0, 0, 0]}, start=0, end=0, count=1, place="centre", width=2.0, length=0.05, depth=0.001, tolerance=0.0002)


def test_fold_vertices_at_and_over_the_vertex_limit(bridge):
    for name in ("Drum", "Again", "Bound", "Over"):
        bridge.ok("add_primitive", type="cylinder", name=name, radius=1.0, depth=0.2, segments=64)
    counted = []
    with swapped(scales, "check_vertex_cap", lambda count: counted.append(count)):
        assert wide_mark(bridge, "Drum")["ok"]
    actual = counted[0]
    with capped(cutters, "MAX_MESH_VERTICES", actual):
        assert wide_mark(bridge, "Again")["ok"]
    with capped(cutters, "MAX_MESH_VERTICES", 0):
        message = wide_mark(bridge, "Bound")["error"]["message"]
    least = int(message.split("at least ")[1].split(" ")[0])
    assert 0.75 * actual <= least <= actual, (least, actual)
    with capped(cutters, "MAX_MESH_VERTICES", least - 1), swapped(cutters, "folded_loop", refuse_work):
        reply = wide_mark(bridge, "Over")
    assert reply["error"]["code"] == "bad_args", reply


def test_extrusion_at_and_over_the_vertex_limit(bridge):
    outline = [[math.cos(math.tau * k / 8), math.sin(math.tau * k / 8)] for k in range(8)]
    arguments = dict(outline=outline, depth=0.5, chamfer=0.05, bevel_segments=3)
    count = len(bridge.ok("extrude_outline", name="Free", **arguments) and bpy.data.objects["Free"].data.vertices)
    with capped(util, "MAX_MESH_VERTICES", count):
        bridge.ok("extrude_outline", name="AtCap", **arguments)
    with capped(util, "MAX_MESH_VERTICES", count - 1), swapped(extrusion, "skin", refuse_work):
        bridge.refuse("extrude_outline", "failed", name="Over", **arguments)


def test_screw_and_bevel_modifiers_at_and_over_the_vertex_limit(bridge):
    for name in ("Plate", "Over"):
        bridge.ok("add_primitive", type="plane", name=name, size=1.0)
    with capped(modifier_growth, "MAX_MESH_VERTICES", 64):
        result = bridge.ok("add_modifier", name="Plate", screw={"angle": 360.0, "steps": 16}, apply=False)
        assert result["evaluated_mesh"]["vertices"] == 64, result
        with swapped(modifiers, "finish_modifier", refuse_work):
            bridge.refuse("add_modifier", "bad_args", name="Over", screw={"angle": 360.0, "steps": 17}, apply=False)
    assert len(bpy.data.objects["Over"].modifiers) == 0
    for name in ("Box", "Capped", "Refused"):
        bridge.ok("add_primitive", type="cube", name=name, size=1.0)
    bevel = {"width": 0.1, "segments": 4}
    actual = bridge.ok("add_modifier", name="Box", bevel=bevel, apply=False)["evaluated_mesh"]["vertices"]
    least = 8 + 4 * 8
    assert least <= actual
    with capped(modifier_growth, "MAX_MESH_VERTICES", least):
        bridge.ok("add_modifier", name="Capped", bevel=bevel, apply=False)
    with capped(modifier_growth, "MAX_MESH_VERTICES", least - 1), swapped(modifiers, "finish_modifier", refuse_work):
        bridge.refuse("add_modifier", "bad_args", name="Refused", bevel=bevel, apply=False)


def test_mesh_bevel_at_and_over_the_vertex_limit(bridge):
    for name in ("Box", "Capped", "Refused"):
        bridge.ok("add_primitive", type="cube", name=name, size=1.0)
    bridge.ok("bevel", name="Box", width=0.1, segments=4)
    actual = len(bpy.data.objects["Box"].data.vertices)
    least = 8 + 4 * 8
    assert least <= actual
    with capped(util, "MAX_MESH_VERTICES", actual):
        bridge.ok("bevel", name="Capped", width=0.1, segments=4)
    blocked = SimpleNamespace(ops=SimpleNamespace(bevel=refuse_work))
    with capped(util, "MAX_MESH_VERTICES", least - 1), swapped(mesh_edit, "bmesh", blocked):
        bridge.refuse("bevel", "failed", name="Refused", width=0.1, segments=4)
    assert len(bpy.data.objects["Refused"].data.vertices) == 8


def test_chain_links_at_and_over_the_link_limit(bridge):
    with capped(roller_chain, "MAX_CHAIN_LINKS", 100):
        result = bridge.ok("roller_chain", name="AtCap", pitch=PITCH, waypoints=[[0, 0, 0], [100.5 * PITCH, 0, 0]])
        assert result["links"] == 100, result
        with swapped(chain, "point_along", refuse_work):
            message = bridge.refuse("roller_chain", "bad_args", name="Over", pitch=PITCH, waypoints=[[0, 0, 0], [101.5 * PITCH, 0, 0]])
    assert "101 links" in message, message


run(globals())
