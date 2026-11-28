"""Dispatch of the terrain kernels to the native core or the Python references."""

import os

import numpy

from . import terrain_core, terrain_diffusion, terrain_flood, terrain_flow, terrain_incision, terrain_lakes, terrain_order, terrain_thermal
from .terrain_grid import EDGE_ALL, TerrainGrid
from .terrain_lakes import Lakes
from .terrain_order import Ordering

ENGINES = ("auto", "core", "python")
WIDTH_MFD = 8
DEFAULT_MAX_RATIO = 0.99
DEFAULT_PICARD = 3


def default_threads():
    return max(1, min(4, os.cpu_count() or 1))


def chosen_core(engine):
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {', '.join(ENGINES)}, got {engine!r}")
    if engine == "python":
        return None
    found = terrain_core.core()
    if found is None and (engine == "core" or terrain_core.required()):
        return terrain_core.require()
    return found


def threads_of(threads):
    return default_threads() if threads is None else int(threads)


def field(value, grid):
    value = numpy.asarray(value, dtype=numpy.float64)
    if value.ndim == 1 and value.size == grid.count:
        value = value.reshape(grid.shape)
    return numpy.ascontiguousarray(numpy.broadcast_to(value, grid.shape)).ravel()


def heights_of(heights):
    return numpy.ascontiguousarray(heights, dtype=numpy.float64)


def index_buffer(values, size):
    found = numpy.ascontiguousarray(values, dtype=numpy.int32).ravel()
    if found.size != size:
        raise ValueError(f"expected {size} values, got {found.size}")
    return found


def d8(heights, spacing=(1.0, 1.0), edges=EDGE_ALL, threads=None, engine="auto"):
    heights = heights_of(heights)
    grid = TerrainGrid.of(heights, spacing, edges)
    found = chosen_core(engine)
    if found is None:
        return terrain_flow.d8(grid, heights)
    receivers = numpy.empty(grid.count, dtype=numpy.int32)
    resolved = terrain_core.I64(0)
    found.call("bw_d8", terrain_core.grid_spec(grid), threads_of(threads), terrain_core.describe(heights), terrain_core.describe(receivers), resolved)
    return receivers, resolved.value


def mfd(heights, exponent, spacing=(1.0, 1.0), edges=EDGE_ALL, threads=None, engine="auto"):
    heights = heights_of(heights)
    grid = TerrainGrid.of(heights, spacing, edges)
    found = chosen_core(engine)
    if found is None:
        return terrain_flow.mfd(grid, heights, exponent)
    receivers = numpy.empty(grid.count * WIDTH_MFD, dtype=numpy.int32)
    shares = numpy.empty(grid.count * WIDTH_MFD)
    resolved = terrain_core.I64(0)
    found.call("bw_mfd", terrain_core.grid_spec(grid), threads_of(threads), terrain_core.describe(heights), float(exponent), terrain_core.describe(receivers), terrain_core.describe(shares), resolved)
    return receivers, shares, resolved.value


def order(receivers, shape, width=1, threads=None, engine="auto"):
    grid = TerrainGrid(shape[0], shape[1])
    found = chosen_core(engine)
    if found is None:
        return terrain_order.order(grid, receivers, width)
    table = index_buffer(receivers, grid.count * int(width))
    placed = numpy.empty(grid.count, dtype=numpy.int32)
    level_start = numpy.empty(grid.count + 1, dtype=numpy.int32)
    donor_start = numpy.empty(grid.count + 1, dtype=numpy.int32)
    donors = numpy.empty(grid.count * int(width), dtype=numpy.int32)
    levels = terrain_core.I64(0)
    found.call("bw_order", terrain_core.grid_spec(grid), threads_of(threads), terrain_core.describe(table), int(width), terrain_core.describe(placed), terrain_core.describe(level_start), terrain_core.describe(donor_start), terrain_core.describe(donors), levels)
    return Ordering(placed, level_start[: levels.value + 1], donor_start, donors[: donor_start[-1]], width)


def accumulate(ordering, weights, shares=None, threads=None, engine="auto"):
    count = len(ordering.order)
    weights = numpy.ascontiguousarray(weights, dtype=numpy.float64).ravel()
    found = chosen_core(engine)
    if found is None:
        return terrain_order.accumulate(ordering, weights, shares)
    shares = numpy.zeros(0) if shares is None else numpy.ascontiguousarray(shares, dtype=numpy.float64).ravel()
    total = numpy.empty(count)
    grid = TerrainGrid(1, count)
    found.call("bw_accumulate", terrain_core.grid_spec(grid), threads_of(threads), ordering.width, terrain_core.describe(shares), terrain_core.describe(ordering.order), terrain_core.describe(ordering.padded_level_start()), terrain_core.describe(ordering.donor_start), terrain_core.describe(ordering.donors), terrain_core.describe(weights), terrain_core.describe(total))
    return total


