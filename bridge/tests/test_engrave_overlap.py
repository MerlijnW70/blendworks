import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy

from harness import run, snapshot
from kit_helpers import is_closed_manifold

from blendworks_bridge import engraving

TOP = 0.363
CUTS = 30
STEP = 0.75


def sector(bridge):
    bridge.ok("sweep", name="Sector", preset="rounded_rectangle", width=0.056, height=0.006, corner_radius=0.0009, segments=2,
              arc={"centre": [0, 0, TOP - 0.003], "axis": [0, 0, 1], "radius": 0.158, "reference": [1, 0, 0], "tolerance": 0.00006, "start_angle": -5.4, "end_angle": 25.4}, shading="auto", smooth_angle=40)


def path(radius):
    return [[radius * math.cos(-math.tau * index / 360), radius * math.sin(-math.tau * index / 360), TOP] for index in range(360)]


def test_overlapping_cuts_off_the_origin_keep_a_closed_mesh_closed(bridge):
    sector(bridge)
    for index in range(CUTS):
        radius = 0.1735 if index % 2 == 0 else 0.1495
        result = bridge.ok("engrave", name="Sector", text=str(30 + index), curve={"waypoints": path(radius), "closed": True, "normal": [0, 0, 1]},
                           size=0.0068, depth=0.0005, offset=radius * math.radians((-index * STEP) % 360), tolerance=0.0002)
        assert result["solver"]["used"] == "manifold" and "closed manifold" in result["solver"]["reason"], result["solver"]
        assert result["manifold"] is True and is_closed_manifold("Sector"), index
        assert result["quality"]["zero_area"] == 0, (index, result["quality"])


def engraved_sector(bridge, cuts):
    sector(bridge)
    for index in range(cuts):
        radius = 0.1735 if index % 2 == 0 else 0.1495
        bridge.ok("engrave", name="Sector", text=str(30 + index), curve={"waypoints": path(radius), "closed": True, "normal": [0, 0, 1]},
                  size=0.0068, depth=0.0005, offset=radius * math.radians((-index * STEP) % 360), tolerance=0.0002)
    return snapshot()


def reverse_edges(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.index_update()
    count = len(bm.edges)
    bm.edges.sort(key=lambda edge: count - edge.index)
    bm.to_mesh(mesh)
    bm.free()


def test_the_cuts_do_not_depend_on_the_order_the_boolean_returns_its_edges_in(bridge):
    plain = engraved_sector(bridge, 3)
    for name in [obj.name for obj in bpy.data.objects]:
        bridge.ok("delete", names=[name])
    original = engraving.apply_cutter

    def reversed_apply(ctx, target, data, cutting, uv_name, solver):
        original(ctx, target, data, cutting, uv_name, solver)
        reverse_edges(target.data)

    engraving.apply_cutter = reversed_apply
    try:
        shuffled = engraved_sector(bridge, 3)
    finally:
        engraving.apply_cutter = original
    assert shuffled["objects"] == plain["objects"]


run(globals())
