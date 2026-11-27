import hashlib
import math

import bpy
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import cloud_forms, weather_continuum, weather_objects, weather_wet

LIQUID_PROPERTY = "blendworks_liquid"
TOP_ATTRIBUTE = "lq_top"
DEPTH_ATTRIBUTE = "liquid_depth"
REACH_PROPERTY = "liquid_depth_reach"
COUNT_PROPERTY = "liquid_depth_vertices"
WET_ATTRIBUTE = "liquid_wet"
SIGNATURE_PROPERTY = "liquid_depth_signature"
SHORE_PROPERTY = "blendworks_shore_width"
GRID_CELLS = 1024
MIN_REACH = 2.0
UP = Vector((0.0, 0.0, 1.0))
REACH = 50.0
STILL_AIR = 2.0
STILL_DIRECTION = 90.0
WIND_BY_STORM = ((0.0, 2.0), (0.18, 3.5), (0.32, 5.0), (0.46, 6.5), (0.6, 7.5), (0.72, 8.5), (0.86, 11.0), (1.0, 14.0))


def piecewise(points, value):
    if value <= points[0][0]:
        return points[0][1]
    for (left, low), (right, high) in zip(points, points[1:]):
        if value <= right:
            return low + (value - left) / (right - left) * (high - low)
    return points[-1][1]


def storm_of(layers):
    """The storm value of the continuum whose cloud layers are closest to the stored ones (weather keeps no other trace)."""
    stored = {layer["genus"]: layer["coverage"] for layer in layers}
    best, chosen = math.inf, 0.0
    for step in range(201):
        storm = step / 200.0
        expected = {layer["genus"]: layer.get("coverage", 1.0) for layer in weather_continuum.state(storm, 0)["layers"]}
        error = sum((stored.get(genus, 0.0) - expected.get(genus, 0.0)) ** 2 for genus in set(stored) | set(expected))
        if error < best - 1e-12:
            best, chosen = error, storm
    return chosen, best


def scene_wind(scene, given=None):
    """Wind at the water: the call's own, else the weather's: the drift of the lowest cloud layer and a speed from its storm value."""
    given = given or {}
    clouds = cloud_forms.stored(scene)
    if clouds is None or not clouds.get("layers"):
        source = "still air (no weather)"
        speed, direction = STILL_AIR, STILL_DIRECTION
    else:
        layers = clouds["layers"]
        lowest = min(layers, key=lambda layer: layer["base"])
        storm, error = storm_of(layers)
        speed, direction = piecewise(WIND_BY_STORM, storm), lowest["wind_direction"]
        source = f"weather: storm {round(storm, 3)} (layer match error {round(error, 6)}), drift of the {lowest['genus']} layer"
    if "speed" in given:
        speed = given["speed"]
    if "direction" in given:
        direction = given["direction"]
    if given:
        source = "call" if {"speed", "direction"} <= set(given) else source + ", partly overridden by the call"
    return {"speed": float(speed), "direction": float(direction) % 360.0, "source": source}


def liquid_objects(scene):
    return [obj for obj in scene.objects if obj.type == "MESH" and obj.get(LIQUID_PROPERTY) is not None]


def is_liquid(obj):
    return obj.get(LIQUID_PROPERTY) is not None


def vertex_points(obj, depsgraph=None):
    """World-space vertices of obj: of its evaluated mesh (modifiers, shape keys) when a depsgraph is given."""
    mesh = obj.evaluated_get(depsgraph).data if depsgraph is not None else obj.data
    points = numpy.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    points = points.reshape(-1, 3)
    matrix = numpy.array(obj.matrix_world)
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def top_triangles(objects):
    """Corners (n, 3) and triangles (m, 3) of the top surfaces of the liquid objects, in world space."""
    corners, faces, offset = [], [], 0
    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        count = len(mesh.loop_triangles)
        vertices = numpy.zeros(count * 3, dtype=numpy.int32)
        owners = numpy.zeros(count, dtype=numpy.int32)
        mesh.loop_triangles.foreach_get("vertices", vertices)
        mesh.loop_triangles.foreach_get("polygon_index", owners)
        flags = numpy.ones(len(mesh.polygons), dtype=bool)
        top = mesh.attributes.get(TOP_ATTRIBUTE)
        if top is not None:
            top.data.foreach_get("value", flags)
        corners.append(vertex_points(obj))
        faces.append(vertices.reshape(-1, 3)[flags[owners]] + offset)
        offset += len(mesh.vertices)
    if not corners:
        return numpy.zeros((0, 3)), numpy.zeros((0, 3), dtype=numpy.int64)
    return numpy.concatenate(corners), numpy.concatenate(faces).astype(numpy.int64)


