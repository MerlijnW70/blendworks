"""Where distant forest grows, and how each tree is drawn. The land's vertices get a forest share from rules (slope,
height, distance to water) and a seeded patch noise whose threshold is set so that forest covers the stated share of
the land. Trees stand on a jittered grid inside the camera's view; each is a real tree near the camera, an impostor card
farther out and part of the canopy surface beyond. A tree's own random number dithers it across each switch band."""
import math

import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from .land_field import smoothstep
from .noise_stack import octave_value

PATCH_STREAM = 23
JITTER_STREAM = 29
SLOPE_EDGE = 6.0
HEIGHT_EDGE = 20.0
VIEW_MARGIN = math.radians(8.0)
DOWN = Vector((0.0, 0.0, -1.0))
COVER_STEPS = 24


def vertex_areas(xy, faces):
    a, b, c = xy[faces[:, 0]], xy[faces[:, 1]], xy[faces[:, 2]]
    area = 0.5 * numpy.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    weights = numpy.zeros(len(xy))
    for corner in range(3):
        numpy.add.at(weights, faces[:, corner], area / 3.0)
    return weights


def patch_noise(xy, wavelength, seed):
    points = numpy.column_stack([xy, numpy.zeros(len(xy))])
    first = octave_value("perlin", "fbm", 1.0, points, wavelength, 1.0, seed * 1009 + PATCH_STREAM, 0)
    second = octave_value("perlin", "fbm", 1.0, points, wavelength / 2.3, 1.0, seed * 1009 + PATCH_STREAM, 1)
    return first + 0.45 * second


def rules(points, normals, water, args):
    """1 where every rule allows forest, falling to 0 over a soft edge past each limit."""
    slope = numpy.degrees(numpy.arccos(numpy.clip(normals[:, 2], -1.0, 1.0)))
    allowed = 1.0 - smoothstep(args["max_slope"] - SLOPE_EDGE, args["max_slope"], slope)
    if "height_range" in args:
        low, high = args["height_range"]
        allowed *= smoothstep(low - HEIGHT_EDGE, low, points[:, 2]) * (1.0 - smoothstep(high, high + HEIGHT_EDGE, points[:, 2]))
    wet = water >= 0.5
    if wet.any() and args["water_margin"] > 0.0:
        tree = KDTree(int(wet.sum()))
        for index, point in enumerate(points[wet, :2].tolist()):
            tree.insert((point[0], point[1], 0.0), index)
        tree.balance()
        reach = numpy.array([tree.find((x, y, 0.0))[2] for x, y in points[:, :2].tolist()])
        allowed *= smoothstep(0.0, args["water_margin"], reach)
    allowed *= 1.0 - smoothstep(0.05, 0.3, water)
    return allowed


def forest_share(points, normals, water, areas, args, wavelength):
    """Forest share per land vertex, and the share of dry land it covers. The patch threshold is found by bisection so
    that the forest's area over the dry land equals the stated cover, as far as the rules allow."""
    allowed = rules(points, normals, water, args)
    noise = patch_noise(points[:, :2], wavelength, args["seed"])
    dry = areas * (water < 0.5)
    total = max(float(dry.sum()), 1e-9)
    low, high = float(noise.min()) - 1.0, float(noise.max()) + 1.0

    def covered(threshold):
        share = allowed * smoothstep(threshold + 0.08, threshold - 0.08, noise)
        return share, float((share * dry).sum()) / total

    for _ in range(COVER_STEPS):
        middle = 0.5 * (low + high)
        if covered(middle)[1] < args["cover"]:
            low = middle
        else:
            high = middle
    return covered(high)


def land_tree(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    local = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
    mesh.vertices.foreach_get("co", local)
    points = local.reshape(-1, 3).astype(numpy.float64) + numpy.array(obj.matrix_world.translation)
    faces = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", faces)
    faces = faces.reshape(-1, 3)
    return BVHTree.FromPolygons([Vector(p) for p in points.tolist()], faces.tolist()), points, faces


def candidates(eye, forward, half_angle, reach, spacing, seed, view_only):
    """Jittered grid points within reach of the eye, inside its view widened by a margin when view_only."""
    low = numpy.floor((eye[:2] - reach) / spacing).astype(int)
    high = numpy.ceil((eye[:2] + reach) / spacing).astype(int)
    columns = numpy.arange(low[0], high[0])
    rows = numpy.arange(low[1], high[1])
    grid_x, grid_y = numpy.meshgrid(columns, rows)
    cells = numpy.column_stack([grid_x.ravel(), grid_y.ravel()]).astype(numpy.float64)
    jitter = cell_random(cells, seed, JITTER_STREAM), cell_random(cells, seed, JITTER_STREAM + 1)
    xy = (cells + 0.5 + 0.8 * (numpy.column_stack(jitter) - 0.5)) * spacing
    offset = xy - eye[:2]
    reach_of = numpy.hypot(offset[:, 0], offset[:, 1])
    keep = reach_of <= reach
    if view_only and forward is not None:
        cosine = (offset @ forward) / numpy.maximum(reach_of, 1e-9)
        keep &= (numpy.arccos(numpy.clip(cosine, -1.0, 1.0)) <= half_angle + VIEW_MARGIN) | (reach_of < 2.0 * spacing)
    return xy[keep], cells[keep]


def cell_random(cells, seed, stream):
    """A uniform number per grid cell, the same for a cell whatever else is placed: a hash of its indices and the seed."""
    value = (cells[:, 0].astype(numpy.int64) * 73856093) ^ (cells[:, 1].astype(numpy.int64) * 19349663) ^ (int(seed) * 83492791 + stream * 2654435761)
    value = value.astype(numpy.uint64)
    value ^= value >> numpy.uint64(33)
    value *= numpy.uint64(0xFF51AFD7ED558CCD)
    value ^= value >> numpy.uint64(33)
    value *= numpy.uint64(0xC4CEB9FE1A85EC53)
    value ^= value >> numpy.uint64(33)
    return (value >> numpy.uint64(11)).astype(numpy.float64) / float(1 << 53)


def ground_hits(tree, faces, share, xy, top):
    """Height and forest share of the land under each point; points off the land get NaN."""
    heights = numpy.full(len(xy), numpy.nan)
    forest = numpy.zeros(len(xy))
    for index, (x, y) in enumerate(xy.tolist()):
        hit = tree.ray_cast(Vector((x, y, top)), DOWN)
        if hit[0] is not None:
            heights[index] = hit[0].z
            forest[index] = share[faces[hit[2]]].mean()
    return heights, forest


def classes(distance, keys, near, far, band):
    """0 a real tree, 1 a card, 2 left to the canopy, dithered by each tree's key across each band."""
    to_card = smoothstep(near * (1.0 - band), near * (1.0 + band), distance)
    to_canopy = smoothstep(far * (1.0 - band), far * (1.0 + band), distance)
    kind = numpy.where(keys[:, 0] >= to_card, 0, 1)
    return numpy.where((kind == 1) & (keys[:, 1] < to_canopy), 2, kind)
