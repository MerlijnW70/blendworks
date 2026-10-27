from array import array
from math import ceil, pi

from judge_common import JudgeError

DEFORM_ONLY = {
    "ARMATURE", "CAST", "CLOTH", "COLLISION", "CORRECTIVE_SMOOTH", "CURVE", "DATA_TRANSFER", "DISPLACE", "DYNAMIC_PAINT", "HOOK",
    "LAPLACIANDEFORM", "LAPLACIANSMOOTH", "LATTICE", "MESH_DEFORM", "NORMAL_EDIT", "SHRINKWRAP", "SIMPLE_DEFORM", "SMOOTH",
    "SOFT_BODY", "SURFACE", "SURFACE_DEFORM", "UV_PROJECT", "UV_WARP", "VERTEX_WEIGHT_EDIT", "VERTEX_WEIGHT_MIX",
    "VERTEX_WEIGHT_PROXIMITY", "WARP", "WAVE", "WEIGHTED_NORMAL", "MESH_CACHE",
}
SHRINKING = {"DECIMATE", "MASK", "BUILD", "WELD"}
UNBOUNDED = {"NODES", "FLUID", "MESH_SEQUENCE_CACHE", "VOLUME_TO_MESH", "OCEAN", "REMESH"}
MAX_DEPTH = 16
GLYPH_POINTS = 64
META_SURFACE_FACTOR = 8.0


class Unbounded(Exception):
    pass


class Shape:
    def __init__(self, vertices, edges, faces, corners):
        self.vertices = vertices
        self.edges = edges
        self.faces = faces
        self.corners = corners

    def triangles(self):
        return max(0, self.corners - 2 * self.faces)

    def scaled(self, factor):
        return Shape(self.vertices * factor, self.edges * factor, self.faces * factor, self.corners * factor)


def mesh_shape(mesh):
    totals = array("i", [0]) * len(mesh.polygons)
    mesh.polygons.foreach_get("loop_total", totals)
    return Shape(len(mesh.vertices), len(mesh.edges), len(totals), sum(totals))


def subdivided(shape, levels):
    if levels <= 0:
        return shape
    vertices = shape.vertices + shape.edges + shape.faces
    edges = 2 * shape.edges + shape.corners
    faces = shape.corners
    shape = Shape(vertices, edges, faces, 4 * faces)
    for _ in range(levels - 1):
        shape = Shape(shape.vertices + shape.edges + shape.faces, 2 * shape.edges + 4 * shape.faces, 4 * shape.faces, 16 * shape.faces)
    return shape


def array_count(modifier):
    if modifier.fit_type == "FIXED_COUNT":
        return max(1, modifier.count)
    if modifier.fit_type == "FIT_LENGTH":
        step = modifier.constant_offset_displace.length if modifier.use_constant_offset else 0.0
        if modifier.use_relative_offset and modifier.relative_offset_displace.length > 0:
            raise Unbounded(f"array modifier {modifier.name} fits a length with a relative offset")
        if step <= 0:
            raise Unbounded(f"array modifier {modifier.name} fits a length without a constant offset")
        return int(ceil(modifier.fit_length / step)) + 1
    raise Unbounded(f"array modifier {modifier.name} fits a curve")


def cap_shape(modifier, estimate, depth):
    total = Shape(0, 0, 0, 0)
    for cap in (modifier.start_cap, modifier.end_cap):
        if cap is not None:
            total = added(total, estimate.object_shape(cap, depth + 1))
    return total


