"""Python reference of threshold hillslopes: the eikonal surface of critical slopes by fast marching."""

import heapq
import math

import numpy

from .terrain_flood import ordered_key
from .terrain_grid import INTERIOR, NODATA, flat_heights


def upwind(a, b, s, dx, dy):
    """The upwind value from the lowest finished neighbours along x (a) and y (b), as the core computes it."""
    along_x = a + s * dx
    along_y = b + s * dy
    if not math.isfinite(a) or not math.isfinite(b):
        return along_x if along_x < along_y else along_y
    wx = 1.0 / (dx * dx)
    wy = 1.0 / (dy * dy)
    half = a * wx + b * wy
    total = wx + wy
    discriminant = half * half - total * (a * a * wx + b * b * wy - s * s)
    if discriminant >= 0.0:
        u = (half + math.sqrt(discriminant)) / total
        if u >= a and u >= b:
            return u
    return along_x if along_x < along_y else along_y


def threshold(grid, heights, tangent):
    """out = min(h, u) with |grad u| = tangent, solved by fast marching in (out, cell) order; outlets and no-data
    cells keep their heights. Returns the surface and the number of cells lowered."""
    flat = flat_heights(heights)
    status = grid.status(flat).tolist()
    tangent = numpy.asarray(tangent, dtype=numpy.float64).ravel().tolist()
    rows, columns = grid.shape
    valid = [status[cell] != NODATA for cell in range(grid.count)]
    if any(valid[cell] and not (math.isfinite(tangent[cell]) and tangent[cell] >= 0.0) for cell in range(grid.count)):
        raise ValueError("the critical tangent must be finite and at least 0 on every valid cell")
    out = flat.tolist()
    done = [False] * grid.count
    lowered = [False] * grid.count
    queue = [(ordered_key(out[cell]), cell) for cell in range(grid.count) if valid[cell]]
    heapq.heapify(queue)

    def lowest(first, second):
        found = math.inf
        for other in (first, second):
            if other is not None and done[other] and out[other] < found:
                found = out[other]
        return found

    while queue:
        key, cell = heapq.heappop(queue)
        if done[cell] or key != ordered_key(out[cell]):
            continue
        done[cell] = True
        row, column = divmod(cell, columns)
        around = (cell + 1 if column + 1 < columns else None, cell + columns if row + 1 < rows else None,
                  cell - 1 if column > 0 else None, cell - columns if row > 0 else None)
        for other in around:
            if other is None or done[other] or status[other] != INTERIOR:
                continue
            r, c = divmod(other, columns)
            a = lowest(other - 1 if c > 0 else None, other + 1 if c + 1 < columns else None)
            b = lowest(other - columns if r > 0 else None, other + columns if r + 1 < rows else None)
            reach = upwind(a, b, tangent[other], grid.spacing_x, grid.spacing_y)
            if reach < out[other]:
                out[other] = reach
                lowered[other] = True
                heapq.heappush(queue, (ordered_key(reach), other))
    return numpy.array(out).reshape(grid.shape), sum(lowered)
