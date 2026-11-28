"""Sun, water and shade on the field grid.

What the scene gives the meadow fields: the sun, the water of liquid_body and liquid_fill, and the objects that cast
shade or shed water (trees, shrubs, rocks), all measured on the field grid."""
import math

import bpy
import numpy
from mathutils import Vector

from . import liquid_world
from .meadow_grid import gaussian, raster_mean

OVERHEAD = (0.0, 0.0, 1.0)
LOWEST_SUN = math.radians(5.0)
CANOPY_BLUR = 1.0
SHADOW_REACH = 150.0
CASTER_LIFT = 0.05
WATER_REACH = 200.0
MOST_FACE_SAMPLES = 4096


def sun_direction(scene):
    """Unit vector towards the strongest sun lamp of the scene, kept at least 5 degrees above the horizon; straight up
    when there is none."""
    suns = [obj for obj in scene.objects if obj.type == "LIGHT" and obj.data.type == "SUN" and not obj.hide_render]
    if not suns:
        return numpy.array(OVERHEAD)
    strongest = max(suns, key=lambda obj: obj.data.energy)
    toward = numpy.array(strongest.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0)))
    toward /= max(numpy.linalg.norm(toward), 1e-12)
    flat = math.hypot(toward[0], toward[1])
    if math.atan2(toward[2], flat) < LOWEST_SUN:
        toward = numpy.array([toward[0] / max(flat, 1e-12) * math.cos(LOWEST_SUN), toward[1] / max(flat, 1e-12) * math.cos(LOWEST_SUN), math.sin(LOWEST_SUN)])
    return toward


def water_measures(grid, scene):
    """Per cell: under water or not, the distance in metres to the nearest water surface and the height above it, from the
    scene's liquids. Without liquids every cell is dry and WATER_REACH from water."""
    liquids = liquid_world.liquid_objects(scene)
    shape = grid.shape
    distance = numpy.full(shape, WATER_REACH)
    above = numpy.full(shape, WATER_REACH)
    wet = numpy.zeros(shape, dtype=bool)
    if not liquids:
        return wet, distance, above
    water = liquid_world.Water(liquids)
    if water.empty:
        return wet, distance, above
    xs, ys = grid.centres()
    points = numpy.column_stack([xs.ravel(), ys.ravel(), grid.heights.ravel()])
    flat_distance, flat_above, flat_wet = distance.ravel(), above.ravel(), wet.ravel()
    up = Vector((0.0, 0.0, 1.0))
    tree = water.tree
    for index in numpy.nonzero(water.near(points, WATER_REACH))[0].tolist():
        point = Vector(points[index])
        hit = tree.ray_cast(point, up)
        if hit[0] is not None and point.z <= water.high[2] + 1e-9:
            flat_wet[index] = True
            flat_distance[index] = 0.0
            flat_above[index] = point.z - hit[0].z
            continue
        location, _, _, gap = tree.find_nearest(point, WATER_REACH)
        if location is not None:
            flat_distance[index] = gap
            flat_above[index] = point.z - location.z
    return wet, distance, above


