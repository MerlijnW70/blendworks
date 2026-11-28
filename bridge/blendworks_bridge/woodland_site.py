"""Ground height, water and moisture.

The ground a woodland stands on: its height and slope under each plan point from the evaluated ground meshes, dry
or under water from the scene's liquids, and a moisture index 0 to 1 from the distance to water and the lowness of the
ground against its surroundings (a topographic position index; damp hollows and shores are wet, rises dry)."""
import math

import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import liquid_world
from .land_field import smoothstep

DOWN = Vector((0.0, 0.0, -1.0))
WATER_REACH = 80.0
WATER_DECAY = 15.0
LOWNESS_RADIUS = 40.0
LOWNESS_DEPTH = 3.0
LOWNESS_SAMPLES = 8
MOISTURE_CELL = 4.0
DRY_REACH = 0.5


def world_triangles(objects, depsgraph):
    vertices, faces = [], []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        local = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float64)
        mesh.vertices.foreach_get("co", local)
        matrix = numpy.array(obj.matrix_world)
        points = local.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]
        corners = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("vertices", corners)
        faces.append(corners.reshape(-1, 3) + sum(len(part) for part in vertices))
        vertices.append(points)
        evaluated.to_mesh_clear()
    points = numpy.concatenate(vertices)
    return points, numpy.concatenate(faces)


class Site:
    def __init__(self, ground, depsgraph, scene, max_slope):
        points, faces = world_triangles(ground, depsgraph)
        self.tree = BVHTree.FromPolygons([Vector(point) for point in points.tolist()], faces.tolist())
        self.top = float(points[:, 2].max()) + 100.0
        self.low = points[:, :2].min(axis=0)
        self.high = points[:, :2].max(axis=0)
        self.water = liquid_world.Water(liquid_world.liquid_objects(scene))
        self.max_slope = max_slope
        self.cache = {}

    def surface(self, xy):
        heights = numpy.full(len(xy), numpy.nan)
        normals = numpy.tile([0.0, 0.0, 1.0], (len(xy), 1))
        for index, (x, y) in enumerate(xy.tolist()):
            hit = self.tree.ray_cast(Vector((x, y, self.top)), DOWN)
            if hit[0] is not None:
                heights[index] = hit[0].z
                normals[index] = tuple(hit[1]) if hit[1].z >= 0.0 else tuple(-hit[1])
        return heights, normals

    def lowness(self, xy, heights):
        total = numpy.zeros(len(xy))
        found = numpy.zeros(len(xy))
        for step in range(LOWNESS_SAMPLES):
            angle = 2.0 * math.pi * step / LOWNESS_SAMPLES
            around, _ = self.surface(xy + LOWNESS_RADIUS * numpy.array([math.cos(angle), math.sin(angle)]))
            seen = ~numpy.isnan(around)
            total[seen] += around[seen]
            found[seen] += 1.0
        mean = numpy.where(found > 0, total / numpy.maximum(found, 1.0), heights)
        return smoothstep(0.0, LOWNESS_DEPTH, mean - heights)

    def moisture_grid(self):
        """Moisture on a grid of MOISTURE_CELL metres over the ground, built once: it varies over tens of metres."""
        if "moisture" not in self.cache:
            columns = int(numpy.ceil((self.high[0] - self.low[0]) / MOISTURE_CELL)) + 1
            rows = int(numpy.ceil((self.high[1] - self.low[1]) / MOISTURE_CELL)) + 1
            grid_x, grid_y = numpy.meshgrid(self.low[0] + MOISTURE_CELL * numpy.arange(columns), self.low[1] + MOISTURE_CELL * numpy.arange(rows))
            cells = numpy.column_stack([grid_x.ravel(), grid_y.ravel()])
            heights, _ = self.surface(cells)
            on = ~numpy.isnan(heights)
            depth = numpy.full(len(cells), -WATER_REACH)
            if on.any():
                depth[on] = self.water.signed_depth(numpy.column_stack([cells[on], heights[on]]), WATER_REACH)
            wet = numpy.exp(-numpy.maximum(-depth, 0.0) / WATER_DECAY)
            low = self.lowness(cells, numpy.where(on, heights, 0.0))
            self.cache["moisture"] = numpy.where(on, numpy.maximum(wet, low), 0.0).reshape(rows, columns)
        return self.cache["moisture"]

    def moisture(self, xy):
        grid = self.moisture_grid()
        rows, columns = grid.shape
        u = numpy.clip((xy[:, 0] - self.low[0]) / MOISTURE_CELL, 0.0, columns - 1.000001)
        v = numpy.clip((xy[:, 1] - self.low[1]) / MOISTURE_CELL, 0.0, rows - 1.000001)
        i, j = v.astype(int), u.astype(int)
        fv, fu = v - i, u - j
        return (grid[i, j] * (1 - fu) + grid[i, j + 1] * fu) * (1 - fv) + (grid[i + 1, j] * (1 - fu) + grid[i + 1, j + 1] * fu) * fv

    def __call__(self, xy):
        xy = numpy.asarray(xy, dtype=numpy.float64).reshape(-1, 2)
        heights, normals = self.surface(xy)
        on = ~numpy.isnan(heights)
        dry = numpy.ones(len(xy), dtype=bool)
        if on.any() and not self.water.empty:
            dry[on] = self.water.signed_depth(numpy.column_stack([xy[on], heights[on]]), DRY_REACH) < 0.0
        slope = numpy.degrees(numpy.arccos(numpy.clip(normals[:, 2], -1.0, 1.0)))
        ok = on & dry & (slope <= self.max_slope)
        return {"ok": ok, "z": numpy.where(on, heights, 0.0), "moisture": numpy.where(on, self.moisture(xy), 0.0), "normal": normals}
