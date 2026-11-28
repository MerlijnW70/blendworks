"""Flood fill of liquid over a ground grid."""

import heapq
import math

import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .errors import bad_args

MAX_NODES = 1_000_000
DOWN = Vector((0.0, 0.0, -1.0))
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))
EIGHT = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def world_triangles(objects, depsgraph):
    corners, faces = [], []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            matrix = obj.matrix_world
            offset = len(corners)
            corners.extend((matrix @ vertex.co)[:] for vertex in mesh.vertices)
            faces.extend(tuple(offset + index for index in triangle.vertices) for triangle in mesh.loop_triangles)
        finally:
            evaluated.to_mesh_clear()
    if not faces:
        raise bad_args("the surface has no faces")
    return numpy.array(corners, dtype=float), faces


class Ground:
    """The surfaces water can rest on, as a BVH of world triangles, sampled straight down."""

    def __init__(self, objects, depsgraph):
        self.points, self.faces = world_triangles(objects, depsgraph)
        self.tree = BVHTree.FromPolygons([Vector(point) for point in self.points], self.faces)
        self.low = self.points.min(axis=0)
        self.high = self.points.max(axis=0)

    def height_at(self, x, y):
        hit = self.tree.ray_cast(Vector((x, y, self.high[2] + 1.0)), DOWN)[0]
        return math.nan if hit is None else hit.z

    def nearest(self, point):
        return self.tree.find_nearest(Vector(point))


class Grid:
    def __init__(self, origin, cell, columns, rows):
        if columns * rows > MAX_NODES:
            raise bad_args(f"the liquid grid would have {columns * rows} nodes, more than {MAX_NODES}; give a coarser resolution")
        if columns < 3 or rows < 3:
            raise bad_args("the liquid area is smaller than three grid cells; give a finer resolution")
        self.origin = origin
        self.cell = cell
        self.columns = columns
        self.rows = rows
        self.xs = origin[0] + numpy.arange(columns) * cell
        self.ys = origin[1] + numpy.arange(rows) * cell

    @classmethod
    def covering(cls, low, high, cell):
        columns = int(math.ceil((high[0] - low[0]) / cell)) + 1
        rows = int(math.ceil((high[1] - low[1]) / cell)) + 1
        return cls((low[0], low[1]), cell, columns, rows)

    def index_of(self, x, y):
        i = int(round((x - self.origin[0]) / self.cell))
        j = int(round((y - self.origin[1]) / self.cell))
        if not (0 <= i < self.columns and 0 <= j < self.rows):
            raise bad_args("the point lies outside the surface")
        return j, i

    def node_points(self):
        x, y = numpy.meshgrid(self.xs, self.ys)
        return x, y

    def sample(self, ground):
        heights = numpy.full((self.rows, self.columns), numpy.nan)
        for j, y in enumerate(self.ys.tolist()):
            for i, x in enumerate(self.xs.tolist()):
                heights[j, i] = ground.height_at(x, y)
        return heights


def flood(below, seeds):
    """The nodes below the level that are 4-connected to a seed."""
    wet = numpy.zeros_like(below)
    for j, i in seeds:
        if below[j, i]:
            wet[j, i] = True
    if not wet.any():
        return wet
    queue = list(zip(*numpy.nonzero(wet)))
    rows, columns = below.shape
    while queue:
        j, i = queue.pop()
        for dj, di in NEIGHBOURS:
            nj, ni = j + dj, i + di
            if 0 <= nj < rows and 0 <= ni < columns and below[nj, ni] and not wet[nj, ni]:
                wet[nj, ni] = True
                queue.append((nj, ni))
    return wet


def touches_edge(mask):
    return bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())


def spill_level(heights, seed):
    """Lowest level at which water filled from seed reaches the edge of the grid: a minimax path by priority flood."""
    rows, columns = heights.shape
    filled = numpy.where(numpy.isnan(heights), -math.inf, heights)
    best = numpy.full(heights.shape, math.inf)
    j0, i0 = seed
    best[j0, i0] = filled[j0, i0]
    heap = [(best[j0, i0], j0, i0)]
    while heap:
        level, j, i = heapq.heappop(heap)
        if level > best[j, i]:
            continue
        if j in (0, rows - 1) or i in (0, columns - 1):
            return level
        for dj, di in NEIGHBOURS:
            nj, ni = j + dj, i + di
            candidate = max(level, filled[nj, ni])
            if candidate < best[nj, ni]:
                best[nj, ni] = candidate
                heapq.heappush(heap, (candidate, nj, ni))
    return math.inf


