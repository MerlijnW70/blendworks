"""The meadow structure fields.

The meadow's structure fields: smooth, seeded fields over the ground that the cover and the ground material read.

- moisture (0 dry to 1 waterlogged): the topographic wetness index ln(a / tan b) (Beven and Kirkby 1979) from
  multiple-flow-direction upslope area (Freeman 1991), nearness to water and height above it, low ground against its
  surroundings, shade and slopes turned from the sun, and a broad seeded noise for soil texture over about 150 m.
- soil depth (0 thin to 1 deep): deeper in hollows and thinner on crests and steep ground, as soil production and creep
  leave it (Heimsath et al. 1997), with a broad seeded noise.
- disturbance (0 to 1): the tread and worn verge of the paths, trodden patches where animals stand and gather, and
  poached ground where the paths reach the water.
- shade (0 full sun to 1 deep shade): canopy and rock shadows cast along the sun onto the ground, terrain shadow, slopes
  turned from the sun, and any meadow_canopy attribute already on the ground.
- grazing (0 ungrazed to 1 short): a patch mosaic of grazed lawns and rejected tall patches 4 to 12 m across (Adler et al.
  2001), heavier near water and along paths (Andrew 1988), lighter on steep slopes.
"""
import json
import math

import numpy

from . import liquid_world
from .meadow_grid import curvature, height_grid, relative_height, slope_tangent, wetness_index
from .meadow_inputs import canopy_shadow, caster_points, footprint, incidence, sun_direction, terrain_shadow, water_measures
from .meadow_paths import path_distance, path_network
from .noise_stack import stack_value

FIELDS = ("moisture", "soil", "disturbance", "shade", "grazing")
PREFIX = "meadow_"
PRESENCE = "meadow_fields"
CANOPY_INPUT = "meadow_canopy"
PATHS_PROPERTY = "meadow_paths"
SIGNATURE_PROPERTY = "meadow_signature"
SMALLEST_SLOPE = 0.01
FLOW_CELL = 2.0
WETNESS_DRY = 4.0
WETNESS_WET = 14.0
MOISTURE_BASE = 0.25
WATER_DISTANCE = 15.0
CAPILLARY_RISE = 1.5
POSITION_RADIUS = 40.0
POSITION_SPAN = 2.5
CURVATURE_SMOOTHING = 4.0
CURVATURE_SPAN = 0.02
STEEP_TANGENT = 0.7
TREAD_HALF_WIDTH = 0.3
VERGE_HALF_WIDTH = 1.2
PATH_REACH = 50.0
TRAMPLED_AREA = 2000.0
TRAMPLED_RADIUS = (1.5, 4.0)
POACHED_RADIUS = 4.0
ROCK_RUNOFF = 0.6
PIOSPHERE_WATER = 30.0
PIOSPHERE_PATH = 8.0


def noise(points, scale, octaves, seed, hurst=0.6):
    params = {"seed": int(seed), "basis": "perlin", "scale": scale, "octaves": octaves, "lacunarity": 2.0, "hurst": hurst, "mode": "fbm", "ridge_offset": 1.0}
    flat = numpy.column_stack([points[:, 0], points[:, 1], numpy.zeros(len(points))])
    return numpy.clip(stack_value(flat, params) / 0.6, -1.0, 1.0)


