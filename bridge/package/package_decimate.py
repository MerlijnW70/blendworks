"""Edge collapse decimation for LODs with locked borders."""

import bmesh
import bpy
import numpy as np

from package_error import geometric_error
from package_locks import feature_vertices
from package_plan import MIN_RATIO, MIN_TRIANGLES, reached
from package_surface import mesh_surface

WELD_DISTANCE = 1e-6
GROUP = "lod-weights"
NORMAL_WEIGHT = 50
NORMAL_THRESHOLD = 0.01
SEARCH_STEPS = 7
LOCK_COST = 2.0
SETTLE_GROWTH = 1.15
LOCK_FLOOR = 1e-4
STRICT = "strict"
SEAMS_RELEASED = "seamsReleased"
BORDERS_ONLY = "bordersOnly"
FREE = "free"
UNCHANGED = "unchanged"
LADDER = (STRICT, SEAMS_RELEASED, BORDERS_ONLY, FREE)
LOCKED = {
    STRICT: ("border", "material", "seam"),
    SEAMS_RELEASED: ("border", "material"),
    BORDERS_ONLY: ("border",),
    FREE: (),
}


def temporary_object(mesh):
    created = bpy.data.objects.new("lod-temporary", mesh)
    bpy.context.scene.collection.objects.link(created)
    return created


def discard_object(created):
    bpy.context.scene.collection.objects.unlink(created)
    bpy.data.objects.remove(created)


def evaluated_mesh(created):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return bpy.data.meshes.new_from_object(created.evaluated_get(depsgraph), depsgraph=depsgraph)


def triangle_total(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def welded(mesh):
    working = mesh.copy()
    builder = bmesh.new()
    builder.from_mesh(working)
    bmesh.ops.remove_doubles(builder, verts=builder.verts, dist=WELD_DISTANCE)
    builder.to_mesh(working)
    builder.free()
    return working


def locked_mask(mesh, mode):
    count = len(mesh.vertices)
    mask = np.zeros(count, dtype=bool)
    if not LOCKED[mode]:
        return mask
    features = feature_vertices(mesh)
    for name in LOCKED[mode]:
        mask |= features[name]
    return mask


def collapse(mesh, ratio, mode):
    locked = locked_mask(mesh, mode)
    created = temporary_object(mesh)
    try:
        modifier = created.modifiers.new("lod-decimate", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        if locked.any():
            group = created.vertex_groups.new(name=GROUP)
            free = np.flatnonzero(~locked).tolist()
            if free:
                group.add(free, 1.0, "REPLACE")
            modifier.vertex_group = group.name
            modifier.vertex_group_factor = 1.0
        return evaluated_mesh(created)
    finally:
        discard_object(created)


def weighted_normals(mesh):
    created = temporary_object(mesh)
    try:
        modifier = created.modifiers.new("lod-normals", "WEIGHTED_NORMAL")
        modifier.mode = "FACE_AREA_WITH_ANGLE"
        modifier.weight = NORMAL_WEIGHT
        modifier.thresh = NORMAL_THRESHOLD
        modifier.keep_sharp = True
        return evaluated_mesh(created)
    finally:
        discard_object(created)


def repeated_faces(builder):
    seen = set()
    repeated = []
    for face in builder.faces:
        key = tuple(sorted(vertex.index for vertex in face.verts))
        if key in seen:
            repeated.append(face)
        seen.add(key)
    return repeated


def cleaned(mesh):
    builder = bmesh.new()
    builder.from_mesh(mesh)
    bmesh.ops.dissolve_degenerate(builder, dist=WELD_DISTANCE, edges=builder.edges[:])
    bmesh.ops.triangulate(builder, faces=builder.faces[:])
    builder.verts.index_update()
    bmesh.ops.delete(builder, geom=repeated_faces(builder), context="FACES")
    builder.to_mesh(mesh)
    builder.free()
    return mesh


def finished(collapsed):
    try:
        return weighted_normals(cleaned(collapsed))
    finally:
        bpy.data.meshes.remove(collapsed)


class Reduction:
    def __init__(self, mesh, mode, source_triangles):
        self.mesh = mesh
        self.mode = mode
        self.triangles = triangle_total(mesh)
        self.ratio = self.triangles / source_triangles if source_triangles else 1.0


def unchanged(source, source_triangles):
    return Reduction(source.copy(), UNCHANGED, source_triangles)


def error_of(mesh, matrix, reference, scale=1.0):
    return geometric_error(reference, mesh_surface(mesh, matrix), sample_scale=scale)["hausdorff"]


def ratio_within_budget(base, matrix, reference, budget):
    low = MIN_RATIO
    high = 1.0
    best = 1.0
    for _ in range(SEARCH_STEPS):
        middle = (low * high) ** 0.5
        candidate = collapse(base, middle, FREE)
        try:
            within = error_of(candidate, matrix, reference, 0.25) <= budget
        finally:
            bpy.data.meshes.remove(candidate)
        if within:
            best = middle
            high = middle
        else:
            low = middle
    return best


def error_limit(budget, free_error, reference):
    if budget is not None:
        return budget
    return max(LOCK_COST * free_error, LOCK_FLOOR * reference.diagonal())


def settled_ratio(base, matrix, reference, budget, ratio):
    while ratio < 1.0:
        candidate = collapse(base, ratio, FREE)
        try:
            if error_of(candidate, matrix, reference) <= budget:
                break
        finally:
            bpy.data.meshes.remove(candidate)
        ratio = min(1.0, ratio * SETTLE_GROWTH)
    return ratio


def reduce_mesh(source, matrix, ratio=None, budget=None, reference=None):
    source_triangles = triangle_total(source)
    if source_triangles <= MIN_TRIANGLES or (ratio is not None and ratio >= 1.0):
        return unchanged(source, source_triangles)
    base = welded(source)
    try:
        if ratio is None:
            ratio = settled_ratio(base, matrix, reference, budget, ratio_within_budget(base, matrix, reference, budget))
            if ratio >= 1.0:
                return unchanged(source, source_triangles)
        target = max(ratio, MIN_TRIANGLES / source_triangles)
        free = collapse(base, target, FREE)
        limit = error_limit(budget, error_of(free, matrix, reference), reference)
        for mode in LADDER[:-1]:
            collapsed = collapse(base, target, mode)
            if reached(triangle_total(collapsed) / source_triangles, target) and error_of(collapsed, matrix, reference) <= limit:
                bpy.data.meshes.remove(free)
                return Reduction(finished(collapsed), mode, source_triangles)
            bpy.data.meshes.remove(collapsed)
        return Reduction(finished(free), FREE, source_triangles)
    finally:
        bpy.data.meshes.remove(base)
