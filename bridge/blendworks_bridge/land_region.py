"""What distant land needs to know about the region it surrounds: its rectangle, its heights on a grid and along its
border, its water, its vertex spacing and its material, all measured from the evaluated objects in world space."""
import math

import bpy
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import liquid_world
from .errors import bad_args

STAT_CELLS = 160
LEAST_STAT_CELLS = 32
BORDER_EPSILON = 1e-3
INSET = 1e-3
DOWN = Vector((0.0, 0.0, -1.0))
SPACING_SAMPLE = 20_000


def evaluated_triangles(objects, depsgraph):
    corners, faces = [], []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if mesh is None:
                continue
            mesh.calc_loop_triangles()
            count = len(mesh.vertices)
            local = numpy.empty(count * 3, dtype=numpy.float32)
            mesh.vertices.foreach_get("co", local)
            matrix = numpy.array(evaluated.matrix_world, dtype=numpy.float64)
            world = local.reshape(-1, 3).astype(numpy.float64) @ matrix[:3, :3].T + matrix[:3, 3]
            triangles = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
            mesh.loop_triangles.foreach_get("vertices", triangles)
            offset = sum(len(part) for part in corners)
            corners.append(world)
            faces.append(triangles.reshape(-1, 3) + offset)
        finally:
            evaluated.to_mesh_clear()
    if not corners:
        return numpy.zeros((0, 3)), numpy.zeros((0, 3), dtype=numpy.int64)
    return numpy.concatenate(corners), numpy.concatenate(faces)


class Surface:
    """Heights of a set of objects seen from above, by ray casts down onto their evaluated triangles."""

    def __init__(self, objects, depsgraph):
        self.points, self.faces = evaluated_triangles(objects, depsgraph)
        self.empty = len(self.faces) == 0
        if not self.empty:
            self.tree = BVHTree.FromPolygons([Vector(p) for p in self.points], self.faces.tolist())
            self.top = float(self.points[:, 2].max()) + 1.0

    def heights(self, xy):
        result = numpy.full(len(xy), numpy.nan)
        if self.empty:
            return result
        for index, (x, y) in enumerate(numpy.asarray(xy, dtype=numpy.float64).tolist()):
            hit = self.tree.ray_cast(Vector((x, y, self.top)), DOWN)
            if hit[0] is not None:
                result[index] = hit[0].z
        return result