def surface_samples(obj, depsgraph, spacing):
    """Points over the evaluated surface of obj in world space: its vertices and, on every triangle wider than spacing,
    seeded random points about spacing apart, so a big face shades its whole footprint."""
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        local = numpy.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", local)
        mesh.calc_loop_triangles()
        triangles = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("vertices", triangles)
    finally:
        evaluated.to_mesh_clear()
    matrix = numpy.array(obj.matrix_world)
    world = local.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]
    if not len(triangles):
        return world
    corners = world[triangles.reshape(-1, 3)]
    areas = 0.5 * numpy.linalg.norm(numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    counts = numpy.minimum(numpy.floor(areas / (spacing * spacing)).astype(int), MOST_FACE_SAMPLES)
    owners = numpy.repeat(numpy.arange(len(corners)), counts)
    if not len(owners):
        return world
    rng = numpy.random.default_rng([len(world), len(owners)])
    root = numpy.sqrt(rng.uniform(size=len(owners)))
    second = rng.uniform(size=len(owners))
    weights = numpy.column_stack([1.0 - root, root * (1.0 - second), root * second])
    return numpy.concatenate([world, numpy.einsum("ij,ijk->ik", weights, corners[owners])])


def caster_points(objects, depsgraph, spacing):
    found = [surface_samples(obj, depsgraph, spacing) for obj in objects if obj.type == "MESH"]
    return numpy.concatenate(found) if found else numpy.zeros((0, 3))


def canopy_shadow(grid, points, sun):
    """Share of each cell in the shadow of the points: each point above the ground is moved along the sun onto the
    ground, the cells it lands in are shaded and the result is blurred by a metre."""
    if not len(points):
        return numpy.zeros(grid.shape)
    ground = grid.sample(grid.heights, points)
    lift = points[:, 2] - ground
    keep = lift > CASTER_LIFT
    if not keep.any():
        return numpy.zeros(grid.shape)
    lifted = points[keep]
    shift = sun[:2] / max(sun[2], 1e-6)
    landed = lifted[:, :2] - shift[None, :] * lift[keep][:, None]
    inside = (landed[:, 0] >= grid.low[0]) & (landed[:, 1] >= grid.low[1]) & (landed[:, 0] < grid.low[0] + grid.columns * grid.cell) & (landed[:, 1] < grid.low[1] + grid.rows * grid.cell)
    if not inside.any():
        return numpy.zeros(grid.shape)
    _, hit = raster_mean(grid, landed[inside], numpy.ones(int(inside.sum())))
    return numpy.clip(1.6 * gaussian(hit.astype(float), CANOPY_BLUR / grid.cell), 0.0, 1.0)


def footprint(grid, points, reach):
    """Share of each cell within about reach metres of the points' ground footprint."""
    if not len(points):
        return numpy.zeros(grid.shape)
    inside = (points[:, 0] >= grid.low[0]) & (points[:, 1] >= grid.low[1]) & (points[:, 0] < grid.low[0] + grid.columns * grid.cell) & (points[:, 1] < grid.low[1] + grid.rows * grid.cell)
    if not inside.any():
        return numpy.zeros(grid.shape)
    _, hit = raster_mean(grid, points[inside], numpy.ones(int(inside.sum())))
    return numpy.clip(2.0 * gaussian(hit.astype(float), max(reach, 0.5 * grid.cell) / grid.cell), 0.0, 1.0)


def terrain_shadow(grid, sun):
    """1 where the terrain hides the sun from the cell, marching towards the sun up to SHADOW_REACH metres."""
    flat = math.hypot(sun[0], sun[1])
    if flat < 1e-6:
        return numpy.zeros(grid.shape)
    rise = sun[2] / flat
    direction = numpy.array([sun[0], sun[1]]) / flat
    xs, ys = grid.centres()
    shade = numpy.zeros(grid.shape, dtype=bool)
    steps = int(min(SHADOW_REACH, max(grid.rows, grid.columns) * grid.cell) / grid.cell)
    for step in range(1, steps + 1):
        run = step * grid.cell
        column = numpy.clip(((xs + direction[0] * run - grid.low[0]) / grid.cell).astype(int), 0, grid.columns - 1)
        row = numpy.clip(((ys + direction[1] * run - grid.low[1]) / grid.cell).astype(int), 0, grid.rows - 1)
        shade |= grid.heights[row, column] > grid.heights + run * rise
    return shade.astype(float)


def incidence(grid, sun):
    """Direct sun on each cell relative to level ground, cos(incidence) / sin(elevation): below 1 on slopes facing away,
    above 1 on slopes facing the sun."""
    dy, dx = numpy.gradient(grid.heights, grid.cell)
    normals = numpy.stack([-dx, -dy, numpy.ones_like(dx)], axis=-1)
    normals /= numpy.linalg.norm(normals, axis=-1, keepdims=True)
    return numpy.maximum(normals @ sun, 0.0) / max(sun[2], 1e-6)


def scene_objects(names):
    return [bpy.data.objects[name] for name in names]
