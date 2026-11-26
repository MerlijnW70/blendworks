import math

import bpy
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import liquid_masks
from .errors import bad_args
from .noise_stack import stack_bounds, stack_field
from .scatter_masks import ramp, slope_degrees
from .util import get_object

UP = Vector((0.0, 0.0, 1.0))
MAX_CROSSINGS = 64
CROSSING_STEP = 1e-5


def soft_band(values, low, high, edge, floor=-math.inf, ceiling=math.inf):
    inside = ((values >= low) & (values <= high)).astype(float)
    if edge <= 0.0:
        return inside
    rising = numpy.clip((values - low) / edge, 0.0, 1.0) if low > floor else 1.0
    falling = numpy.clip((high - values) / edge, 0.0, 1.0) if high < ceiling else 1.0
    return inside * numpy.minimum(rising, falling)


class Obstacles:
    def __init__(self, objects, depsgraph):
        corners, faces, lows, highs = [], [], [], []
        for obj in objects:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                mesh.calc_loop_triangles()
                matrix = obj.matrix_world
                offset = len(corners)
                placed = [(matrix @ vertex.co)[:] for vertex in mesh.vertices]
                corners.extend(placed)
                faces.extend(tuple(offset + index for index in triangle.vertices) for triangle in mesh.loop_triangles)
            finally:
                evaluated.to_mesh_clear()
            if placed:
                points = numpy.array(placed)
                lows.append(points.min(axis=0))
                highs.append(points.max(axis=0))
        if not faces:
            raise bad_args("the distance mask objects have no faces")
        self.tree = BVHTree.FromPolygons([Vector(point) for point in corners], faces)
        self.lows, self.highs = numpy.array(lows), numpy.array(highs)

    def box_gaps(self, points):
        gaps = numpy.full(len(points), numpy.inf)
        enclosed = numpy.zeros(len(points), dtype=bool)
        for low, high in zip(self.lows, self.highs):
            outside = numpy.maximum(numpy.maximum(low - points, points - high), 0.0)
            gap = numpy.linalg.norm(outside, axis=1)
            gaps = numpy.minimum(gaps, gap)
            enclosed |= gap == 0.0
        return gaps, enclosed

    def inside(self, point):
        crossings = 0
        origin = point.copy()
        for _ in range(MAX_CROSSINGS):
            hit, _, _, _ = self.tree.ray_cast(origin, UP)
            if hit is None:
                break
            crossings += 1
            origin = hit + UP * CROSSING_STEP
        return crossings % 2 == 1

    def signed_distances(self, points, reach):
        box_gap, enclosed = self.box_gaps(points)
        result = box_gap.copy()
        near = numpy.nonzero(box_gap <= reach)[0]
        for index in near.tolist():
            point = Vector(points[index])
            location, _, _, gap = self.tree.find_nearest(point)
            if location is None:
                continue
            result[index] = -gap if enclosed[index] and self.inside(point) else gap
        return result


def obstacle_set(spec, depsgraph, cache):
    key = tuple(sorted(spec["objects"]))
    if key not in cache:
        objects = [get_object(name) for name in key]
        meshes = [obj for obj in objects if obj.type == "MESH"]
        if len(meshes) != len(objects):
            raise bad_args("distance mask objects must be meshes")
        cache[key] = Obstacles(meshes, depsgraph)
    return cache[key]


def distance_mask(points, spec, depsgraph, cache):
    obstacles = obstacle_set(spec, depsgraph, cache)
    low = spec.get("min", -math.inf)
    high = spec.get("max", math.inf)
    edge = spec["edge"]
    reach = (high if math.isfinite(high) else low) + edge
    distances = obstacles.signed_distances(points, max(reach, 0.0))
    return soft_band(distances, low, high, edge)


def noise_mask(points, noise):
    lowest, highest = stack_bounds(noise)
    unit = (stack_field(points, noise) - lowest) / (highest - lowest)
    return numpy.clip((unit - noise["threshold"]) / noise["softness"] + 0.5, 0.0, 1.0)


def view_mask(points, camera, scene, margin):
    matrix = numpy.array(camera.matrix_world.inverted())
    local = points @ matrix[:3, :3].T + matrix[:3, 3]
    depth = -local[:, 2]
    frame = list(camera.data.view_frame(scene=scene))
    half = max(max(abs(corner.x) for corner in frame), max(abs(corner.y) for corner in frame)) * (1.0 + 2.0 * margin)
    if camera.data.type == "ORTHO":
        x, y = numpy.abs(local[:, 0]), numpy.abs(local[:, 1])
    else:
        plane = -frame[0].z
        with numpy.errstate(divide="ignore", invalid="ignore"):
            x = numpy.abs(local[:, 0] / depth * plane)
            y = numpy.abs(local[:, 1] / depth * plane)
    return ((depth > 0.0) & (x <= half) & (y <= half)).astype(float)


def population_masks(surface, population, candidates, context):
    points = candidates.points
    values = numpy.ones(len(points))
    if "slope" in population:
        slope = population["slope"]
        values *= soft_band(slope_degrees(surface.normals[candidates.triangle]), slope[0], slope[1], population["slope_edge"], 0.0, 180.0)
    if "height_range" in population:
        band = population["height_range"]
        values *= soft_band(points[:, 2], band[0], band[1], population["height_edge"])
    if context.get("liquid") is not None and population["liquid"] != "ignore":
        values *= liquid_masks.mask(context["liquid"], surface, candidates.triangle, candidates.weights, population["liquid"], population["shore"])
    if "attribute" in population:
        spec = population["attribute"]
        attribute = context["attributes"][spec["name"]]
        values *= ramp(surface.interpolate(attribute, candidates.triangle, candidates.weights), spec["range"][0], spec["range"][1])
    return values


def expensive_masks(population, points, context, values):
    alive = numpy.nonzero(values > 0.0)[0]
    for spec in population.get("distance", []):
        if len(alive):
            values[alive] *= distance_mask(points[alive], spec, context["depsgraph"], context["obstacles"])
            alive = alive[values[alive] > 0.0]
    if "noise" in population and len(alive):
        values[alive] *= noise_mask(points[alive], population["noise"])
    return values


def camera_object(name):
    camera = bpy.data.objects.get(name)
    if camera is None or camera.type != "CAMERA":
        raise bad_args(f"{name} is not a camera")
    return camera
