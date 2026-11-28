"""Python reference of flow receivers: D8 and multiple flow with exponent p, flats resolved (Barnes 2014)."""

from collections import deque

import numpy

from .terrain_grid import INTERIOR, OUTLET, flat_heights
from .terrain_pow import pow as portable_pow

WIDTH_MFD = 8


def neighbour_heights(grid, flat):
    table = grid.neighbours()
    inside = table >= 0
    around = numpy.where(inside, flat[numpy.maximum(table, 0)], numpy.nan)
    return table, inside, around


def steepest(grid, flat, status):
    table, inside, around = neighbour_heights(grid, flat)
    distances = grid.distances()
    best = numpy.zeros(grid.count)
    found = numpy.full(grid.count, -1, dtype=numpy.int64)
    with numpy.errstate(invalid="ignore"):
        for slot in range(8):
            drop = (flat - around[slot]) / distances[slot]
            better = inside[slot] & numpy.isfinite(around[slot]) & (drop > best)
            best = numpy.where(better, drop, best)
            found = numpy.where(better, table[slot], found)
    found[status != INTERIOR] = -1
    return found


def neighbours_of(grid, cell):
    row, column = divmod(cell, grid.columns)
    for row_step, column_step in ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)):
        other_row, other_column = row + row_step, column + column_step
        if 0 <= other_row < grid.rows and 0 <= other_column < grid.columns:
            yield other_row * grid.columns + other_column


def flat_cells(grid, flat, status, receivers):
    table, inside, around = neighbour_heights(grid, flat)
    equal = (inside & (around == flat)).any(axis=0)
    return (status == INTERIOR) & (receivers < 0) & equal


def resolve_flats(grid, flat, status, receivers):
    flats = flat_cells(grid, flat, status, receivers)
    if not flats.any():
        return 0
    heights = flat.tolist()
    is_flat = flats.tolist()
    kinds = status.tolist()
    given = receivers.tolist()
    low_edges, high_edges = deque(), deque()
    for cell in range(grid.count):
        here = heights[cell]
        if here != here or abs(here) == float("inf"):
            continue
        if given[cell] >= 0 or kinds[cell] == OUTLET:
            if any(is_flat[other] and heights[other] == here for other in neighbours_of(grid, cell)):
                low_edges.append(cell)
        elif is_flat[cell]:
            if any(abs(heights[other]) != float("inf") and heights[other] > here for other in neighbours_of(grid, cell)):
                high_edges.append(cell)
    labels = [0] * grid.count
    next_label = 1
    for start in low_edges:
        if labels[start]:
            continue
        height = heights[start]
        labels[start] = next_label
        fill = deque([start])
        while fill:
            cell = fill.popleft()
            for other in neighbours_of(grid, cell):
                if labels[other] == 0 and heights[other] == height:
                    labels[other] = next_label
                    fill.append(other)
        next_label += 1
    high_edges = deque(cell for cell in high_edges if labels[cell])
    mask = [0] * grid.count
    flat_height = [0] * next_label
    passes(grid, labels, is_flat, high_edges, mask, flat_height, False)
    passes(grid, labels, is_flat, low_edges, mask, flat_height, True)
    resolved = 0
    for cell in range(grid.count):
        if not is_flat[cell] or not labels[cell]:
            continue
        best, chosen = mask[cell], -1
        for other in neighbours_of(grid, cell):
            if labels[other] == labels[cell] and mask[other] < best:
                best, chosen = mask[other], other
        if chosen >= 0:
            receivers[cell] = chosen
            resolved += 1
    return resolved


def passes(grid, labels, is_flat, starts, mask, flat_height, towards):
    if towards:
        for cell in range(grid.count):
            mask[cell] = -mask[cell]
    queue, loops = deque(starts), 1
    while queue:
        following = deque()
        while queue:
            cell = queue.popleft()
            if mask[cell] > 0:
                continue
            if not towards:
                mask[cell] = loops
                flat_height[labels[cell]] = loops
            elif mask[cell] < 0:
                mask[cell] = flat_height[labels[cell]] + mask[cell] + 2 * loops
            else:
                mask[cell] = 2 * loops
            following.extend(other for other in neighbours_of(grid, cell) if labels[other] == labels[cell] and is_flat[other])
        queue, loops = following, loops + 1


def d8(grid, heights):
    flat = flat_heights(heights)
    status = grid.status(flat)
    receivers = steepest(grid, flat, status)
    resolved = resolve_flats(grid, flat, status, receivers)
    return receivers.astype(numpy.int32), resolved


def mfd(grid, heights, exponent):
    if not (numpy.isfinite(exponent) and 0.0 < exponent <= 100.0):
        raise ValueError(f"the flow exponent p must be a finite number in (0, 100], got {exponent}")
    flat = flat_heights(heights)
    single, resolved = d8(grid, heights)
    table, inside, around = neighbour_heights(grid, flat)
    distances = grid.distances()
    count = grid.count
    receivers = numpy.full((count, WIDTH_MFD), -1, dtype=numpy.int32)
    shares = numpy.zeros((count, WIDTH_MFD))
    weights = numpy.zeros((count, WIDTH_MFD))
    used = numpy.zeros(count, dtype=numpy.int64)
    total = numpy.zeros(count)
    rows = numpy.arange(count)
    active = single >= 0
    with numpy.errstate(invalid="ignore"):
        for slot in range(8):
            drop = (flat - around[slot]) / distances[slot]
            down = active & inside[slot] & numpy.isfinite(around[slot]) & (drop > 0.0)
            weight = portable_pow(numpy.where(down, drop, 1.0), exponent)
            chosen = rows[down]
            weights[chosen, used[down]] = weight[down]
            receivers[chosen, used[down]] = table[slot][down]
            total = numpy.where(down, total + weight, total)
            used = used + down
    fallback = active & ((used == 0) | ~(total > 0.0))
    spread = active & ~fallback
    with numpy.errstate(invalid="ignore", divide="ignore"):
        shares[spread] = weights[spread] / total[spread, None]
    shares[~spread] = 0.0
    receivers[~active] = -1
    receivers[fallback] = -1
    receivers[fallback, 0] = single[fallback]
    shares[fallback, 0] = 1.0
    slots = numpy.arange(WIDTH_MFD)[None, :]
    receivers[spread] = numpy.where(slots < used[spread, None], receivers[spread], -1)
    return receivers.ravel(), shares.ravel(), resolved
