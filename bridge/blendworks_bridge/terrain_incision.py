"""Python reference of implicit stream-power incision (Braun & Willett 2013), closed form for n = 1 and Newton for general n."""

import numpy

from .terrain_pow import pow as portable_pow

NEWTON_TOLERANCE = 1e-12
NEWTON_STEPS = 100


def check_law(area_exponent, slope_exponent, dt):
    if not (numpy.isfinite(area_exponent) and 0.0 <= area_exponent <= 10.0):
        raise ValueError(f"the area exponent m must be in [0, 10], got {area_exponent}")
    if not (numpy.isfinite(slope_exponent) and 0.0 < slope_exponent <= 10.0):
        raise ValueError(f"the slope exponent n must be in (0, 10], got {slope_exponent}")
    if not (numpy.isfinite(dt) and dt >= 0.0):
        raise ValueError(f"the time step must be finite and at least 0, got {dt}")


def solve(start, below, factor, exponent):
    found = start.copy()
    moving = (start > below) & (factor > 0.0)
    if exponent == 1.0:
        found[moving] = (start[moving] + factor[moving] * below[moving]) / (1.0 + factor[moving])
        return found
    low, high, height = below.copy(), start.copy(), start.copy()
    active = moving.copy()
    with numpy.errstate(all="ignore"):
        for _ in range(NEWTON_STEPS):
            if not active.any():
                break
            rise = height - below
            power = portable_pow(numpy.where(active, rise, 1.0), exponent)
            residual = height - start + factor * power
            high = numpy.where(active & (residual > 0.0), height, high)
            low = numpy.where(active & ~(residual > 0.0), height, low)
            slope = 1.0 + factor * exponent * power / rise
            candidate = numpy.where(rise > 0.0, height - residual / slope, numpy.nan)
            inside = (candidate >= low) & (candidate <= high)
            candidate = numpy.where(inside, candidate, 0.5 * (low + high))
            step = candidate - height
            height = numpy.where(active, candidate, height)
            active = active & ~(numpy.abs(step) <= NEWTON_TOLERANCE * (1.0 + numpy.abs(height)))
    found[moving] = height[moving]
    return found


def incise(grid, heights, receivers, ordering, area, erodibility, area_exponent, slope_exponent, dt):
    check_law(area_exponent, slope_exponent, dt)
    start = numpy.asarray(heights, dtype=numpy.float64).ravel()
    receivers = numpy.asarray(receivers, dtype=numpy.int64).ravel()
    area = numpy.asarray(area, dtype=numpy.float64).ravel()
    erodibility = numpy.asarray(erodibility, dtype=numpy.float64).ravel()
    moving = numpy.isfinite(start) & (receivers >= 0)
    if not (numpy.isfinite(erodibility[moving]) & (erodibility[moving] >= 0.0)).all():
        raise ValueError("erodibility must be finite and at least 0 on every cell with a receiver")
    if not (numpy.isfinite(area[moving]) & (area[moving] >= 0.0)).all():
        raise ValueError("area must be finite and at least 0 on every cell with a receiver")
    solved = start.copy()
    for index in range(ordering.levels):
        cells = ordering.level(index)
        cells = cells[moving[cells]]
        below = solved[receivers[cells]]
        cells, below = cells[numpy.isfinite(below)], below[numpy.isfinite(below)]
        if len(cells) == 0:
            continue
        distance = grid.distance(cells, receivers[cells])
        factor = erodibility[cells] * dt * portable_pow(area[cells], area_exponent) / portable_pow(distance, slope_exponent)
        solved[cells] = solve(start[cells], below, factor, slope_exponent)
    return solved