def signature(points, extra=""):
    """A digest of positions (to float32) and a string, to tell whether geometry changed since it was measured."""
    digest = hashlib.blake2b(digest_size=16)
    digest.update(numpy.ascontiguousarray(points, dtype=numpy.float32).tobytes())
    digest.update(extra.encode())
    return digest.hexdigest()


class Water:
    """The top surfaces of the liquids in the scene, to ask whether a point lies under water and how far it is from it."""

    total_queries = 0

    def __init__(self, objects):
        corners, faces = top_triangles(objects)
        self.empty = not len(faces)
        self.queries = 0
        self.signature = ""
        if not self.empty:
            self.corners, self.faces = corners, faces
            self.triangles = corners[faces]
            self.built = None
            self.low, self.high = corners.min(axis=0), corners.max(axis=0)
            self.signature = signature(self.triangles)

    @property
    def tree(self):
        """The BVH of the surface, built on the first query: a digest alone needs none."""
        if self.built is None:
            self.built = BVHTree.FromPolygons(self.corners.tolist(), self.faces.tolist())
        return self.built

    def near(self, points, reach):
        """Which points can lie within reach of the water: not above it by reach or more, and in a cell of a grid that a
        triangle's footprint, grown by reach, touches. Conservative: every point the exact queries could give a depth is kept."""
        keep = numpy.all((points >= self.low - reach) & (points <= self.high + reach), axis=1) & (points[:, 2] <= self.high[2] + reach)
        if not keep.any():
            return keep
        origin = self.low[:2] - reach
        span = self.high[:2] + reach - origin
        cell = max(reach, float(span.max()) / GRID_CELLS, 1e-9)
        shape = numpy.ceil(span / cell).astype(int) + 2
        low = numpy.floor((self.triangles[:, :, :2].min(axis=1) - reach - origin) / cell).astype(int)
        high = numpy.floor((self.triangles[:, :, :2].max(axis=1) + reach - origin) / cell).astype(int)
        marks = numpy.zeros(shape + 1, dtype=numpy.int32)
        numpy.add.at(marks, (low[:, 0], low[:, 1]), 1)
        numpy.add.at(marks, (high[:, 0] + 1, low[:, 1]), -1)
        numpy.add.at(marks, (low[:, 0], high[:, 1] + 1), -1)
        numpy.add.at(marks, (high[:, 0] + 1, high[:, 1] + 1), 1)
        covered = marks.cumsum(axis=0).cumsum(axis=1) > 0
        index = numpy.floor((points[keep][:, :2] - origin) / cell).astype(int)
        keep[numpy.nonzero(keep)[0]] = covered[index[:, 0], index[:, 1]]
        return keep

    def signed_depth(self, points, reach=REACH):
        """Depth of water above each point (positive), or minus the distance to the nearest water surface (dry), at most reach."""
        result = numpy.full(len(points), -reach)
        if self.empty:
            return result
        for index in numpy.nonzero(self.near(points, reach))[0].tolist():
            point = Vector(points[index])
            self.queries += 1
            Water.total_queries += 1
            hit = self.tree.ray_cast(point, UP)
            if hit[0] is not None and (point.z <= self.high[2] + 1e-9):
                result[index] = hit[0].z - point.z
                continue
            nearest = self.tree.find_nearest(point, reach)
            if nearest[0] is not None:
                result[index] = -min(nearest[3], reach)
        return result


def wetness(depth, width):
    dry = numpy.clip(-depth / max(width, 1e-6), 0.0, 1.0)
    return numpy.where(depth >= 0.0, 1.0, (1.0 - dry) ** 1.5)


def write_point_attribute(mesh, name, values):
    existing = mesh.attributes.get(name)
    if existing is not None:
        mesh.attributes.remove(existing)
    attribute = mesh.attributes.new(name, "FLOAT", "POINT")
    attribute.data.foreach_set("value", numpy.ascontiguousarray(values, dtype=numpy.float32))