def incise(heights, receivers, ordering, area, erodibility, area_exponent, slope_exponent, dt, spacing=(1.0, 1.0), threads=None, engine="auto"):
    heights = heights_of(heights)
    grid = TerrainGrid.of(heights, spacing)
    area = field(area, grid)
    erodibility = field(erodibility, grid)
    found = chosen_core(engine)
    if found is None:
        return terrain_incision.incise(grid, heights, receivers, ordering, area, erodibility, area_exponent, slope_exponent, dt).reshape(grid.shape)
    receivers = index_buffer(receivers, grid.count)
    solved = numpy.empty(grid.shape)
    found.call("bw_incise", terrain_core.grid_spec(grid), threads_of(threads), terrain_core.describe(heights), terrain_core.describe(receivers), terrain_core.describe(ordering.order), terrain_core.describe(ordering.padded_level_start()), terrain_core.describe(area), terrain_core.describe(erodibility), float(area_exponent), float(slope_exponent), float(dt), terrain_core.describe(solved))
    return solved


def route_lakes(heights, receivers, ordering, carve=True, spacing=(1.0, 1.0), edges=EDGE_ALL, threads=None, engine="auto"):
    heights = heights_of(heights)
    grid = TerrainGrid.of(heights, spacing, edges)
    found = chosen_core(engine)
    if found is None:
        return terrain_lakes.route(grid, heights, receivers, ordering, carve)
    receivers = index_buffer(receivers, grid.count)
    routed, basin, lake = (numpy.empty(grid.count, dtype=numpy.int32) for _ in range(3))
    water = numpy.empty(grid.shape)
    spill, spill_to = (numpy.empty(grid.count + 1, dtype=numpy.int32) for _ in range(2))
    basins, lakes = terrain_core.I64(0), terrain_core.I64(0)
    describe = terrain_core.describe
    found.call("bw_route_lakes", terrain_core.grid_spec(grid), threads_of(threads), describe(heights), describe(receivers), describe(ordering.order), describe(ordering.padded_level_start()), int(bool(carve)), describe(routed), describe(basin), describe(lake), describe(water), describe(spill), describe(spill_to), basins, lakes)
    return Lakes(routed, basin, lake, water, spill, spill_to, basins.value, lakes.value)


def priority_flood(heights, epsilon=True, edges=EDGE_ALL, engine="auto"):
    heights = heights_of(heights)
    grid = TerrainGrid.of(heights, (1.0, 1.0), edges)
    found = chosen_core(engine)
    if found is None:
        return terrain_flood.priority_flood(grid, heights, epsilon)
    filled = numpy.empty(grid.shape)
    raised = terrain_core.I64(0)
    found.call("bw_priority_flood", terrain_core.grid_spec(grid), terrain_core.describe(heights), int(bool(epsilon)), terrain_core.describe(filled), raised)
    return filled, raised.value


def diffuse(heights, diffusivity, dt, spacing=(1.0, 1.0), edges=EDGE_ALL, critical_slope=None, max_ratio=DEFAULT_MAX_RATIO, iterations=DEFAULT_PICARD, threads=None, engine="auto"):
    heights = heights_of(heights)
    grid = TerrainGrid.of(heights, spacing, edges)
    diffusivity = field(diffusivity, grid)
    critical = None if critical_slope is None else (float(critical_slope), float(max_ratio), int(iterations))
    if critical is not None and not (numpy.isfinite(critical[0]) and critical[0] > 0.0):
        raise ValueError(f"the critical slope must be finite and above 0, got {critical_slope}")
    found = chosen_core(engine)
    if found is None:
        return terrain_diffusion.diffuse(grid, heights, diffusivity, float(dt), critical)
    out = numpy.empty(grid.shape)
    slope, ratio, picard = critical if critical is not None else (0.0, 0.0, 0)
    found.call("bw_diffuse", terrain_core.grid_spec(grid), threads_of(threads), terrain_core.describe(heights), terrain_core.describe(diffusivity), float(dt), slope, ratio, picard, terrain_core.describe(out))
    return out


def slide(heights, tangent, rate=0.5, iterations=1, spacing=(1.0, 1.0), edges=EDGE_ALL, threads=None, engine="auto"):
    heights = heights_of(heights)
    grid = TerrainGrid.of(heights, spacing, edges)
    tangent = field(tangent, grid)
    found = chosen_core(engine)
    if found is None:
        return terrain_thermal.slide(grid, heights, tangent, float(rate), int(iterations))
    out = numpy.empty(grid.shape)
    found.call("bw_slide", terrain_core.grid_spec(grid), threads_of(threads), terrain_core.describe(heights), terrain_core.describe(tangent), float(rate), int(iterations), terrain_core.describe(out))
    return out
