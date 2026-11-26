import math

import numpy
from mathutils import Vector
from mathutils.kdtree import KDTree

from . import liquid_grid
from .errors import bad_args

MANNING_NATURAL = 0.035
BANK_SLOPE = 0.5
MIN_SLOPE = 1e-4
RAPIDS = (0.02, 0.08)
RIVER_NODES = 400
END_TAPER = 1.5
MOUTH_REACH = 6
FREEBOARD = 0.15
MOUTH_TUCK = 0.003


class Path:
    """A river centreline in plan, sampled evenly, with the arc length, tangents and a level per sample."""

    def __init__(self, points, spacing):
        points = numpy.asarray(points, dtype=float)[:, :2]
        keep = numpy.concatenate([[True], numpy.linalg.norm(numpy.diff(points, axis=0), axis=1) > 1e-9])
        points = points[keep]
        if len(points) < 2:
            raise bad_args("the river path needs at least two distinct points")
        steps = numpy.linalg.norm(numpy.diff(points, axis=0), axis=1)
        arc = numpy.concatenate([[0.0], numpy.cumsum(steps)])
        count = max(int(math.ceil(arc[-1] / spacing)) + 1, 2)
        self.s = numpy.linspace(0.0, arc[-1], count)
        self.xy = numpy.column_stack([numpy.interp(self.s, arc, points[:, 0]), numpy.interp(self.s, arc, points[:, 1])])
        tangent = numpy.gradient(self.xy, axis=0)
        self.tangent = tangent / numpy.maximum(numpy.linalg.norm(tangent, axis=1)[:, None], 1e-12)
        self.tree = KDTree(count)
        for index, (x, y) in enumerate(self.xy.tolist()):
            self.tree.insert((x, y, 0.0), index)
        self.tree.balance()
        self.level = None
        self.depth = None
        self.ground = None

    @property
    def length(self):
        return float(self.s[-1])

    def nearest(self, points):
        index = numpy.zeros(len(points), dtype=int)
        distance = numpy.zeros(len(points))
        for row, (x, y) in enumerate(numpy.asarray(points)[:, :2].tolist()):
            _, found, gap = self.tree.find((x, y, 0.0))
            index[row] = found
            distance[row] = gap
        offset = numpy.asarray(points)[:, :2] - self.xy[index]
        side = numpy.sign(self.tangent[index, 0] * offset[:, 1] - self.tangent[index, 1] * offset[:, 0])
        return index, distance, side


def chaikin(points, rounds=2):
    points = numpy.asarray(points, dtype=float)
    for _ in range(rounds):
        if len(points) < 3:
            break
        q = 0.75 * points[:-1] + 0.25 * points[1:]
        r = 0.25 * points[:-1] + 0.75 * points[1:]
        middle = numpy.empty((2 * len(q), points.shape[1]))
        middle[0::2], middle[1::2] = q, r
        points = numpy.concatenate([points[:1], middle, points[-1:]])
    return points


def lowest_line(grid, heights, source, stop):
    """Steepest descent from source over the ground with its depressions filled: the line water takes. Standing water
    (stop) drains its hollow, so a hollow holding a lake fills only down to it."""
    filled = liquid_grid.priority_filled(heights, 1e-5 * grid.cell, stop)
    start = grid.index_of(source[0], source[1])
    nodes = liquid_grid.descend(filled, start, stop)
    if len(nodes) < 3:
        raise bad_args("water from source does not run anywhere: it starts at the edge or in a hollow")
    return numpy.array([(grid.xs[i], grid.ys[j]) for j, i in nodes]), stop is not None and stop[nodes[-1]]


def running_minimum(values):
    return numpy.minimum.accumulate(values)


def smooth_profile(values, window):
    if window < 2:
        return values
    kernel = numpy.ones(window) / window
    padded = numpy.concatenate([numpy.full(window, values[0]), values, numpy.full(window, values[-1])])
    return numpy.convolve(padded, kernel, mode="same")[window:-window]


def levels(path, ground, depth, mouth_level, taper, carved=False):
    """Water level along the path, never rising downstream, easing into the level of the water it ends in. A river that
    carves its channel runs in it, FREEBOARD of its depth below the ground of its line (the banks stand above the water,
    as in a channel at normal flow); one that does not stands depth above that ground, so it can only fill a hollow line
    and spills over flat ground beside it. The depth tapers to nothing over the first metres from the source."""
    profile = numpy.array([ground.height_at(x, y) for x, y in path.xy.tolist()])
    if numpy.isnan(profile).all():
        raise bad_args("the river path does not cross the ground")
    profile = numpy.where(numpy.isnan(profile), numpy.nanmax(profile), profile)
    ends = numpy.clip(numpy.minimum(path.s, path.length - path.s if mouth_level is None else numpy.inf) / max(END_TAPER * depth / 0.15, 1e-6), 0.0, 1.0)
    path.depth = depth * numpy.sqrt(ends)
    path.ground = profile
    level = running_minimum(profile - FREEBOARD * path.depth if carved else profile + path.depth)
    if mouth_level is not None:
        share = numpy.clip((path.length - path.s) / max(taper, 1e-6), 0.0, 1.0)
        level = mouth_level + numpy.maximum(level - mouth_level, 0.0) * share
    level = running_minimum(smooth_profile(level, max(int(taper / max(path.s[1], 1e-9) / 8), 1)))
    if mouth_level is not None:
        level = mouth_level + numpy.maximum(level - mouth_level, 0.0) * share
    path.level = level
    return level