def median_spacing(points, faces):
    if len(faces) == 0:
        return 1.0
    chosen = faces[:: max(1, len(faces) // SPACING_SAMPLE)]
    edges = numpy.linalg.norm(points[chosen[:, 0], :2] - points[chosen[:, 1], :2], axis=1)
    edges = edges[edges > 1e-9]
    return float(numpy.median(edges)) if len(edges) else 1.0


class Region:
    def __init__(self, ctx, terrain=None, bounds=None, ground=None, water_level=None):
        depsgraph = ctx.depsgraph()
        if terrain:
            self.objects = terrain
        elif ground is not None:
            self.objects = [ground]
        else:
            raise bad_args("give terrain, or bounds with ground")
        self.ground = Surface(self.objects, depsgraph)
        if self.ground.empty:
            raise bad_args("the region has no faces to measure")
        if bounds is not None:
            low, high = bounds["min"], bounds["max"]
        else:
            low, high = self.ground.points[:, :2].min(axis=0), self.ground.points[:, :2].max(axis=0)
        if high[0] - low[0] <= 0.0 or high[1] - low[1] <= 0.0:
            raise bad_args("the region has no area seen from above")
        self.low = numpy.array(low[:2], dtype=numpy.float64)
        self.high = numpy.array(high[:2], dtype=numpy.float64)
        self.spacing = median_spacing(self.ground.points, self.ground.faces)
        liquids = [obj for obj in liquid_world.liquid_objects(ctx.scene) if obj.visible_get(view_layer=ctx.view_layer)]
        self.water = liquid_world.Water(liquids)
        self.water_surface = Surface(liquids, depsgraph) if liquids else None
        self.water_level = water_level

    def size(self):
        return self.high - self.low

    def wet(self, xy, ground):
        wet = numpy.zeros(len(xy), dtype=bool)
        if self.water_level is not None:
            wet |= ground < self.water_level
        if not self.water.empty:
            depth = self.water.signed_depth(numpy.column_stack([xy, ground]))
            wet |= depth > 0.0
        return wet

    def surface_heights(self, xy):
        """Ground heights, raised to the water surface where there is water: what the land continues."""
        ground = self.ground.heights(xy)
        wet = self.wet(xy, numpy.nan_to_num(ground, nan=-1e30))
        top = ground.copy()
        if self.water_surface is not None:
            water = self.water_surface.heights(xy)
            top = numpy.where(wet & ~numpy.isnan(water), numpy.fmax(water, ground), top)
        if self.water_level is not None:
            top = numpy.where(wet, numpy.fmax(top, self.water_level), top)
        return top, wet

    def grid(self, cells=None):
        """A square-celled grid of heights over the region, with its water and the cells that were hit."""
        width, height = self.size()
        longest = max(width, height)
        if cells is None:
            cells = int(min(STAT_CELLS, max(LEAST_STAT_CELLS, math.ceil(longest / max(self.spacing, 1e-6)))))
        spacing = longest / cells
        columns = max(LEAST_STAT_CELLS // 2, int(round(width / spacing)))
        rows = max(LEAST_STAT_CELLS // 2, int(round(height / spacing)))
        xs = self.low[0] + (numpy.arange(columns) + 0.5) * width / columns
        ys = self.low[1] + (numpy.arange(rows) + 0.5) * height / rows
        grid_x, grid_y = numpy.meshgrid(xs, ys)
        xy = numpy.column_stack([grid_x.ravel(), grid_y.ravel()])
        ground = self.ground.heights(xy)
        valid = ~numpy.isnan(ground)
        wet = self.wet(xy, numpy.nan_to_num(ground, nan=-1e30)) & valid
        heights = numpy.where(valid, ground, numpy.nanmean(ground) if valid.any() else 0.0)
        return heights.reshape(rows, columns), wet.reshape(rows, columns), valid.reshape(rows, columns), width / columns

    def border_sides(self, spacing):
        """Four sides of the border, corner to corner, counter-clockwise from (x0, y0): the region's own vertices on the
        border and samples at most `spacing` apart."""
        x0, y0 = self.low
        x1, y1 = self.high
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        points = self.ground.points[:, :2]
        sides = []
        for index in range(4):
            start = numpy.array(corners[index])
            end = numpy.array(corners[(index + 1) % 4])
            direction = end - start
            length = float(numpy.linalg.norm(direction))
            unit = direction / length
            normal = numpy.array([unit[1], -unit[0]])
            along = (points - start) @ unit
            across = (points - start) @ normal
            on = (numpy.abs(across) < BORDER_EPSILON) & (along > 0.0) & (along < length)
            count = max(1, int(math.ceil(length / spacing)))
            samples = numpy.linspace(0.0, length, count + 1)
            fractions = numpy.unique(numpy.round(numpy.concatenate([samples, along[on]]), 6))
            fractions = fractions[(fractions >= 0.0) & (fractions <= length)]
            if fractions[0] > 0.0:
                fractions = numpy.concatenate([[0.0], fractions])
            if fractions[-1] < length:
                fractions = numpy.concatenate([fractions, [length]])
            merged = [fractions[0]]
            for value in fractions[1:]:
                if value - merged[-1] > max(1e-4, spacing * 1e-3) or value == length:
                    merged.append(value)
            if len(merged) > 2 and merged[-1] - merged[-2] <= max(1e-4, spacing * 1e-3):
                del merged[-2]
            sides.append(start[None, :] + numpy.array(merged)[:, None] * unit[None, :])
        return sides

    def inward(self, xy):
        """Points moved a hair into the region, so that rays at the very border still hit it."""
        centre = (self.low + self.high) / 2.0
        direction = numpy.sign(centre[None, :] - xy)
        return xy + direction * INSET


def region_material(objects):
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material is not None:
                return slot.material
    return None


def uv_affine(obj):
    """Least-squares map from world x, y to the object's active UVs, or None without UVs."""
    mesh = obj.data
    if obj.type != "MESH" or mesh.uv_layers.active is None or len(mesh.loops) == 0:
        return None
    count = len(mesh.loops)
    step = max(1, count // SPACING_SAMPLE)
    uv = numpy.empty(count * 2, dtype=numpy.float32)
    mesh.uv_layers.active.data.foreach_get("uv", uv)
    vertex_of = numpy.empty(count, dtype=numpy.int64)
    mesh.loops.foreach_get("vertex_index", vertex_of)
    local = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
    mesh.vertices.foreach_get("co", local)
    matrix = numpy.array(obj.matrix_world, dtype=numpy.float64)
    world = local.reshape(-1, 3).astype(numpy.float64) @ matrix[:3, :3].T + matrix[:3, 3]
    chosen = numpy.arange(0, count, step)
    xy = world[vertex_of[chosen], :2]
    design = numpy.column_stack([xy, numpy.ones(len(xy))])
    solution, *_ = numpy.linalg.lstsq(design, uv.reshape(-1, 2)[chosen].astype(numpy.float64), rcond=None)
    residual = numpy.abs(design @ solution - uv.reshape(-1, 2)[chosen]).max() if len(xy) else 0.0
    return solution if residual < 1e-3 else None


def remove_object(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        return
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
