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


def top_triangles(objects):
    corners, faces = [], []
    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        top = mesh.attributes.get(TOP_ATTRIBUTE)
        flags = numpy.ones(len(mesh.polygons), dtype=bool)
        if top is not None:
            flags = numpy.zeros(len(mesh.polygons), dtype=bool)
            top.data.foreach_get("value", flags)
        matrix = obj.matrix_world
        offset = len(corners)
        corners.extend((matrix @ vertex.co)[:] for vertex in mesh.vertices)
        faces.extend(tuple(offset + index for index in tri.vertices) for tri in mesh.loop_triangles if flags[tri.polygon_index])
    return corners, faces


class Water:
    """The top surfaces of the liquids in the scene, to ask whether a point lies under water and how far it is from it."""

    def __init__(self, objects):
        corners, faces = top_triangles(objects)
        self.empty = not faces
        if not self.empty:
            self.tree = BVHTree.FromPolygons([Vector(point) for point in corners], faces)
            points = numpy.array(corners)
            self.low, self.high = points.min(axis=0), points.max(axis=0)

    def signed_depth(self, points, reach=REACH):
        """Depth of water above each point (positive), or minus the distance to the nearest water surface (dry)."""
        result = numpy.full(len(points), -reach)
        if self.empty:
            return result
        low, high = self.low - reach, self.high + reach
        near = numpy.nonzero(numpy.all((points >= low) & (points <= high), axis=1))[0]
        for index in near.tolist():
            point = Vector(points[index])
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


def vertex_points(obj):
    mesh = obj.data
    points = numpy.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    points = points.reshape(-1, 3)
    matrix = numpy.array(obj.matrix_world)
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def write_point_attribute(mesh, name, values):
    existing = mesh.attributes.get(name)
    if existing is not None:
        mesh.attributes.remove(existing)
    attribute = mesh.attributes.new(name, "FLOAT", "POINT")
    attribute.data.foreach_set("value", numpy.ascontiguousarray(values, dtype=numpy.float32))


def same_topology(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    return len(evaluated.data.vertices) == len(obj.data.vertices)


def mark_shore(obj, water, width, depsgraph):
    if not same_topology(obj, depsgraph):
        return None
    reach = max(width * 2.0, 1.0)
    depth = water.signed_depth(vertex_points(obj), reach)
    write_point_attribute(obj.data, DEPTH_ATTRIBUTE, depth)
    obj.data[REACH_PROPERTY] = reach
    obj.data[COUNT_PROPERTY] = len(obj.data.vertices)
    write_point_attribute(obj.data, WET_ATTRIBUTE, wetness(depth, width))
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


def wet_shores(ctx, width, names=None):
    """Write liquid_depth and liquid_wet on the ground and rocks near the water and darken their materials as weather wets ground."""
    scene = ctx.scene
    water = Water(liquid_objects(scene))
    objects = [bpy.data.objects[name] for name in names] if names is not None else shore_candidates(scene, water, width)
    depsgraph = ctx.depsgraph()
    marked, skipped, materials = [], [], set()
    for obj in objects:
        if mark_shore(obj, water, width, depsgraph) is None:
            skipped.append(obj.name)
            continue
        marked.append(obj.name)
        for slot in obj.material_slots:
            if slot.material is not None and weather_wet.apply_shore(slot.material, WET_ATTRIBUTE, DEPTH_ATTRIBUTE):
                materials.add(slot.material.name)
    return {"objects": marked, "skipped": skipped, "materials": sorted(materials), "width": width}


def target_depth(obj, depsgraph, reach=REACH):
    """liquid_depth of a mask target, true out to reach metres from the water: its own attribute when liquid_body wrote one
    that far out, else measured now against the scene's liquids. A dry point further than the measuring reach reads minus
    that reach, so an attribute written with a shorter reach than the caller's band would put the whole land inside it. An
    attribute from before the mesh changed (joined with others, which fill it with zeros) is measured again."""
    attribute = obj.data.attributes.get(DEPTH_ATTRIBUTE)
    stored = float(obj.data.get(REACH_PROPERTY, 0.0))
    current = obj.data.get(COUNT_PROPERTY) == len(obj.data.vertices)
    if attribute is not None and attribute.domain == "POINT" and stored >= reach and current and same_topology(obj, depsgraph):
        values = numpy.zeros(len(obj.data.vertices), dtype=numpy.float32)
        attribute.data.foreach_get("value", values)
        return values.astype(float)
    liquids = liquid_objects(bpy.context.scene)
    if not liquids or not same_topology(obj, depsgraph):
        return None
    return Water(liquids).signed_depth(vertex_points(obj), max(reach, REACH))
