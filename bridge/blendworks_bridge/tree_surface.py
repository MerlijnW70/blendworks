import math

import bmesh
import numpy
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from .noise_stack import stack_field
from .tree_frames import smoothstep
from .tree_join import AXIS, MATERIAL, RADIUS, TANGENT

SHARP_DEGREES = 60.0
FADE_REACH = 4.0
TOUCH_SHIFT = 0.01
REPAIR_ROUNDS = 6
HELPERS = (RADIUS, TANGENT, MATERIAL)


def corner_vertices(mesh):
    corners = numpy.empty(len(mesh.loops), dtype=numpy.int64)
    mesh.loops.foreach_get("vertex_index", corners)
    return corners


def vertex_values(mesh, corners):
    count = len(mesh.vertices)
    radius_corners = numpy.empty(len(mesh.loops), dtype=numpy.float32)
    mesh.attributes[RADIUS].data.foreach_get("value", radius_corners)
    radius = numpy.full(count, numpy.inf)
    numpy.minimum.at(radius, corners, radius_corners)
    radius[~numpy.isfinite(radius)] = 0.0
    tangent_corners = numpy.empty(len(mesh.loops) * 3, dtype=numpy.float32)
    mesh.attributes[TANGENT].data.foreach_get("vector", tangent_corners)
    tangent = numpy.zeros((count, 3))
    numpy.add.at(tangent, corners, tangent_corners.reshape(-1, 3))
    length = numpy.linalg.norm(tangent, axis=1, keepdims=True)
    return radius, numpy.divide(tangent, length, out=numpy.zeros_like(tangent), where=length > 1e-12)


def positions_and_normals(mesh):
    count = len(mesh.vertices)
    points = numpy.empty(count * 3)
    mesh.vertices.foreach_get("co", points)
    normals = numpy.empty(count * 3)
    mesh.vertex_normals.foreach_get("vector", normals)
    return points.reshape(-1, 3), normals.reshape(-1, 3)


def face_axes(mesh):
    values = numpy.empty(len(mesh.polygons), dtype=numpy.int32)
    mesh.attributes[AXIS].data.foreach_get("value", values)
    return values


def crease_vertices(mesh, corners):
    sizes = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_total", sizes)
    axes = numpy.repeat(face_axes(mesh), sizes)
    low = numpy.full(len(mesh.vertices), numpy.iinfo(numpy.int32).max)
    high = numpy.full(len(mesh.vertices), -1)
    numpy.minimum.at(low, corners, axes)
    numpy.maximum.at(high, corners, axes)
    return numpy.flatnonzero((high >= 0) & (low != high))


def distances_to(points, chosen):
    if len(chosen) == 0:
        return numpy.full(len(points), numpy.inf)
    tree = KDTree(len(chosen))
    for index in chosen.tolist():
        tree.insert(points[index], index)
    tree.balance()
    return numpy.array([tree.find(point)[2] for point in points.tolist()])


def self_overlaps(mesh):
    mesh.calc_loop_triangles()
    triangles = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", triangles)
    triangles = triangles.reshape(-1, 3)
    points, _ = positions_and_normals(mesh)
    tree = BVHTree.FromPolygons(points.tolist(), triangles.tolist(), all_triangles=True)
    involved = set()
    pairs = 0
    for first, second in tree.overlap(tree):
        if first >= second or set(triangles[first].tolist()) & set(triangles[second].tolist()):
            continue
        pairs += 1
        involved.update(triangles[first].tolist())
        involved.update(triangles[second].tolist())
    return pairs, numpy.array(sorted(involved), dtype=numpy.int64)


def neighbourhood(mesh, chosen):
    edges = numpy.empty(len(mesh.edges) * 2, dtype=numpy.int64)
    mesh.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    picked = numpy.zeros(len(mesh.vertices), dtype=bool)
    picked[chosen] = True
    grown = picked.copy()
    grown[edges[picked[edges[:, 0]], 1]] = True
    grown[edges[picked[edges[:, 1]], 0]] = True
    return numpy.flatnonzero(grown)


def triangulate_crossings(mesh, involved):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        chosen = {face for index in involved.tolist() for face in bm.verts[index].link_faces if len(face.verts) > 3}
        if chosen:
            bmesh.ops.triangulate(bm, faces=sorted(chosen, key=lambda face: face.index), quad_method="BEAUTY", ngon_method="BEAUTY")
            bm.to_mesh(mesh)
            mesh.update()
        return len(chosen)
    finally:
        bm.free()


