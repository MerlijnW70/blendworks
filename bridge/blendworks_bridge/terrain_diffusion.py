"""Python reference of hillslope diffusion: linear by ADI and non-linear critical-slope diffusion (Roering et al. 1999)."""

import numpy

from .terrain_grid import INTERIOR


def check_settings(heights, diffusivity, dt, critical):
    valid = numpy.isfinite(heights)
    if not (numpy.isfinite(dt) and dt >= 0.0):
        raise ValueError(f"the time step must be finite and at least 0, got {dt}")
    if not (numpy.isfinite(diffusivity[valid]) & (diffusivity[valid] >= 0.0)).all():
        raise ValueError("diffusivity must be finite and at least 0 on every valid cell")
    if critical is not None:
        slope, max_ratio, iterations = critical
        if not (numpy.isfinite(slope) and slope > 0.0):
            raise ValueError(f"the critical slope must be finite and above 0, got {slope}")
        if not 0.0 < max_ratio < 1.0:
            raise ValueError(f"the slope ratio cap must be in (0, 1), got {max_ratio}")
        if not 1 <= iterations <= 100:
            raise ValueError(f"the Picard iterations must be 1 to 100, got {iterations}")


def cross_gradient(heights, spacing, axis):
    valid = numpy.isfinite(heights)
    moved = numpy.moveaxis(heights, axis, 0)
    valid_moved = numpy.moveaxis(valid, axis, 0)
    before = numpy.full(moved.shape, numpy.nan)
    after = numpy.full(moved.shape, numpy.nan)
    before[1:] = moved[:-1]
    after[:-1] = moved[1:]
    has_before = numpy.zeros(moved.shape, dtype=bool)
    has_after = numpy.zeros(moved.shape, dtype=bool)
    has_before[1:] = valid_moved[:-1]
    has_after[:-1] = valid_moved[1:]
    with numpy.errstate(invalid="ignore"):
        found = numpy.where(has_before & has_after, (after - before) / (2.0 * spacing), 0.0)
        found = numpy.where(~has_before & has_after, (after - moved) / spacing, found)
        found = numpy.where(has_before & ~has_after, (moved - before) / spacing, found)
    return numpy.moveaxis(found, 0, axis)


def roering(gradient_squared, slope, max_ratio):
    ratio = numpy.sqrt(gradient_squared) / slope
    ratio = numpy.where(ratio > max_ratio, max_ratio, ratio)
    return 1.0 / (1.0 - ratio * ratio)


def faces(grid, current, diffusivity, dt, critical):
    valid = numpy.isfinite(current)
    east = numpy.zeros(grid.shape)
    south = numpy.zeros(grid.shape)
    scale_x = dt / (grid.spacing_x * grid.spacing_x)
    scale_y = dt / (grid.spacing_y * grid.spacing_y)
    with numpy.errstate(invalid="ignore"):
        pair = valid[:, :-1] & valid[:, 1:]
        factor = numpy.ones(pair.shape)
        if critical is not None:
            across_rows = cross_gradient(current, grid.spacing_y, 0)
            along = (current[:, 1:] - current[:, :-1]) / grid.spacing_x
            across = 0.5 * (across_rows[:, :-1] + across_rows[:, 1:])
            factor = roering(along * along + across * across, critical[0], critical[1])
        east[:, :-1] = numpy.where(pair, scale_x * (0.5 * (diffusivity[:, :-1] + diffusivity[:, 1:])) * factor, 0.0)
        pair = valid[:-1, :] & valid[1:, :]
        factor = numpy.ones(pair.shape)
        if critical is not None:
            across_columns = cross_gradient(current, grid.spacing_x, 1)
            along = (current[1:, :] - current[:-1, :]) / grid.spacing_y
            across = 0.5 * (across_columns[:-1, :] + across_columns[1:, :])
            factor = roering(along * along + across * across, critical[0], critical[1])
        south[:-1, :] = numpy.where(pair, scale_y * (0.5 * (diffusivity[:-1, :] + diffusivity[1:, :])) * factor, 0.0)
    return east, south


def thomas(free, couplings, source):
    lines, length = source.shape
    out = numpy.zeros(source.shape)
    upper = numpy.zeros(source.shape)
    previous_upper = numpy.zeros(lines)
    previous_value = numpy.zeros(lines)
    with numpy.errstate(invalid="ignore"):
        for position in range(length):
            before = couplings[:, position - 1] if position > 0 else numpy.zeros(lines)
            after = couplings[:, position]
            a = numpy.where(free[:, position], -before, 0.0)
            b = numpy.where(free[:, position], 1.0 + before + after, 1.0)
            c = numpy.where(free[:, position], -after, 0.0)
            denominator = b - a * previous_upper
            upper[:, position] = c / denominator
            right = numpy.where(a != 0.0, source[:, position] - a * previous_value, source[:, position])
            out[:, position] = right / denominator
            previous_upper = upper[:, position]
            previous_value = out[:, position]
        for position in range(length - 2, -1, -1):
            factor = upper[:, position]
            out[:, position] = numpy.where(factor != 0.0, out[:, position] - factor * out[:, position + 1], out[:, position])
    return out


def diffuse(grid, heights, diffusivity, dt, critical=None):
    start = numpy.asarray(heights, dtype=numpy.float64).reshape(grid.shape)
    diffusivity = numpy.asarray(diffusivity, dtype=numpy.float64).reshape(grid.shape)
    check_settings(start, diffusivity, dt, critical)
    free = (grid.status(start) == INTERIOR).reshape(grid.shape)
    iterations = 1 if critical is None else critical[2]
    current = start.copy()
    for _ in range(iterations):
        east, south = faces(grid, current, diffusivity, dt, critical)
        half = thomas(free, east, start)
        current = thomas(free.T, south.T, half.T).T.copy()
    return current