def carve(objects, path, width, depth):
    """Lower the ground into a parabolic bed under the river and banks of slope 1:2 up to the old ground."""
    half = width / 2.0
    carved = 0
    for obj in objects:
        mesh = obj.data
        matrix = obj.matrix_world
        inverse = matrix.inverted()
        world = [matrix @ vertex.co for vertex in mesh.vertices]
        points = numpy.array([point[:] for point in world])
        rise = float(numpy.max(path.ground - path.level)) if path.ground is not None else 0.0
        reach = half + (max(rise, 0.0) + depth) / BANK_SLOPE + 2.0 * depth
        low, high = path.xy.min(axis=0) - reach, path.xy.max(axis=0) + reach
        near = numpy.nonzero(numpy.all((points[:, :2] >= low) & (points[:, :2] <= high), axis=1))[0]
        if not len(near):
            continue
        index, distance, _ = path.nearest(points[near])
        here = path.depth[index] if path.depth is not None else depth
        bed = path.level[index] - here
        target = numpy.where(distance <= half, bed + here * (distance / half) ** 2, path.level[index] + (distance - half) * BANK_SLOPE)
        lower = target < points[near, 2]
        for row in near[lower].tolist():
            world[row].z = float(target[numpy.searchsorted(near, row)])
            mesh.vertices[row].co = inverse @ world[row]
            carved += 1
        mesh.update()
    return carved


def manning_speed(depth, width, slope, roughness):
    radius = depth * width / (width + 2.0 * depth)
    return radius ** (2.0 / 3.0) * numpy.sqrt(numpy.maximum(slope, MIN_SLOPE)) / roughness


def flow_fields(path, points, width, depth, roughness):
    index, distance, side = path.nearest(points)
    slope = -numpy.gradient(path.level, path.s)
    slope = numpy.maximum(slope, MIN_SLOPE)
    speed = manning_speed(depth, width, slope[index], roughness)
    flow = numpy.column_stack([path.tangent[index] * speed[:, None], numpy.zeros(len(points))])
    uvs = numpy.column_stack([0.5 + side * distance / width, path.s[index]])
    foam = numpy.clip((slope[index] - RAPIDS[0]) / (RAPIDS[1] - RAPIDS[0]), 0.0, 1.0)
    return flow, speed, uvs, foam, slope


def region(grid, heights, path, width, overlap, excluded):
    x, y = grid.node_points()
    nodes = numpy.column_stack([x.ravel(), y.ravel()])
    index, distance, _ = path.nearest(nodes)
    level = path.level[index].reshape(heights.shape)
    band = (distance <= width / 2.0 + 3.0 * grid.cell + width).reshape(heights.shape)
    below = band & ~numpy.isnan(heights) & (heights < level) & ~excluded
    seeds = []
    for px, py in path.xy[:: max(len(path.xy) // 200, 1)].tolist():
        j = int(round((py - grid.origin[1]) / grid.cell))
        i = int(round((px - grid.origin[0]) / grid.cell))
        if 0 <= j < grid.rows and 0 <= i < grid.columns:
            seeds.append((j, i))
    wet = liquid_grid.flood(below, seeds)
    from .liquid_bodies import dilate

    return level, (wet | dilate(wet)) & ~excluded, wet


def mouth_level(grid, water, end, width, median):
    """The level a river eases into at its mouth: MOUTH_TUCK under the lowest wave trough of the water around the mouth,
    sampled four times finer than the grid. Where the lake's shore edge reaches over the river, the river then lies under
    it, so the two surfaces never coincide (no z-fighting) and no dry bed shows between them."""
    reach = 2.0 * width + MOUTH_REACH * grid.cell
    steps = numpy.arange(-reach, reach + 1e-9, grid.cell / 4.0)
    lowest = math.inf
    for dx in steps:
        for dy in steps:
            hit = water.tree.ray_cast(Vector((end[0] + dx, end[1] + dy, water.low[2] - 1000.0)), Vector((0.0, 0.0, 1.0)))
            if hit[0] is not None:
                lowest = min(lowest, hit[0].z)
    return (lowest if math.isfinite(lowest) else median) - MOUTH_TUCK


def under_water(grid, water):
    if water is None or water.empty:
        return numpy.zeros((grid.rows, grid.columns), dtype=bool), None
    x, y = grid.node_points()
    points = numpy.column_stack([x.ravel(), y.ravel(), numpy.full(x.size, water.low[2] - 1000.0)])
    inside = numpy.zeros(x.size, dtype=bool)
    near = numpy.nonzero((points[:, 0] >= water.low[0]) & (points[:, 0] <= water.high[0]) & (points[:, 1] >= water.low[1]) & (points[:, 1] <= water.high[1]))[0]
    levels_found = []
    for row in near.tolist():
        hit = water.tree.ray_cast(Vector(points[row]), Vector((0.0, 0.0, 1.0)))
        if hit[0] is not None:
            inside[row] = True
            levels_found.append(hit[0].z)
    return inside.reshape(grid.rows, grid.columns), (float(numpy.median(levels_found)) if levels_found else None)
