"""Python reference of the breadth-first receiver queue with levels (Barnes 2019) and accumulation along it."""

import numpy

from .terrain_grid import NEIGHBOURS


class Ordering:
    def __init__(self, order, level_start, donor_start, donors, width):
        self.order = numpy.ascontiguousarray(order, dtype=numpy.int32)
        self.level_start = numpy.ascontiguousarray(level_start, dtype=numpy.int32)
        self.donor_start = numpy.ascontiguousarray(donor_start, dtype=numpy.int32)
        self.donors = numpy.ascontiguousarray(donors, dtype=numpy.int32)
        self.width = int(width)

    @property
    def levels(self):
        return len(self.level_start) - 1

    def level(self, index):
        return self.order[self.level_start[index] : self.level_start[index + 1]].astype(numpy.int64)

    def padded_level_start(self):
        cached = getattr(self, "padded", None)
        if cached is None or not numpy.array_equal(cached[: len(self.level_start)], self.level_start):
            cached = numpy.full(len(self.order) + 1, -1, dtype=numpy.int32)
            cached[: len(self.level_start)] = self.level_start
            self.padded = cached
        return cached


def check_table(grid, receivers, width):
    table = numpy.asarray(receivers)
    if not 1 <= width <= 8:
        raise ValueError(f"a receiver table has 1 to 8 slots per cell, got {width}")
    if table.size != grid.count * width:
        raise ValueError(f"receivers hold {table.size} values, the grid needs {grid.count * width}")
    table = table.astype(numpy.int64).reshape(grid.count, width)
    if ((table < -1) | (table >= grid.count)).any():
        raise ValueError("a receiver is outside the grid and not -1")
    if (table == numpy.arange(grid.count)[:, None]).any():
        raise ValueError("a cell is its own receiver")
    ordered = numpy.sort(table, axis=1)
    if ((ordered[:, 1:] == ordered[:, :-1]) & (ordered[:, 1:] >= 0)).any():
        raise ValueError("a cell names the same receiver twice")
    return table


def donor_lists(grid, table):
    count, width = table.shape
    index = numpy.arange(count, dtype=numpy.int64)
    rows, columns = numpy.divmod(index, grid.columns)
    receiving, keys, edges = [], [], []
    near = numpy.zeros(table.shape, dtype=bool)
    for slot, (row_step, column_step) in enumerate(NEIGHBOURS):
        other_rows, other_columns = rows + row_step, columns + column_step
        inside = (other_rows >= 0) & (other_rows < grid.rows) & (other_columns >= 0) & (other_columns < grid.columns)
        other = numpy.where(inside, other_rows * grid.columns + other_columns, 0)
        for k in range(width):
            pointing = inside & (table[other, k] == index)
            receiving.append(index[pointing])
            keys.append(numpy.full(int(pointing.sum()), slot * width + k, dtype=numpy.int64))
            edges.append(other[pointing] * width + k)
            near[other[pointing], k] = True
    far_cells, far_slots = numpy.nonzero((table >= 0) & ~near)
    far_edges = far_cells * width + far_slots
    receiving.append(table[far_cells, far_slots])
    keys.append(8 * width + far_edges)
    edges.append(far_edges)
    receiving, keys, edges = numpy.concatenate(receiving), numpy.concatenate(keys), numpy.concatenate(edges)
    by = numpy.lexsort((keys, receiving))
    donors = edges[by]
    start = numpy.zeros(count + 1, dtype=numpy.int64)
    start[1:] = numpy.cumsum(numpy.bincount(receiving, minlength=count))
    return start, donors


def order(grid, receivers, width):
    table = check_table(grid, receivers, width)
    count = grid.count
    start, donors = donor_lists(grid, table)
    remaining = (table >= 0).sum(axis=1)
    position = numpy.full(count, -1, dtype=numpy.int64)
    current = numpy.flatnonzero(remaining == 0)
    placed, level_start, levels = [], [0], []
    total = 0
    while len(current):
        position[current] = numpy.arange(total, total + len(current))
        levels.append(current)
        total += len(current)
        level_start.append(total)
        counts = start[current + 1] - start[current]
        offsets = numpy.arange(int(counts.sum())) - numpy.repeat(numpy.cumsum(counts) - counts, counts)
        edge = donors[numpy.repeat(start[current], counts) + offsets]
        receiver = numpy.repeat(current, counts)
        donor = edge // width
        if width > 1:
            numpy.subtract.at(remaining, donor, 1)
            last = numpy.where(table[donor] >= 0, position[numpy.maximum(table[donor], 0)], -1).max(axis=1)
            keep = (remaining[donor] == 0) & (last == position[receiver])
            donor = donor[keep]
        current = donor
    if total != count:
        raise RuntimeError(f"the flow graph has a cycle: {count - total} of {count} cells cannot be ordered")
    placed = numpy.concatenate(levels) if levels else numpy.zeros(0, dtype=numpy.int64)
    return Ordering(placed, numpy.array(level_start), start, donors, width)


def accumulate(ordering, weights, shares=None):
    width = ordering.width
    total = numpy.array(weights, dtype=numpy.float64).ravel().copy()
    start = ordering.donor_start.astype(numpy.int64)
    donors = ordering.donors.astype(numpy.int64)
    share = None if width == 1 else numpy.asarray(shares, dtype=numpy.float64).ravel()
    for index in reversed(range(ordering.levels)):
        cells = ordering.level(index)
        counts = start[cells + 1] - start[cells]
        sums = total[cells].copy()
        for j in range(int(counts.max()) if len(cells) else 0):
            having = counts > j
            edge = donors[start[cells[having]] + j]
            if width == 1:
                sums[having] = sums[having] + total[edge]
            else:
                sums[having] = sums[having] + share[edge] * total[edge // width]
        total[cells] = sums
    return total
