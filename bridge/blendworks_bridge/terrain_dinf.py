"""Python reference of D-infinity flow directions (Tarboton 1997) and implicit incision over several receivers."""

import math

import numpy

from .terrain_grid import NODATA, OUTLET, flat_heights
from .terrain_pow import pow as portable_pow

FACETS = ((0, 1), (2, 1), (2, 3), (4, 3), (4, 5), (6, 5), (6, 7), (0, 7))
ATAN_TERMS = 24
QUARTER_PI = 0.7853981633974483
HALF_PI = 1.5707963267948966
TAN_EIGHTH_PI = 0.41421356237309503


def atan_series(u):
    square = u * u
    total = 0.0
    for term in range(ATAN_TERMS - 1, -1, -1):
        coefficient = (1.0 if term % 2 == 0 else -1.0) / float(2 * term + 1)
        total = coefficient + square * total
    return u * total


def atan_positive(t):
    """atan(t) for t >= 0 from additions, multiplications and divisions, as the core computes it."""
    if t > 1.0:
        return HALF_PI - atan_positive(1.0 / t)
    if t > TAN_EIGHTH_PI:
        return QUARTER_PI + atan_series((t - 1.0) / (t + 1.0))
    return atan_series(t)


def facet_flow(here, around, distances):
    best = None
    for side, diagonal in FACETS:
        e1, e2 = around[side], around[diagonal]
        if e1 != e1 or e2 != e2:
            continue
        d1 = distances[side]
        diagonal_distance = distances[diagonal]
        d2 = math.sqrt(diagonal_distance * diagonal_distance - d1 * d1)
        widest = atan_positive(d2 / d1)
        s1 = (here - e1) / d1
        s2 = (e1 - e2) / d2
        if s1 > 0.0 and s2 > 0.0:
            angle = atan_positive(s2 / s1)
            angle, slope = (widest, (here - e2) / diagonal_distance) if angle > widest else (angle, math.sqrt(s1 * s1 + s2 * s2))
        elif s1 > 0.0:
            angle, slope = 0.0, s1
        else:
            angle, slope = widest, (here - e2) / diagonal_distance
        if slope > 0.0 and (best is None or slope > best[0]):
            best = (slope, side, diagonal, angle, widest)
    if best is None:
        return None
    _, side, diagonal, angle, widest = best
    share = angle / widest
    return (side, 1.0 - share), (diagonal, share)


def dinf(grid, heights):
    """Receiver table and shares, eight slots per cell in neighbour order."""
    flat = flat_heights(heights)
    status = grid.status(flat)
    table = grid.neighbours()
    distances = grid.distances()
    receivers = numpy.full(grid.count * 8, -1, dtype=numpy.int32)
    shares = numpy.zeros(grid.count * 8)
    for cell in range(grid.count):
        if status[cell] in (NODATA, OUTLET):
            continue
        around = [math.nan] * 8
        for slot in range(8):
            other = int(table[slot][cell])
            if other >= 0 and status[other] != NODATA:
                around[slot] = float(flat[other])
        found = facet_flow(float(flat[cell]), around, distances)
        if found is None:
            continue
        for slot, share in found:
            if share > 0.0:
                receivers[cell * 8 + slot] = int(table[slot][cell])
                shares[cell * 8 + slot] = share
    return receivers, shares


def incise_many(grid, heights, table, shares, width, ordering, area, erodibility, area_exponent, dt):
    """Implicit incision for n = 1 over several receivers, cells in queue order, as the core solves it."""
    flat = flat_heights(heights)
    solved = flat.copy()
    table = numpy.asarray(table).ravel()
    shares = numpy.asarray(shares, dtype=numpy.float64).ravel()
    area = numpy.asarray(area, dtype=numpy.float64).ravel()
    erodibility = numpy.asarray(erodibility, dtype=numpy.float64).ravel()
    bases = erodibility * dt * portable_pow(area, area_exponent)
    columns = grid.columns
    for cell in ordering.order.tolist():
        start = float(flat[cell])
        if not math.isfinite(start):
            continue
        base = float(bases[cell])
        weight = 0.0
        pulled = 0.0
        for slot in range(width):
            receiver = int(table[cell * width + slot])
            if receiver < 0:
                continue
            below = float(solved[receiver])
            if math.isfinite(below) and below < start:
                rows, cols = divmod(receiver, columns)
                row, col = divmod(cell, columns)
                distance = math.sqrt(((rows - row) * grid.spacing_y) ** 2 + ((cols - col) * grid.spacing_x) ** 2)
                factor = base * shares[cell * width + slot] / distance
                weight += factor
                pulled += factor * below
        if weight > 0.0:
            solved[cell] = (start + pulled) / (1.0 + weight)
    return solved.reshape(grid.shape)
