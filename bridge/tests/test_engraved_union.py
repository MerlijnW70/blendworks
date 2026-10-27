import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engrave_checks import shape_counts
from harness import run
from kit_helpers import is_closed_manifold, volume

RADIUS = 0.15


def engraved_rings(bridge):
    bridge.ok("sweep", name="Horizon", preset="rounded_rectangle", width=0.03, height=0.006, corner_radius=0.0009, segments=2, circle={"centre": [0, 0, 0], "radius": RADIUS, "tolerance": 0.00006})
    bridge.ok("sweep", name="Meridian", preset="rounded_rectangle", width=0.02, height=0.006, corner_radius=0.0009, segments=2, circle={"centre": [0, 0, 0], "axis": [0, 1, 0], "radius": RADIUS, "tolerance": 0.00006})
    bridge.ok("engrave_scale", name="Horizon", ring={"centre": [0, 0, 0.003], "radius": 0.158}, step=1, depth=0.0004, length=0.004, width=0.0004, classes=[{"every": 10, "length": 0.006}])
    bridge.ok("engrave_scale", name="Meridian", ring={"centre": [0, 0.003, 0], "axis": [0, 1, 0], "radius": 0.152}, step=2, depth=0.0004, length=0.003, width=0.0004)
    for index in range(12):
        bridge.ok("engrave", name="Horizon", text=str(30 * index), ring={"centre": [0, 0, 0.003], "radius": 0.145, "angle": 30 * index + 15}, size=0.005, depth=0.0005)
        bridge.ok("engrave", name="Meridian", text=str(30 * index), ring={"centre": [0, 0.003, 0], "axis": [0, 1, 0], "radius": 0.145, "angle": 30 * index + 15}, size=0.004, depth=0.0005)
    return volume("Horizon"), volume("Meridian")


def test_an_exact_union_of_two_engraved_rings_is_closed_and_clean(bridge):
    horizon, meridian = engraved_rings(bridge)
    result = bridge.ok("boolean", name="Horizon", cutter="Meridian", operation="union", solver="exact", manifold=True, cutter_action="delete")
    assert result["solver"] == {"used": "exact", "reason": "asked for"}
    assert result["manifold"] is True and is_closed_manifold("Horizon")
    joined = volume("Horizon")
    assert max(horizon, meridian) < joined < horizon + meridian, (horizon, meridian, joined)
    assert shape_counts("Horizon")["slivers"] == 0 and result["quality"]["slivers"] == 0, result["quality"]


def test_auto_measures_the_meshes_and_says_which_solver_it_used_and_why(bridge):
    engraved_rings(bridge)
    closed = bridge.ok("boolean", name="Horizon", cutter="Meridian", operation="union", solver="auto", manifold=True, cutter_action="delete")
    assert closed["solver"]["used"] == "manifold" and "closed manifold" in closed["solver"]["reason"], closed["solver"]
    assert closed["manifold"] is True and is_closed_manifold("Horizon")
    bridge.ok("add_primitive", type="plane", name="Sheet", size=0.5)
    bridge.ok("add_primitive", type="cube", name="Block", size=0.1)
    opened = bridge.ok("boolean", name="Sheet", cutter="Block", operation="difference", solver="auto")
    assert opened["solver"]["used"] == "exact" and "Sheet is not a closed manifold" in opened["solver"]["reason"] and "edge(s) without exactly two faces" in opened["solver"]["reason"], opened["solver"]


run(globals())