def priority_filled(heights, epsilon, outlets=None):
    """Depressions filled so every node drains to the edge, or to an outlet node (standing water), with a small rise per
    step (Barnes, Lehman and Mulla 2014: the priority queue starts from every node that drains)."""
    rows, columns = heights.shape
    filled = numpy.where(numpy.isnan(heights), numpy.nanmax(heights), heights).copy()
    done = numpy.zeros(heights.shape, dtype=bool)
    heap = []
    for j in range(rows):
        for i in range(columns):
            if j in (0, rows - 1) or i in (0, columns - 1) or (outlets is not None and outlets[j, i]):
                heapq.heappush(heap, (filled[j, i], j, i))
                done[j, i] = True
    while heap:
        level, j, i = heapq.heappop(heap)
        for dj, di in EIGHT:
            nj, ni = j + dj, i + di
            if 0 <= nj < rows and 0 <= ni < columns and not done[nj, ni]:
                done[nj, ni] = True
                filled[nj, ni] = max(filled[nj, ni], level + epsilon)
                heapq.heappush(heap, (filled[nj, ni], nj, ni))
    return filled


def descend(filled, start, stop=None, limit=100_000):
    """Steepest descent over a filled grid (D8) from start until the edge or a node where stop is true."""
    rows, columns = filled.shape
    path = [start]
    j, i = start
    for _ in range(limit):
        if stop is not None and stop[j, i] and len(path) > 1:
            break
        if j in (0, rows - 1) or i in (0, columns - 1):
            break
        best, step = 0.0, None
        for dj, di in EIGHT:
            nj, ni = j + dj, i + di
            drop = (filled[j, i] - filled[nj, ni]) / math.hypot(dj, di)
            if drop > best:
                best, step = drop, (nj, ni)
        if step is None:
            break
        j, i = step
        path.append(step)
    return path


class Sheet:
    """Triangles of the region where the ground lies below a level field, clipped along the contour by linear interpolation."""

    def __init__(self):
        self.keys = {}
        self.points = []
        self.triangles = []

    def vertex(self, key, point):
        index = self.keys.get(key)
        if index is None:
            index = len(self.points)
            self.keys[key] = index
            self.points.append(point)
        return index

    def arrays(self):
        return numpy.array(self.points, dtype=float).reshape(-1, 3), numpy.array(self.triangles, dtype=int).reshape(-1, 3)


def node_point(grid, level, j, i):
    return (float(grid.xs[i]), float(grid.ys[j]), float(level[j, i]))


def edge_point(grid, level, depth, a, b):
    fa, fb = depth[a], depth[b]
    t = fa / (fa - fb)
    xa, ya, za = node_point(grid, level, *a)
    xb, yb, zb = node_point(grid, level, *b)
    return (xa + t * (xb - xa), ya + t * (yb - ya), za + t * (zb - za))


def clip_triangle(sheet, grid, level, depth, corners):
    values = [depth[corner] for corner in corners]
    if all(value <= 0.0 for value in values):
        return
    polygon = []
    for index, corner in enumerate(corners):
        following = corners[(index + 1) % 3]
        inside = depth[corner] > 0.0
        if inside:
            polygon.append(sheet.vertex(("n",) + corner, node_point(grid, level, *corner)))
        if inside != (depth[following] > 0.0):
            key = ("e",) + tuple(sorted((corner, following)))
            polygon.append(sheet.vertex(key, edge_point(grid, level, depth, corner, following)))
    for index in range(1, len(polygon) - 1):
        sheet.triangles.append((polygon[0], polygon[index], polygon[index + 1]))


def level_sheet(grid, heights, level, region, overlap=0.0):
    """Water surface over region: depth = level + overlap - ground, positive where wet; NaN ground counts as dry."""
    depth = numpy.where(numpy.isnan(heights), -1.0, level + overlap - heights)
    depth = numpy.where(region, depth, numpy.minimum(depth, -1e-9))
    sheet = Sheet()
    touched = region[:-1, :-1] | region[1:, :-1] | region[:-1, 1:] | region[1:, 1:]
    for j, i in zip(*numpy.nonzero(touched)):
        j, i = int(j), int(i)
        a, b, c, d = (j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)
        clip_triangle(sheet, grid, level, depth, (a, b, c))
        clip_triangle(sheet, grid, level, depth, (a, c, d))
    return sheet.arrays()


def triangle_areas(points, triangles):
    if len(triangles) == 0:
        return numpy.zeros(0)
    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    return 0.5 * numpy.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))


def held_volume(grid, heights, level, region):
    """Volume of water between the ground and the level over region, by the trapezoid rule on the grid."""
    depth = numpy.where(region & ~numpy.isnan(heights), numpy.maximum(level - heights, 0.0), 0.0)
    return float(depth.sum() * grid.cell * grid.cell)