def same_topology(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    return len(evaluated.data.vertices) == len(obj.data.vertices)


def band_of(body, width, own):
    """Width of a body's wet band: the call's when it is the body being made or when no body is named, else the one it was made with."""
    if own is None or body.name == own:
        return width
    return float(body.get(SHORE_PROPERTY, width))


def shore_fields(points, widths, waters):
    """liquid_depth (the nearest water's signed depth, out to the shortest band reach) and liquid_wet (the wettest of the
    bodies' own bands) at points. Each body wets by its own width, so a later body never overwrites an earlier one's band."""
    reaches = [max(width * 2.0, 1.0) for width in widths]
    reach = min(reaches, default=1.0)
    depth = numpy.full(len(points), -reach)
    wet = numpy.zeros(len(points))
    for water, width, own_reach in zip(waters, widths, reaches):
        own = water.signed_depth(points, own_reach)
        depth = numpy.maximum(depth, numpy.maximum(own, -reach))
        wet = numpy.maximum(wet, wetness(own, width))
    return depth, wet, reach


def waters_signature(waters):
    return "".join(water.signature for water in waters)


def store_depth(obj, depth, reach, points, water_signature):
    write_point_attribute(obj.data, DEPTH_ATTRIBUTE, depth)
    obj.data[REACH_PROPERTY] = reach
    obj.data[COUNT_PROPERTY] = len(obj.data.vertices)
    obj.data[SIGNATURE_PROPERTY] = signature(points, water_signature)


def mark_shore(obj, widths, waters, depsgraph):
    if not same_topology(obj, depsgraph):
        return None
    points = vertex_points(obj, depsgraph)
    depth, wet, reach = shore_fields(points, widths, waters)
    store_depth(obj, depth, reach, points, waters_signature(waters))
    write_point_attribute(obj.data, WET_ATTRIBUTE, wet)
    obj.data.update()
    return depth


def shore_candidates(scene, water, width):
    found = []
    if water.empty:
        return found
    low, high = water.low - width - 1.0, water.high + width + 1.0
    for obj in scene.objects:
        if obj.type != "MESH" or is_liquid(obj) or weather_objects.kind_of(obj) is not None or obj.get("blendworks_atmosphere_domain"):
            continue
        if obj.data.attributes.get("gc_transform") is not None:
            continue
        corners = numpy.array([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])
        if numpy.all(corners.max(axis=0) >= low) and numpy.all(corners.min(axis=0) <= high):
            found.append(obj)
    return found


def wet_shores(ctx, width, names=None, body=None):
    """Write liquid_depth and liquid_wet on the ground and rocks near the water and darken their materials as weather wets ground.
    Every liquid in the scene wets by its own width, kept on the liquid; width is the new body's (body names it), or every
    body's when none is named, as for rocks set at the water line."""
    scene = ctx.scene
    bodies = liquid_objects(scene)
    if body is not None and body in scene.objects:
        scene.objects[body][SHORE_PROPERTY] = width
    widths = [band_of(item, width, body) for item in bodies]
    waters = [Water([item]) for item in bodies]
    objects = [bpy.data.objects[name] for name in names] if names is not None else shore_candidates(scene, Water(bodies), max(widths, default=width))
    depsgraph = ctx.depsgraph()
    marked, skipped, materials = [], [], set()
    for obj in objects:
        if mark_shore(obj, widths, waters, depsgraph) is None:
            skipped.append(obj.name)
            continue
        marked.append(obj.name)
        for slot in obj.material_slots:
            if slot.material is not None and weather_wet.apply_shore(slot.material, WET_ATTRIBUTE, DEPTH_ATTRIBUTE):
                materials.add(slot.material.name)
    return {"objects": marked, "skipped": skipped, "materials": sorted(materials), "width": width}


def target_depth(obj, depsgraph, reach=MIN_REACH):
    """liquid_depth of a mask target, true out to reach metres from the water. It is the attribute liquid_body wrote when that
    was measured that far out, on this very ground and these very liquids (a digest of the evaluated vertices and the water's
    triangles, so any deformation or change of the water counts, not only a changed vertex count); otherwise it is measured
    now against the scene's liquids and kept on the target for the next call, so the measuring is paid once, not per call.
    A dry point further than the measuring reach reads minus that reach, so a shorter attribute would put the whole land
    inside a wider band. Where the target already has a wet band (liquid_wet), a stale one is refreshed with the depth."""
    if not same_topology(obj, depsgraph):
        return None
    points = vertex_points(obj, depsgraph)
    liquids = liquid_objects(bpy.context.scene)
    attribute = obj.data.attributes.get(DEPTH_ATTRIBUTE)
    waters = [Water([item]) for item in liquids]
    marked = signature(points, waters_signature(waters))
    stored = float(obj.data.get(REACH_PROPERTY, 0.0))
    if attribute is not None and attribute.domain == "POINT" and stored >= reach and obj.data.get(COUNT_PROPERTY) == len(points) and obj.data.get(SIGNATURE_PROPERTY) == marked:
        values = numpy.zeros(len(points), dtype=numpy.float32)
        attribute.data.foreach_get("value", values)
        return values.astype(float)
    if not liquids:
        return None
    union = Water(liquids)
    measured = max(reach, MIN_REACH)
    depth = union.signed_depth(points, measured)
    store_depth(obj, depth, measured, points, waters_signature(waters))
    if obj.data.attributes.get(WET_ATTRIBUTE) is not None:
        widths = [float(item.get(SHORE_PROPERTY, 1.0)) for item in liquids]
        write_point_attribute(obj.data, WET_ATTRIBUTE, shore_fields(points, widths, waters)[1])
    obj.data.update()
    return depth
