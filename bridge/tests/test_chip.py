import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run

import bpy
import numpy
from rock_helpers import convex, mesh_of, report, world_and_faces

EDGE_POINTS = numpy.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=float)


def distance_to_cube_edges(points, half=1.0):
    inner = numpy.abs(points)
    nearest = numpy.sort(half - inner, axis=1)
    return numpy.sqrt(nearest[:, 0] ** 2 + nearest[:, 1] ** 2)


def inside_solid(name, points):
    world, faces = world_and_faces(name)
    inside = numpy.ones(len(points), dtype=bool)
    for face in faces:
        corners = world[face]
        normal = numpy.cross(corners[1] - corners[0], corners[2] - corners[0])
        length = numpy.linalg.norm(normal)
        if length > 0:
            inside &= (points - corners[0]) @ (normal / length) <= 1e-6
    return inside


def test_chip_leaves_a_closed_convex_solid_and_removes_volume(bridge):
    bridge.ok("add_primitive", type="cube", name="Block", size=2.0)
    result = bridge.ok("chip", name="Block", count=8, depth=0.4, seed=2)
    assert result["chips"] == 8
    state = report("Block")
    assert state["closed"] and convex("Block")
    assert 0 < result["removed_volume"] < 0.5
    close(state["volume"], result["volume_after"], 1e-4)
    close(result["volume_before"] - result["removed_volume"], state["volume"], 1e-4)
    assert len(mesh_of("Block").data.polygons) > 6


def test_chip_removes_volume_only_within_depth_of_the_original_edges(bridge):
    bridge.ok("add_primitive", type="cube", name="Block", size=2.0)
    depth = 0.35
    bridge.ok("chip", name="Block", count=10, depth=depth, seed=7)
    rng = numpy.random.default_rng(0)
    points = rng.uniform(-1.0, 1.0, size=(400000, 3))
    removed = points[~inside_solid("Block", points)]
    assert len(removed) > 200
    assert distance_to_cube_edges(removed).max() <= depth + 1e-4


def test_chip_respects_the_object_transform_and_keeps_its_materials(bridge):
    bridge.ok("add_primitive", type="cube", name="Block", size=1.0, location=[3.0, 1.0, 0.5], rotation=[0, 0, 30])
    bridge.ok("transform", name="Block", scale=[2.0, 1.0, 1.0])
    obj = mesh_of("Block")
    placed = (tuple(obj.location), tuple(obj.rotation_euler), tuple(obj.scale))
    result = bridge.ok("chip", name="Block", count=3, depth=0.2, seed=1)
    assert placed == (tuple(obj.location), tuple(obj.rotation_euler), tuple(obj.scale))
    assert result["fresh_slot"] == 1 and [slot.name if slot else None for slot in obj.data.materials] == [None, "FreshBreak"]
    assert 1 in {polygon.material_index for polygon in obj.data.polygons}
    assert report("Block")["closed"]


def test_chip_refuses_open_nonconvex_or_hopeless_requests(bridge):
    bridge.ok("add_primitive", type="torus", name="Ring")
    bridge.refuse("chip", "bad_args", name="Ring")
    bridge.ok("add_primitive", type="plane", name="Sheet")
    bridge.refuse("chip", "bad_args", name="Sheet")
    bridge.ok("add_primitive", type="cube", name="Block", size=2.0)
    bridge.refuse("chip", "bad_args", name="Block", depth=0.0)
    bridge.refuse("chip", "bad_args", name="Block", count=0)


run(globals())
