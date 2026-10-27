import math

import bmesh
import bpy
import numpy
from mathutils import Euler, Matrix, Vector

from .errors import bad_args, failed, not_found
from .limits import MAX_MESH_VERTICES

GEOMETRY_TYPES = ("MESH", "CURVE", "FONT", "SURFACE", "META")


def rounded(value, digits=6):
    result = round(float(value), digits)
    return 0.0 if result == 0 else result


def vec(values, digits=6):
    return [rounded(value, digits) for value in values]


def degrees(euler):
    return [rounded(math.degrees(angle)) for angle in euler]


def euler_from_degrees(values):
    return Euler([math.radians(value) for value in values], "XYZ")


def get_object(name):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.name not in bpy.context.scene.objects:
        raise not_found(f"no object named {name} in the scene")
    return obj


def get_mesh_object(name):
    obj = get_object(name)
    if obj.type != "MESH":
        raise bad_args(f"{name} is a {obj.type.lower()}, not a mesh")
    return obj


def get_objects(object_names):
    seen = set()
    objects = []
    for name in object_names:
        if name in seen:
            raise bad_args(f"{name} is listed twice")
        seen.add(name)
        objects.append(get_object(name))
    return objects


def require_free_name(name):
    if name is not None and name in bpy.data.objects:
        raise bad_args(f"an object named {name} already exists")


def link_object(ctx, name, data):
    obj = bpy.data.objects.new(name, data)
    ctx.scene.collection.objects.link(obj)
    for other in ctx.view_layer.objects:
        other.select_set(False, view_layer=ctx.view_layer)
    obj.select_set(True, view_layer=ctx.view_layer)
    ctx.view_layer.objects.active = obj
    return obj


def place(obj, location=None, rotation=None):
    if location is not None:
        obj.location = Vector(location)
    if rotation is not None:
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = euler_from_degrees(rotation)


def triangle_count(mesh):
    faces = len(mesh.polygons)
    if faces == 0:
        return 0
    sizes = numpy.empty(faces, dtype=numpy.int32)
    mesh.polygons.foreach_get("loop_total", sizes)
    return int(sizes.sum(dtype=numpy.int64)) - 2 * faces


def mesh_counts(mesh):
    return {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "faces": len(mesh.polygons),
        "triangles": triangle_count(mesh),
    }


def evaluated_points(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    if obj.type == "MESH" or obj.type in GEOMETRY_TYPES:
        mesh = evaluated.to_mesh()
        try:
            if mesh is None:
                return []
            matrix = evaluated.matrix_world
            return [matrix @ vertex.co for vertex in mesh.vertices]
        finally:
            evaluated.to_mesh_clear()
    return []


def bounds_of(points):
    if not points:
        return None
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def bounds_dict(bounds):
    if bounds is None:
        return None
    low, high = bounds
    return {"min": vec(low), "max": vec(high), "size": vec(high - low), "centre": vec((low + high) / 2)}


def local_coordinates(mesh):
    flat = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
    mesh.vertices.foreach_get("co", flat)
    return flat.reshape(-1, 3).astype(numpy.float64)


def world_coordinates(obj, depsgraph):
    if obj.type not in GEOMETRY_TYPES:
        return numpy.empty((0, 3))
    evaluated = obj.evaluated_get(depsgraph)
    matrix = numpy.array(evaluated.matrix_world, dtype=numpy.float64)
    if obj.type == "MESH" and obj.mode == "OBJECT" and len(obj.modifiers) == 0 and obj.data.shape_keys is None:
        local = local_coordinates(obj.data)
    else:
        mesh = evaluated.to_mesh()
        try:
            local = local_coordinates(mesh) if mesh is not None else numpy.empty((0, 3))
        finally:
            evaluated.to_mesh_clear()
    return local @ matrix[:3, :3].T + matrix[:3, 3]


def array_bounds(points):
    if len(points) == 0:
        return None
    return Vector(points.min(axis=0)), Vector(points.max(axis=0))


def object_bounds(obj, depsgraph):
    return array_bounds(world_coordinates(obj, depsgraph))


def merge_bounds(bounds):
    present = [entry for entry in bounds if entry is not None]
    if not present:
        return None
    low = Vector((min(b[0].x for b in present), min(b[0].y for b in present), min(b[0].z for b in present)))
    high = Vector((max(b[1].x for b in present), max(b[1].y for b in present), max(b[1].z for b in present)))
    return low, high


def scene_bounds(ctx, objects=None, cache=None):
    depsgraph = ctx.depsgraph()
    found = []
    for obj in objects if objects is not None else ctx.scene.objects:
        if obj.type in GEOMETRY_TYPES and obj.visible_get(view_layer=ctx.view_layer):
            if cache is not None and obj.name in cache:
                found.append(cache[obj.name])
                continue
            bounds = object_bounds(obj, depsgraph)
            if cache is not None:
                cache[obj.name] = bounds
            found.append(bounds)
    return merge_bounds(found)


def local_bounds(mesh):
    return bounds_of([vertex.co.copy() for vertex in mesh.vertices])


def check_vertex_cap(count):
    if count > MAX_MESH_VERTICES:
        raise failed(f"the result would have {count} vertices; the cap is {MAX_MESH_VERTICES}")


class EditMesh:
    def __init__(self, obj):
        self.obj = obj
        self.bm = bmesh.new()
        self.bm.from_mesh(obj.data)
        self.bm.verts.ensure_lookup_table()
        self.bm.faces.ensure_lookup_table()

    def __enter__(self):
        return self.bm

    def __exit__(self, kind, error, trace):
        try:
            if kind is None:
                check_vertex_cap(len(self.bm.verts))
                self.bm.normal_update()
                self.bm.to_mesh(self.obj.data)
                self.obj.data.update()
        finally:
            self.bm.free()
        return False


def compensate_children(obj, matrix):
    for child in obj.children:
        child.matrix_parent_inverse = matrix @ child.matrix_parent_inverse


def identity():
    return Matrix.Identity(4)


def object_summary(obj, view_layer, depsgraph, cache=None):
    entry = {
        "name": obj.name,
        "type": obj.type.lower(),
        "location": vec(obj.location),
        "rotation": degrees(obj.matrix_basis.to_euler("XYZ")),
        "scale": vec(obj.scale),
        "dimensions": vec(obj.dimensions),
        "parent": obj.parent.name if obj.parent else None,
        "collections": sorted(collection.name for collection in obj.users_collection),
        "visible": obj.visible_get(view_layer=view_layer),
        "selected": obj.select_get(view_layer=view_layer),
    }
    if obj.type == "EMPTY":
        entry["display"] = obj.empty_display_type.lower()
        entry["display_size"] = rounded(obj.empty_display_size)
    if obj.type in GEOMETRY_TYPES:
        if cache is not None and obj.name in cache:
            bounds = cache[obj.name]
        else:
            bounds = object_bounds(obj, depsgraph)
            if cache is not None:
                cache[obj.name] = bounds
        entry["bounds"] = bounds_dict(bounds)
        entry["materials"] = [slot.material.name if slot.material else None for slot in obj.material_slots]
    if obj.type == "MESH":
        entry["mesh"] = mesh_counts(obj.data)
        entry["modifiers"] = [{"name": m.name, "type": m.type.lower()} for m in obj.modifiers]
        if len(obj.modifiers) > 0:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            entry["evaluated_mesh"] = mesh_counts(mesh)
            evaluated.to_mesh_clear()
        entry["uv_layers"] = [layer.name for layer in obj.data.uv_layers]
    return entry