def smoothstep(low, high, values):
    t = numpy.clip((values - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Settings:
    def __init__(self, seed=0, shade=(), obstacles=(), paths="auto", path_points=None):
        self.seed = int(seed)
        self.shade = list(shade)
        self.obstacles = list(obstacles)
        self.paths = paths
        self.path_points = path_points


class Terrain:
    """The grid measures, computed once for all targets of a call."""

    def __init__(self, points, scene, depsgraph, settings):
        grid = height_grid(points)
        self.grid = grid
        self.sun = sun_direction(scene)
        flow = height_grid(points, smallest=FLOW_CELL)
        self.flow = flow
        self.wetness = smoothstep(WETNESS_DRY, WETNESS_WET, wetness_index(flow, SMALLEST_SLOPE))
        self.position = numpy.clip(-relative_height(grid, POSITION_RADIUS) / POSITION_SPAN, -1.0, 1.0)
        self.curvature = numpy.clip(curvature(grid, CURVATURE_SMOOTHING) / CURVATURE_SPAN, -1.0, 1.0)
        self.steep = numpy.clip(slope_tangent(grid) / STEEP_TANGENT, 0.0, 1.0)
        self.wet, self.water_distance, self.water_above = water_measures(grid, scene)
        casters = caster_points(settings.shade, depsgraph, 0.5 * grid.cell)
        rocks = caster_points(settings.obstacles, depsgraph, 0.5 * grid.cell)
        self.canopy = canopy_shadow(grid, casters, self.sun)
        self.runoff = footprint(grid, rocks, ROCK_RUNOFF)
        self.cast = terrain_shadow(grid, self.sun)
        self.light = incidence(grid, self.sun)
        self.lines = self.paths(settings)
        self.trampled = self.trampled_patches(settings)

    def paths(self, settings):
        if settings.paths == "none":
            return []
        return path_network(self.grid, self.wet, settings.seed, settings.path_points)

    def trampled_patches(self, settings):
        """Trodden patches: one per TRAMPLED_AREA square metres on average, 1.5 to 4 m in radius, where the grid is fine
        enough to hold them; and poached ground at every path end beside the water."""
        grid = self.grid
        rng = numpy.random.default_rng([settings.seed, 0x7A3])
        area = grid.rows * grid.columns * grid.cell * grid.cell
        count = int(rng.poisson(area / TRAMPLED_AREA)) if grid.cell <= TRAMPLED_RADIUS[1] else 0
        centres = grid.low + rng.uniform(size=(count, 2)) * numpy.array([grid.columns, grid.rows]) * grid.cell
        radii = list(rng.uniform(*TRAMPLED_RADIUS, count))
        centres = [tuple(centre) for centre in centres.tolist()]
        self.patch_count = count
        for line in self.lines:
            for end in (line[0], line[-1]):
                distance = grid.sample(self.water_distance, numpy.array([end[:2]]))[0]
                if distance < 3.0 * grid.cell + POACHED_RADIUS:
                    centres.append((end[0], end[1]))
                    radii.append(POACHED_RADIUS)
        values = numpy.zeros(grid.shape)
        xs, ys = grid.centres()
        for (x, y), radius in zip(centres, radii):
            low_c = max(0, int((x - 3 * radius - grid.low[0]) / grid.cell))
            high_c = min(grid.columns, int((x + 3 * radius - grid.low[0]) / grid.cell) + 1)
            low_r = max(0, int((y - 3 * radius - grid.low[1]) / grid.cell))
            high_r = min(grid.rows, int((y + 3 * radius - grid.low[1]) / grid.cell) + 1)
            if low_c >= high_c or low_r >= high_r:
                continue
            gap = numpy.hypot(xs[low_r:high_r, low_c:high_c] - x, ys[low_r:high_r, low_c:high_c] - y)
            values[low_r:high_r, low_c:high_c] = numpy.maximum(values[low_r:high_r, low_c:high_c], 0.85 * numpy.exp(-(gap / radius) ** 4))
        return values

    def fields(self, points, canopy_input, seed):
        """The five fields at world points, each 0 to 1."""
        grid = self.grid
        sample = lambda values: grid.sample(values, points)
        wet = sample(self.wet.astype(float)) > 0.5
        distance = sample(self.water_distance)
        above = numpy.maximum(sample(self.water_above), 0.0)
        water = numpy.exp(-distance / WATER_DISTANCE) * numpy.exp(-above / CAPILLARY_RISE)
        canopy = numpy.maximum(sample(self.canopy), canopy_input)
        light = sample(self.light)
        cast = sample(self.cast)
        turned = numpy.clip(1.0 - light, 0.0, 1.0)
        shade = 1.0 - (1.0 - canopy) * (1.0 - 0.75 * cast) * (1.0 - 0.6 * turned)
        broad = noise(points, 150.0, 3, seed * 31 + 1)
        wetness = self.flow.sample(self.wetness, points)
        moisture = MOISTURE_BASE + 0.42 * wetness + 0.55 * water + 0.12 * sample(self.position) + 0.12 * shade
        moisture += 0.12 * broad - 0.12 * numpy.clip(light - 1.0, 0.0, 1.0) + 0.2 * sample(self.runoff)
        moisture = numpy.where(wet, 1.0, numpy.clip(moisture, 0.0, 1.0))
        soil = 0.5 + 0.35 * sample(self.curvature) - 0.5 * sample(self.steep) + 0.15 * wetness + 0.15 * noise(points, 80.0, 3, seed * 31 + 2)
        tread = path_distance(self.lines, points, PATH_REACH)
        worn = 1.0 - smoothstep(TREAD_HALF_WIDTH, VERGE_HALF_WIDTH, tread)
        disturbance = numpy.maximum(worn, sample(self.trampled))
        patches = noise(points, 12.0, 3, seed * 31 + 3, 0.5)
        grazing = 0.45 + 0.65 * patches + 0.25 * numpy.exp(-tread / PIOSPHERE_PATH) + 0.2 * numpy.exp(-distance / PIOSPHERE_WATER) - 0.3 * sample(self.steep)
        return {
            "moisture": moisture,
            "soil": numpy.clip(soil, 0.0, 1.0),
            "disturbance": numpy.clip(disturbance, 0.0, 1.0),
            "shade": numpy.clip(shade, 0.0, 1.0),
            "grazing": numpy.clip(grazing, 0.0, 1.0),
        }


def geometry_signature(points):
    return liquid_world.signature(points, "meadow")


def write_fields(obj, values, points, lines):
    mesh = obj.data
    for name in FIELDS:
        liquid_world.write_point_attribute(mesh, PREFIX + name, values[name])
    liquid_world.write_point_attribute(mesh, PRESENCE, numpy.ones(len(points)))
    mesh[PATHS_PROPERTY] = json.dumps(lines)
    mesh[SIGNATURE_PROPERTY] = geometry_signature(points)
    mesh.update()


def read_attribute(mesh, name, count):
    attribute = mesh.attributes.get(name)
    if attribute is None or attribute.domain != "POINT" or attribute.data_type != "FLOAT" or len(attribute.data) != count:
        return None
    values = numpy.zeros(count, dtype=numpy.float32)
    attribute.data.foreach_get("value", values)
    return values.astype(float)


def stored_fields(obj, points):
    """The fields already on obj, when they were computed for its current geometry."""
    mesh = obj.data
    if mesh.get(SIGNATURE_PROPERTY) != geometry_signature(points):
        return None
    values = {}
    for name in FIELDS:
        found = read_attribute(mesh, PREFIX + name, len(points))
        if found is None:
            return None
        values[name] = found
    return values, json.loads(mesh.get(PATHS_PROPERTY, "[]"))


def compute(targets, scene, depsgraph, settings):
    """The fields at every evaluated vertex of every target, from one terrain grid over all of them, written on each target
    whose modifiers keep its vertex count. Returns {name: values}, the path polylines and a report."""
    points = {obj.name: liquid_world.vertex_points(obj, depsgraph) for obj in targets}
    union = numpy.concatenate(list(points.values()))
    terrain = Terrain(union, scene, depsgraph, settings)
    result, written, skipped = {}, [], []
    for obj in targets:
        own = points[obj.name]
        canopy_input = numpy.zeros(len(own))
        if len(obj.data.vertices) == len(own):
            given = read_attribute(obj.data, CANOPY_INPUT, len(own))
            canopy_input = given if given is not None else canopy_input
        values = {name: value.astype(numpy.float32).astype(float) for name, value in terrain.fields(own, numpy.clip(canopy_input, 0.0, 1.0), settings.seed).items()}
        result[obj.name] = values
        if len(obj.data.vertices) == len(own):
            write_fields(obj, values, own, terrain.lines)
            written.append(obj.name)
        else:
            skipped.append(obj.name)
    report = {
        "grid": {"rows": terrain.grid.rows, "columns": terrain.grid.columns, "cell": round(terrain.grid.cell, 4)},
        "sun": [round(float(value), 4) for value in terrain.sun],
        "paths": len(terrain.lines),
        "trodden_patches": terrain.patch_count,
        "path_length": round(sum(float(numpy.linalg.norm(numpy.diff(numpy.asarray(line)[:, :2], axis=0), axis=1).sum()) for line in terrain.lines), 3),
        "written": written,
    }
    if skipped:
        report["skipped"] = skipped
    for name in FIELDS:
        stacked = numpy.concatenate([values[name] for values in result.values()])
        report[name] = {"mean": round(float(stacked.mean()), 4), "min": round(float(stacked.min()), 4), "max": round(float(stacked.max()), 4)}
    return result, terrain.lines, report


def fields_for(obj, scene, depsgraph, settings):
    """The fields of one cover target: those already on it for its current geometry, or computed now."""
    points = liquid_world.vertex_points(obj, depsgraph)
    stored = stored_fields(obj, points)
    if stored is not None:
        values, lines = stored
        return values, lines, {"reused": True, "paths": len(lines)}
    result, lines, report = compute([obj], scene, depsgraph, settings)
    report["reused"] = False
    return result[obj.name], lines, report
