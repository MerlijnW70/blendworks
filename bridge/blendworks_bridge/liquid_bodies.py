"""Liquid bodies: basins, fetch, levels and local bottoms."""

import math

import numpy

from . import liquid_grid, liquid_ripples, liquid_spectrum
from .errors import bad_args

LAKE_NODES = 400
PUDDLE_CELL = 0.01
PUDDLE_RADIUS = 2.0
OVERLAP_CELLS = 0.25
SPILL_MARGIN = 0.03


def default_cell(low, high, nodes):
    return max(max(high[0] - low[0], high[1] - low[1]) / nodes, 1e-4)


def fetch_along(mask, grid, direction):
    """Longest stretch of open water along the wind: the projected length of the wet nodes on the wind direction."""
    if not mask.any():
        return 0.0
    heading = math.radians(direction)
    x, y = grid.node_points()
    along = x[mask] * math.sin(heading) + y[mask] * math.cos(heading)
    return float(along.max() - along.min() + grid.cell)


class Basin:
    """Water standing in a hollow of the ground up to a level, from the grid sampled under it."""

    def __init__(self, grid, heights, level, wet, overlap):
        self.grid = grid
        self.heights = heights
        self.level = level
        self.wet = wet
        self.overlap = overlap

    @property
    def area(self):
        points, triangles = liquid_grid.level_sheet(self.grid, self.heights, numpy.full(self.heights.shape, self.level), self.wet, 0.0)
        return float(liquid_grid.triangle_areas(points, triangles).sum())

    @property
    def volume(self):
        return liquid_grid.held_volume(self.grid, self.heights, self.level, self.wet)

    @property
    def max_depth(self):
        return float(numpy.nanmax(numpy.where(self.wet, self.level - self.heights, 0.0)))

    def sheet(self):
        level = numpy.full(self.heights.shape, self.level)
        region = self.wet | dilate(self.wet)
        return liquid_grid.level_sheet(self.grid, self.heights, level, region, self.overlap)


def dilate(mask):
    grown = mask.copy()
    grown[1:, :] |= mask[:-1, :]
    grown[:-1, :] |= mask[1:, :]
    grown[:, 1:] |= mask[:, :-1]
    grown[:, :-1] |= mask[:, 1:]
    return grown


def resolve_level(heights, seed_node, args, kind):
    ground_there = heights[seed_node]
    if math.isnan(ground_there):
        raise bad_args("there is no ground under point")
    if "level" in args and "depth" in args:
        raise bad_args("give level or depth, not both")
    if "level" in args:
        return args["level"]
    if "depth" in args:
        bottom = local_bottom(heights, seed_node)
        return bottom + args["depth"]
    spill = liquid_grid.spill_level(heights, local_node(heights, seed_node))
    if not math.isfinite(spill):
        raise bad_args("the hollow never spills; give level or depth")
    return spill - SPILL_MARGIN * max(spill - local_bottom(heights, seed_node), 0.0)


def local_bottom(heights, node):
    """Lowest ground reached by walking downhill from node."""
    j, i = local_node(heights, node)
    return float(heights[j, i])


def local_node(heights, node):
    filled = numpy.where(numpy.isnan(heights), numpy.inf, heights)
    j, i = node
    rows, columns = heights.shape
    while True:
        best = (filled[j, i], j, i)
        for dj, di in liquid_grid.EIGHT:
            nj, ni = j + dj, i + di
            if 0 <= nj < rows and 0 <= ni < columns and filled[nj, ni] < best[0]:
                best = (filled[nj, ni], nj, ni)
        if best[1:] == (j, i):
            return j, i
        j, i = best[1], best[2]


def fill_basin(ground, args, kind):
    point = args.get("point")
    if point is None:
        raise bad_args(f"a {kind} needs point: a spot in the hollow to fill")
    if kind == "puddle":
        radius = args.get("radius", PUDDLE_RADIUS)
        low = (point[0] - radius, point[1] - radius)
        high = (point[0] + radius, point[1] + radius)
        cell = args.get("resolution", min(PUDDLE_CELL, radius / 50.0))
    else:
        low, high = ground.low[:2], ground.high[:2]
        cell = args.get("resolution", default_cell(low, high, LAKE_NODES))
    grid = liquid_grid.Grid.covering(low, high, cell)
    heights = grid.sample(ground)
    seed_node = grid.index_of(point[0], point[1])
    level = resolve_level(heights, seed_node, args, kind)
    wet = liquid_grid.flood(~numpy.isnan(heights) & (heights < level), [seed_node, local_node(heights, seed_node)])
    if not wet.any():
        raise bad_args(f"the ground at point lies above the level {round(level, 6)}: nothing to fill")
    if liquid_grid.touches_edge(wet):
        spill = liquid_grid.spill_level(heights, local_node(heights, seed_node))
        where = "radius" if kind == "puddle" else "ground"
        raise bad_args(f"the water reaches the edge of the {where} at level {round(level, 6)}: the hollow spills at {round(spill, 6)}; give a lower level" + (" or a larger radius" if kind == "puddle" else ""))
    overlap = args.get("overlap", OVERLAP_CELLS * cell)
    return Basin(grid, heights, level, wet, overlap)


def wave_displacement(points, tile, state, depth, choppiness):
    """Heights and horizontal shifts of the mesh-band waves, damped where the water is too shallow to carry them."""
    if tile is None or state["hs"] <= 0.0:
        return numpy.zeros(len(points)), numpy.zeros((len(points), 2)), numpy.ones(len(points))
    x, y = points[:, 0], points[:, 1]
    limit = liquid_spectrum.depth_limit(depth)
    factor = numpy.clip(limit / max(state["hs"], 1e-9), 0.0, 1.0)
    heights = tile.sample(tile.heights, x, y) * factor
    shifts = numpy.stack([tile.sample(tile.shift_x, x, y), tile.sample(tile.shift_y, x, y)], axis=1) * factor[:, None] * (choppiness > 0.0)
    jacobian = tile.sample(tile.jacobian, x, y)
    return heights, shifts, jacobian


def mesh_tile(state, direction, cell, seed, choppiness, size_hint):
    if state["hs"] <= 0.0:
        return None
    size = liquid_spectrum.tile_size(state, max(size_hint, 32.0 * cell))
    resolution = int(min(1024, max(64, 2 ** math.ceil(math.log2(size / cell)))))
    band = (0.0, liquid_ripples.mesh_cutoff(cell))
    tile = liquid_spectrum.synthesise(state, direction, resolution, size, seed, band=band, choppiness=choppiness)
    return tile if tile.variance > 0.0 else None


def foam_values(jacobian, fraction, depth, hs):
    threshold = liquid_spectrum.foam_threshold(jacobian, fraction) if numpy.isfinite(jacobian).all() else -math.inf
    crest = numpy.clip((threshold - jacobian) / 0.08 + 0.5, 0.0, 1.0) if math.isfinite(threshold) else numpy.zeros(len(jacobian))
    if hs <= 0.0:
        return crest
    breaking = hs / liquid_spectrum.BREAKER_INDEX
    surf = numpy.where(depth < breaking, numpy.clip(1.0 - depth / breaking, 0.0, 1.0) * numpy.clip(depth / (0.1 * breaking + 1e-6), 0.0, 1.0), 0.0)
    return numpy.maximum(crest, surf)
