import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run

import bmesh
import bpy
import numpy
from rock_helpers import convex, mesh_of, report, world_and_faces


def block(bridge, name="Block", size=2.0, kind="cube"):
    if kind == "cube":
        bridge.ok("add_primitive", type="cube", name=name, size=size)
    else:
        bridge.ok("add_primitive", type="ico_sphere", name=name, radius=size / 2, subdivisions=2)


def merged_counts(name):
    bm = bmesh.new()
    bm.from_mesh(mesh_of(name).data)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0), verts=bm.verts[:], edges=bm.edges[:])
    counts = (len(bm.faces), len(bm.verts))
    bm.free()
    return counts


def uv_area(name):
    obj = mesh_of(name)
    layer = obj.data.uv_layers.active
    assert layer is not None
    areas = []
    for polygon in obj.data.polygons:
        uv = numpy.array([tuple(layer.uv[loop].vector) for loop in polygon.loop_indices])
        areas.append(0.5 * abs(sum(uv[i, 0] * uv[(i + 1) % len(uv), 1] - uv[(i + 1) % len(uv), 0] * uv[i, 1] for i in range(len(uv)))))
    return areas


def test_pieces_add_up_to_the_original_volume_and_each_is_closed_and_convex(bridge):
    for mode in ("binary", "voronoi"):
        block(bridge, "Block", 2.0, "ico")
        original = report("Block")["volume"]
        result = bridge.ok("fracture", name="Block", pieces=14, mode=mode, seed=3, min_size=0.05)
        assert result["count"] == 14 and "Block" not in bpy.data.objects
        total = 0.0
        for name in result["pieces"]:
            state = report(name)
            assert state["closed"] and state["volume"] > 0, name
            assert convex(name), name
            total += state["volume"]
        assert abs(total - original) / original < 0.005, (mode, total, original)
        close(result["pieces_volume"], total, 1e-6)
        for name in result["pieces"]:
            bpy.data.objects.remove(bpy.data.objects[name])


def test_every_face_is_mapped_and_cut_faces_have_their_own_slot(bridge):
    bridge.ok("material_procedural", name="Rock", stone={"color": [0.4, 0.4, 0.4], "cracks": False})
    block(bridge)
    bridge.ok("assign_material", name="Block", material="Rock")
    result = bridge.ok("fracture", name="Block", pieces=6, seed=1, min_size=0.1)
    assert result["fresh_slot"] == 1 and result["fresh_material"] == "FreshBreak"
    fresh_faces = 0
    for name in result["pieces"]:
        mesh = mesh_of(name).data
        assert [slot.name for slot in mesh.materials] == ["Rock", "FreshBreak"]
        assert min(uv_area(name)) > 1e-6
        indices = [polygon.material_index for polygon in mesh.polygons]
        fresh_faces += indices.count(1)
        assert set(indices) <= {0, 1}
    assert fresh_faces >= 6, fresh_faces
    piece = mesh_of(result["pieces"][0]).data
    cut = [polygon for polygon in piece.polygons if polygon.material_index == 1][0]
    uv = numpy.array([tuple(piece.uv_layers.active.uv[loop].vector) for loop in cut.loop_indices])
    corners = numpy.array([tuple(piece.vertices[index].co + mesh_of(result["pieces"][0]).location) for index in cut.vertices])
    axis = int(numpy.argmax(numpy.abs(numpy.array(cut.normal))))
    keep = [i for i in range(3) if i != axis]
    flip = -1.0 if cut.normal[axis] < 0 else 1.0
    close(uv[:, 0].tolist(), (flip * corners[:, keep[0]]).tolist(), 1e-4)
    close(uv[:, 1].tolist(), corners[:, keep[1]].tolist(), 1e-4)


def test_binary_pieces_are_blocky_with_about_six_faces_and_eight_vertices(bridge):
    block(bridge, "Block", 2.0)
    result = bridge.ok("fracture", name="Block", pieces=200, mode="binary", seed=2, min_size=0.0001)
    assert result["count"] == 200
    counts = numpy.array([merged_counts(name) for name in result["pieces"]], dtype=float)
    faces, vertices = counts.mean(axis=0)
    assert 6 * 0.8 <= faces <= 6 * 1.2, faces
    assert 8 * 0.8 <= vertices <= 8 * 1.2, vertices
    close([result["mean_faces"], result["mean_vertices"]], [faces, vertices], 0.05)


def test_fracture_is_deterministic_and_min_size_bounds_the_thickness(bridge):
    block(bridge)
    first = bridge.ok("fracture", name="Block", pieces=10, seed=5, min_size=0.3, keep_original=True)
    assert "Block" in bpy.data.objects
    positions = [tuple(mesh_of(name).location) for name in first["pieces"]]
    for name in first["pieces"]:
        bpy.data.objects.remove(bpy.data.objects[name])
    second = bridge.ok("fracture", name="Block", pieces=10, seed=5, min_size=0.3)
    assert positions == [tuple(mesh_of(name).location) for name in second["pieces"]]
    for name in second["pieces"]:
        world, faces = world_and_faces(name)
        widths = []
        for face in faces:
            corners = world[face]
            normal = numpy.cross(corners[1] - corners[0], corners[2] - corners[0])
            normal /= numpy.linalg.norm(normal)
            projected = world @ normal
            widths.append(projected.max() - projected.min())
        assert min(widths) >= 0.3 - 1e-6


def test_fracture_refuses_what_it_cannot_cut_exactly(bridge):
    bridge.ok("add_primitive", type="torus", name="Ring")
    assert "convex" in bridge.refuse("fracture", "bad_args", name="Ring", pieces=4)
    bridge.ok("add_primitive", type="plane", name="Sheet")
    assert "closed" in bridge.refuse("fracture", "bad_args", name="Sheet", pieces=4)
    block(bridge)
    bridge.refuse("fracture", "bad_args", name="Block", pieces=1)
    bridge.refuse("fracture", "bad_args", name="Block", pieces=2, mode="shatter")
    bridge.refuse("fracture", "not_found", name="Block", pieces=2, fresh_material="Ghost")
    bridge.refuse("fracture", "failed", name="Block", pieces=4, min_size=5.0)


run(globals())