def apply_modifier(modifier, shape, estimate, depth):
    kind = modifier.type
    if kind in DEFORM_ONLY or kind in SHRINKING:
        return shape
    if kind in UNBOUNDED:
        raise Unbounded(f"{kind.lower().replace('_', ' ')} modifier {modifier.name} cannot be bounded before it runs")
    if kind in {"SUBSURF", "MULTIRES"}:
        return subdivided(shape, modifier.render_levels)
    if kind == "TRIANGULATE":
        triangles = shape.triangles()
        return Shape(shape.vertices, shape.edges + triangles, triangles, 3 * triangles)
    if kind == "ARRAY":
        caps = cap_shape(modifier, estimate, depth)
        return added(shape.scaled(array_count(modifier)), caps)
    if kind == "MIRROR":
        return shape.scaled(2 ** sum(1 for axis in modifier.use_axis if axis))
    if kind == "SOLIDIFY":
        return Shape(2 * shape.vertices, 2 * shape.edges + shape.vertices, 2 * shape.faces + shape.edges, 2 * shape.corners + 4 * shape.edges)
    if kind == "SCREW":
        steps = max(1, modifier.render_steps) * max(1, modifier.iterations)
        return Shape(shape.vertices * (steps + 1), shape.edges * (steps + 1) + shape.vertices * steps, shape.faces * 2 + shape.edges * steps, shape.corners * 2 + 4 * shape.edges * steps)
    if kind == "BEVEL":
        segments = max(1, modifier.segments)
        faces = shape.faces + shape.edges * segments + shape.vertices * segments * segments
        return Shape(shape.vertices * (segments + 1) ** 2 + shape.edges * 2 * (segments + 1), 4 * faces, faces, 4 * faces + shape.corners)
    if kind == "EDGE_SPLIT":
        return Shape(shape.corners + shape.vertices, 2 * shape.edges, shape.faces, shape.corners)
    if kind == "WIREFRAME":
        faces = shape.faces + 2 * shape.corners + 2 * shape.edges
        return Shape(2 * shape.corners + 2 * shape.vertices, 4 * faces, faces, 4 * faces)
    if kind == "SKIN":
        faces = 6 * shape.vertices + 4 * shape.edges
        return Shape(8 * shape.vertices + 4 * shape.edges, 4 * faces, faces, 4 * faces)
    if kind == "EXPLODE":
        return Shape(shape.corners, shape.corners, shape.faces, shape.corners)
    if kind == "BOOLEAN":
        other = Shape(0, 0, 0, 0)
        if modifier.operand_type == "OBJECT" and modifier.object is not None:
            other = estimate.object_shape(modifier.object, depth + 1)
        elif modifier.operand_type == "COLLECTION" and modifier.collection is not None:
            other = estimate.collection_shape(modifier.collection, depth + 1)
        corners = 4 * (shape.corners + other.corners)
        return Shape(corners, corners, corners // 3, corners)
    raise Unbounded(f"the {kind.lower()} modifier {modifier.name} is not one the judge can bound before it runs")


def curve_shape(obj):
    data = obj.data
    resolution = max(1, getattr(data, "render_resolution_u", 0) or data.resolution_u)
    if obj.type == "FONT":
        ring = len(data.body) * GLYPH_POINTS * resolution
    else:
        ring = 0
        for spline in data.splines:
            points = len(spline.bezier_points) or len(spline.points)
            ring += points * (resolution if spline.type != "POLY" else 1) + 1
    if obj.type == "SURFACE":
        resolution_v = max(1, getattr(data, "render_resolution_v", 0) or data.resolution_v)
        faces = sum((len(spline.points) * resolution_v + 1) for spline in data.splines) * ring
        return Shape(faces + ring, 2 * faces + ring, faces, 4 * faces)
    profile = 1
    if data.bevel_mode == "OBJECT" and data.bevel_object is not None and data.bevel_object.type == "CURVE":
        bevel = data.bevel_object.data
        profile = sum((len(spline.bezier_points) or len(spline.points)) * max(1, bevel.resolution_u) + 1 for spline in bevel.splines)
    elif data.bevel_depth > 0 or data.extrude > 0:
        profile = 4 * (data.bevel_resolution + 1) + 2
    faces = ring * profile + 2 * ring
    return Shape(faces + ring, 2 * faces + ring, faces, 4 * faces)


def meta_shape(obj):
    data = obj.data
    resolution = max(data.render_resolution, 1e-4)
    area = 0.0
    for element in data.elements:
        reach = element.radius * 2 + max(element.size_x, element.size_y, element.size_z)
        area += 4 * pi * reach * reach
    faces = int(ceil(META_SURFACE_FACTOR * area / (resolution * resolution)))
    return Shape(faces, 2 * faces, faces, 4 * faces)


def added(first, second):
    return Shape(first.vertices + second.vertices, first.edges + second.edges, first.faces + second.faces, first.corners + second.corners)


class Estimate:
    def __init__(self):
        self.shapes = {}
        self.visiting = set()

    def own_shape(self, obj, depth):
        if obj.type == "MESH" and obj.data is not None:
            shape = mesh_shape(obj.data)
        elif obj.type in {"CURVE", "FONT", "SURFACE"} and obj.data is not None:
            shape = curve_shape(obj)
        elif obj.type == "META" and obj.data is not None:
            shape = meta_shape(obj)
        else:
            shape = Shape(0, 0, 0, 0)
        for modifier in obj.modifiers:
            if modifier.show_render:
                shape = apply_modifier(modifier, shape, self, depth)
        return shape

    def instanced_shape(self, obj, depth):
        total = Shape(0, 0, 0, 0)
        if obj.instance_type == "COLLECTION" and obj.instance_collection is not None:
            total = added(total, self.collection_shape(obj.instance_collection, depth + 1))
        elif obj.instance_type in {"VERTS", "FACES"} and obj.type == "MESH" and obj.data is not None:
            places = len(obj.data.vertices) if obj.instance_type == "VERTS" else len(obj.data.polygons)
            for child in obj.children:
                total = added(total, self.object_shape(child, depth + 1).scaled(places))
        for system in getattr(obj, "particle_systems", []):
            settings = system.settings
            children = max(settings.rendered_child_count, 0) if settings.child_type != "NONE" else 0
            copies = settings.count * (1 + children)
            if settings.render_type == "OBJECT" and settings.instance_object is not None:
                total = added(total, self.object_shape(settings.instance_object, depth + 1).scaled(copies))
            elif settings.render_type == "COLLECTION" and settings.instance_collection is not None:
                total = added(total, self.collection_shape(settings.instance_collection, depth + 1).scaled(copies))
        return total

    def object_shape(self, obj, depth):
        if depth > MAX_DEPTH:
            raise Unbounded(f"instancing nests deeper than {MAX_DEPTH} levels")
        key = obj.as_pointer()
        if key in self.shapes:
            return self.shapes[key]
        if key in self.visiting:
            raise Unbounded(f"object {obj.name[:80]} instances itself")
        self.visiting.add(key)
        try:
            shape = added(self.own_shape(obj, depth), self.instanced_shape(obj, depth))
        finally:
            self.visiting.discard(key)
        self.shapes[key] = shape
        return shape

    def collection_shape(self, collection, depth):
        if depth > MAX_DEPTH:
            raise Unbounded(f"instancing nests deeper than {MAX_DEPTH} levels")
        total = Shape(0, 0, 0, 0)
        for obj in collection.all_objects:
            total = added(total, self.object_shape(obj, depth))
        return total


def triangle_bound(scene):
    estimate = Estimate()
    total = 0
    for obj in scene.objects:
        total += estimate.object_shape(obj, 0).triangles()
    return total


def check_budget(scene, triangle_cap):
    try:
        bound = triangle_bound(scene)
    except Unbounded as reason:
        raise JudgeError("unbounded_geometry", f"the asset cannot be bounded before Blender evaluates it: {reason}; apply it before delivery") from None
    if bound > triangle_cap:
        raise JudgeError(
            "too_many_triangles",
            f"the asset may make up to {bound} triangles once its modifiers and instances run, over the judge's cap of {triangle_cap}; refused before evaluating it",
        )
    return bound
