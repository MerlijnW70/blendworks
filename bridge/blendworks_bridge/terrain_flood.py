"""Python reference of Priority-Flood with epsilon (Barnes et al. 2014)."""

import heapq
import struct
from collections import deque

import numpy

from .terrain_flow import neighbours_of
from .terrain_grid import NODATA, OUTLET, flat_heights


def ordered_key(value):
    bits = struct.unpack("<Q", struct.pack("<d", value))[0]
    return bits ^ 0xFFFFFFFFFFFFFFFF if bits >> 63 else bits | (1 << 63)


def next_up(value):
    if value != value or value == float("inf"):
        return value
    if value == 0.0:
        return struct.unpack("<d", struct.pack("<Q", 1))[0]
    bits = struct.unpack("<Q", struct.pack("<d", value))[0]
    return struct.unpack("<d", struct.pack("<Q", bits + 1 if value > 0.0 else bits - 1))[0]


def priority_flood(grid, heights, epsilon):
    flat = flat_heights(heights)
    status = grid.status(flat).tolist()
    filled = flat.tolist()
    closed = [False] * grid.count
    open_cells = []
    for cell in range(grid.count):
        if status[cell] == OUTLET:
            closed[cell] = True
            open_cells.append((ordered_key(filled[cell]), cell))
    heapq.heapify(open_cells)
    pit = deque()
    raised = 0
    while pit or open_cells:
        cell = pit.popleft() if pit else heapq.heappop(open_cells)[1]
        level = next_up(filled[cell]) if epsilon else filled[cell]
        for other in neighbours_of(grid, cell):
            if closed[other] or status[other] == NODATA:
                continue
            closed[other] = True
            if filled[other] <= level:
                raised += filled[other] < level
                filled[other] = level
                pit.append(other)
            else:
                heapq.heappush(open_cells, (ordered_key(filled[other]), other))
    return numpy.array(filled).reshape(grid.shape), raised