def separate_touching(mesh, rounds=REPAIR_ROUNDS):
    pairs, involved = self_overlaps(mesh)
    found = pairs
    triangulated = triangulate_crossings(mesh, involved) if pairs else 0
    if triangulated:
        pairs, involved = self_overlaps(mesh)
    corners = corner_vertices(mesh)
    radius, _ = vertex_values(mesh, corners)
    for step in range(rounds):
        if pairs == 0:
            break
        points, normals = positions_and_normals(mesh)
        points[involved] -= normals[involved] * (TOUCH_SHIFT * (step + 1) * numpy.maximum(radius[involved], 1e-3))[:, None]
        mesh.vertices.foreach_set("co", points.astype(numpy.float32).reshape(-1))
        mesh.update()
        pairs, involved = self_overlaps(mesh)
    return {"found": found, "triangulated": triangulated, "left": pairs}


def undo_crossings(mesh, before, rounds=REPAIR_ROUNDS):
    reverted = 0
    for _ in range(rounds):
        pairs, involved = self_overlaps(mesh)
        if pairs == 0:
            break
        grown = neighbourhood(mesh, involved)
        points, _ = positions_and_normals(mesh)
        points[grown] = before[grown]
        reverted += len(grown)
        mesh.vertices.foreach_set("co", points.astype(numpy.float32).reshape(-1))
        mesh.update()
    return reverted


def bark_noise(mesh, noise):
    if noise["amplitude"] <= 0.0:
        return {"amplitude": 0.0, "largest": 0.0}
    corners = corner_vertices(mesh)
    radius, tangent = vertex_values(mesh, corners)
    points, normals = positions_and_normals(mesh)
    along = numpy.einsum("ij,ij->i", points, tangent)
    lookup = points + (1.0 / noise["grain"] - 1.0) * along[:, None] * tangent
    bound = numpy.minimum(noise["amplitude"], noise["share"] * radius)
    fade = smoothstep(0.0, FADE_REACH * bound, distances_to(points, crease_vertices(mesh, corners)))
    heights = stack_field(lookup, noise) * bound * fade
    moved = points + normals * heights[:, None]
    mesh.vertices.foreach_set("co", moved.astype(numpy.float32).reshape(-1))
    mesh.update()
    reverted = undo_crossings(mesh, points)
    share = numpy.divide(numpy.abs(heights), radius, out=numpy.zeros_like(heights), where=radius > 0)
    return {"amplitude": noise["amplitude"], "largest": float(numpy.abs(heights).max()) if len(heights) else 0.0, "largest_share_of_radius": float(share.max()) if len(share) else 0.0, "reverted_vertices": reverted}


def face_materials(mesh, slots):
    values = numpy.empty(len(mesh.polygons), dtype=numpy.int32)
    mesh.attributes[MATERIAL].data.foreach_get("value", values)
    mapping = numpy.zeros(max(slots) + 1 if slots else 1, dtype=numpy.int32)
    for index, slot in enumerate(slots):
        mapping[slot] = index
    mesh.polygons.foreach_set("material_index", mapping[values])
    return values


def mark_sharp(mesh):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        limit = math.radians(SHARP_DEGREES)
        axis = bm.faces.layers.int.get(AXIS)
        material = bm.faces.layers.int.get(MATERIAL)
        sharp = 0
        for edge in bm.edges:
            faces = edge.link_faces
            border = len(faces) == 2 and (faces[0][axis] != faces[1][axis] or faces[0][material] != faces[1][material])
            hard = border and edge.calc_face_angle(0.0) > limit
            edge.smooth = not hard
            sharp += hard
        bm.to_mesh(mesh)
        return sharp
    finally:
        bm.free()


def drop_helpers(mesh, keep_axis=False):
    for name in HELPERS + (() if keep_axis else (AXIS,)):
        attribute = mesh.attributes.get(name)
        if attribute is not None:
            mesh.attributes.remove(attribute)


def shell_count(mesh):
    edges = numpy.empty(len(mesh.edges) * 2, dtype=numpy.int64)
    mesh.edges.foreach_get("vertices", edges)
    labels = numpy.arange(len(mesh.vertices))
    pairs = edges.reshape(-1, 2)
    while True:
        low = numpy.minimum(labels[pairs[:, 0]], labels[pairs[:, 1]])
        changed = numpy.zeros(len(labels), dtype=bool)
        for column in (0, 1):
            before = labels[pairs[:, column]]
            numpy.minimum.at(labels, pairs[:, column], low)
            changed[pairs[:, column]] |= labels[pairs[:, column]] != before
        labels = labels[labels]
        if not changed.any():
            break
    used = numpy.zeros(len(labels), dtype=bool)
    used[pairs.reshape(-1)] = True
    return int(len(numpy.unique(labels[used])))
