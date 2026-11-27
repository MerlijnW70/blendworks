import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
import numpy

from harness import run
from blendworks_bridge.edge_order import canonical_edges, canonical_order

GRID = 40


def grid_mesh(name):
    steps = numpy.arange(GRID, dtype=numpy.float32)
    xs, ys = numpy.meshgrid(steps, steps)
    points = numpy.stack([xs.ravel(), ys.ravel(), numpy.sin(xs.ravel()) * numpy.cos(ys.ravel())], axis=1)
    first = (numpy.arange(GRID - 1)[None, :] + GRID * numpy.arange(GRID - 1)[:, None]).ravel()
    quads = numpy.stack([first, first + 1, first + GRID + 1, first + GRID], axis=1)
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(points))
    mesh.vertices.foreach_set("co", points.ravel())
    mesh.loops.add(quads.size)
    mesh.loops.foreach_set("vertex_index", quads.astype(numpy.int32).ravel())
    mesh.polygons.add(len(quads))
    mesh.polygons.foreach_set("loop_start", numpy.arange(len(quads), dtype=numpy.int32) * 4)
    mesh.update(calc_edges=True)
    return mesh


def mark_some(mesh):
    low, high = edges_of(mesh)
    chosen = (low * 7 + high) % 5 == 0
    mesh.edges.foreach_set("use_edge_sharp", chosen)
    mesh.edge_creases_ensure()
    mesh.attributes["crease_edge"].data.foreach_set("value", numpy.where(chosen, 0.5, 0.0).astype(numpy.float32))


def edges_of(mesh):
    pairs = numpy.empty(len(mesh.edges) * 2, dtype=numpy.int64)
    mesh.edges.foreach_get("vertices", pairs)
    pairs = pairs.reshape(-1, 2)
    return pairs.min(axis=1), pairs.max(axis=1)


def digest(mesh):
    found = hashlib.sha256()
    for name, field, kind, width in ((".edge_verts", "value", numpy.int32, 2), (".corner_edge", "value", numpy.int32, 1), (".corner_vert", "value", numpy.int32, 1), ("sharp_edge", "value", numpy.bool_, 1), ("crease_edge", "value", numpy.float32, 1)):
        attribute = mesh.attributes[name]
        count = len(mesh.loops) if attribute.domain == "CORNER" else len(mesh.edges)
        values = numpy.empty(count * width, dtype=kind)
        attribute.data.foreach_get(field, values)
        found.update(values.tobytes())
    return found.hexdigest()


def reversed_edges(mesh, name):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.edges.sort(key=lambda edge: -edge.index)
        other = bpy.data.meshes.new(name)
        bm.to_mesh(other)
        return other
    finally:
        bm.free()


def corners_match_edges(mesh):
    low, high = edges_of(mesh)
    corner_edge = numpy.empty(len(mesh.loops), dtype=numpy.int64)
    mesh.loops.foreach_get("edge_index", corner_edge)
    corner_vert = numpy.empty(len(mesh.loops), dtype=numpy.int64)
    mesh.loops.foreach_get("vertex_index", corner_vert)
    starts = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    totals = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    following = numpy.arange(len(mesh.loops)) + 1
    ends = starts + totals
    following[ends - 1] = starts
    a, b = corner_vert, corner_vert[following]
    return bool(numpy.array_equal(low[corner_edge], numpy.minimum(a, b)) and numpy.array_equal(high[corner_edge], numpy.maximum(a, b)))


def is_canonical(mesh):
    return bool(numpy.array_equal(canonical_order(mesh), numpy.arange(len(mesh.edges))))


def test_two_edge_orders_of_one_mesh_become_identical_with_their_edge_attributes(bridge):
    first = grid_mesh("first")
    mark_some(first)
    second = reversed_edges(first, "second")
    assert digest(first) != digest(second)
    assert canonical_edges(first) and canonical_edges(second)
    assert digest(first) == digest(second)
    for mesh in (first, second):
        assert is_canonical(mesh) and corners_match_edges(mesh) and not mesh.validate(verbose=False)
    sharp_pairs = {pair for pair, sharp in zip(zip(*edges_of(first)), (edge.use_edge_sharp for edge in first.edges)) if sharp}
    assert sharp_pairs == {(int(a), int(b)) for a, b in zip(*edges_of(first)) if (a * 7 + b) % 5 == 0}
    assert not canonical_edges(first)


def test_every_edge_building_command_leaves_canonical_edges(bridge):
    bridge.ok("heightfield", name="land", size=[40.0, 40.0], resolution=49, height=4.0, seed=4, skirt=True)
    bridge.ok("liquid_body", kind="lake", name="lake", ground=["land"], point=[0.0, 0.0, 0.0], seed=3)
    bridge.ok("grow_tree", name="birch", preset="birch", seed=7, location=[-30.0, -30.0, 0.0], limit=0, height=4.0)
    bridge.ok("tree_mesh", name="birch")
    bridge.ok("tree_leaves", name="birch_bark", seed=7, detail="low")
    vertices = [[x, y, 0.0] for y in range(30) for x in range(30)]
    faces = [[y * 30 + x, y * 30 + x + 1, (y + 1) * 30 + x + 1, (y + 1) * 30 + x] for y in range(29) for x in range(29)]
    bridge.ok("mesh_from_data", name="sheet", vertices=vertices, faces=faces, sharp_edges=[[0, 1], [31, 32]])
    bridge.ok("add_primitive", type="torus", name="ring", location=[20.0, 0.0, 0.0])
    bridge.ok("remesh", name="ring", voxel_size=0.05)
    bridge.ok("blob", name="drop", points=[{"position": [0.0, 20.0, 0.0], "radius": 0.6}, {"position": [0.6, 20.0, 0.2], "radius": 0.5}], voxel_size=0.04)
    bridge.ok("add_primitive", type="cylinder", name="pipe", radius=0.5, depth=2.0, segments=128, location=[-10.0, 20.0, 0.0])
    bridge.ok("add_modifier", name="pipe", solidify={"thickness": 0.05}, apply=True)
    bridge.ok("export", path="sheet.obj", names=["sheet"])
    bridge.ok("delete", names=["sheet"])
    bridge.ok("import", path="sheet.obj")
    for name in ("land", "lake", "birch_bark_leaves", "sheet", "ring", "drop", "pipe"):
        mesh = bpy.data.objects[name].data
        assert len(mesh.edges) > 100, (name, len(mesh.edges))
        assert is_canonical(mesh), name
        assert corners_match_edges(mesh), name


def test_uv_spheres_are_the_same_mesh_every_time_with_outward_faces(bridge):
    bridge.ok("add_primitive", type="sphere", name="a", segments=24, rings=12)
    bridge.ok("add_primitive", type="sphere", name="b", segments=24, rings=12)
    meshes = [bpy.data.objects[name].data for name in ("a", "b")]
    assert len(meshes[0].vertices) == 24 * 11 + 2 and len(meshes[0].polygons) == 24 * 12
    loops = []
    for mesh in meshes:
        corner_vert = numpy.empty(len(mesh.loops), dtype=numpy.int32)
        mesh.loops.foreach_get("vertex_index", corner_vert)
        loops.append(corner_vert)
        for polygon in mesh.polygons:
            assert polygon.normal.dot(polygon.center) > 0.0
        uv = numpy.empty(len(mesh.loops) * 2, dtype=numpy.float32)
        mesh.uv_layers["UVMap"].uv.foreach_get("vector", uv)
        assert uv.min() >= 0.0 and uv.max() <= 1.0
    assert numpy.array_equal(loops[0], loops[1])


run(globals())
