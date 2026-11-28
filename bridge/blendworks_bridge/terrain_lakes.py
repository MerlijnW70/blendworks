"""Python reference of lake routing by the basin graph and its minimum spanning tree (Cordonnier, Bovy & Braun 2019)."""

from collections import deque

import numpy

from .terrain_grid import INTERIOR, OUTLET, flat_heights

SEA = 0
NO_BASIN = -1
FORWARD = ((0, 1), (1, 1), (1, 0), (1, -1))
SIGN = numpy.uint64(1 << 63)


class Lakes:
    def __init__(self, receivers, basin, lake, water, spill, spill_to, basins, lakes):
        self.receivers = receivers
        self.basin = basin
        self.lake = lake
        self.water = water
        self.spill = spill
        self.spill_to = spill_to
        self.basins = int(basins)
        self.lakes = int(lakes)


def ordered_bits(values):
    bits = numpy.ascontiguousarray(values, dtype=numpy.float64).view(numpy.uint64)
    return numpy.where(bits >> numpy.uint64(63) == 1, ~bits, bits | SIGN)


def basin_labels(grid, receivers, status):
    """Every cell takes the label of the root its receivers lead to: the sea for an outlet, its
    number for a pit, none for no-data. The roots are found by pointer jumping, which reaches
    twice as far down the receivers every round."""
    count = grid.count
    pits = numpy.flatnonzero((status == INTERIOR) & (receivers < 0))
    label = numpy.full(count, NO_BASIN, dtype=numpy.int64)
    label[status == OUTLET] = SEA
    label[pits] = numpy.arange(1, len(pits) + 1)
    cells = numpy.arange(count)
    flows = (status == INTERIOR) & (receivers >= 0)
    root = numpy.where(flows, receivers, cells).astype(numpy.int64)
    for _ in range(max(count, 1).bit_length() + 1):
        further = root[root]
        if numpy.array_equal(further, root):
            break
        root = further
    stuck = flows[root]
    if stuck.any():
        raise RuntimeError(f"the flow graph has a cycle through cell {int(numpy.flatnonzero(stuck)[0])}")
    return label[root], pits


def basin_edges(grid, flat, basin):
    index = numpy.arange(grid.count).reshape(grid.shape)
    parts = []
    for row_step, column_step in FORWARD:
        low_column, high_column = max(0, -column_step), grid.columns - max(0, column_step)
        here = index[: grid.rows - row_step, low_column:high_column].ravel()
        there = index[row_step:, low_column + column_step : high_column + column_step].ravel()
        keep = (basin[here] != NO_BASIN) & (basin[there] != NO_BASIN) & (basin[here] != basin[there])
        parts.append(numpy.stack([here[keep], there[keep]], axis=1))
    pairs = numpy.concatenate(parts) if parts else numpy.zeros((0, 2), dtype=numpy.int64)
    cell, other = pairs[:, 0], pairs[:, 1]
    height = numpy.where(flat[cell] >= flat[other], flat[cell], flat[other])
    low = numpy.minimum(basin[cell], basin[other])
    high = numpy.maximum(basin[cell], basin[other])
    return height, low, high, cell, other


def boruvka(edges, nodes):
    height, low, high, cell, other = edges
    rank = numpy.empty(len(height), dtype=numpy.int64)
    rank[numpy.lexsort((other, cell, ordered_bits(height)))] = numpy.arange(len(height))
    by_rank = numpy.argsort(rank)
    none = len(height)
    component = numpy.arange(nodes)
    count = nodes
    alive = numpy.arange(len(height))
    chosen = []
    while len(alive):
        best = numpy.full(count, none, dtype=numpy.int64)
        numpy.minimum.at(best, component[low[alive]], rank[alive])
        numpy.minimum.at(best, component[high[alive]], rank[alive])
        index = numpy.flatnonzero(best < none)
        edge = by_rank[best[index]]
        here, there = component[low[edge]], component[high[edge]]
        partner = numpy.where(here == index, there, here)
        mutual = best[partner] == best[index]
        target = numpy.arange(count)
        target[index] = numpy.where(mutual & (index < partner), index, partner)
        taken = edge[~mutual | (index < partner)]
        if not len(taken):
            break
        chosen.extend(taken.tolist())
        while True:
            jumped = target[target]
            if numpy.array_equal(jumped, target):
                break
            target = jumped
        roots = target == numpy.arange(count)
        numbered = numpy.cumsum(roots) - 1
        component = numbered[target[component]]
        count = int(roots.sum())
        alive = alive[component[low[alive]] != component[high[alive]]]
    return sorted(chosen, key=lambda index: rank[index])


def spanning_tree(flat, basin, pits, edges):
    basins = len(pits)
    nodes = basins + 1
    chosen = boruvka(edges, nodes)
    height, low, high, cell, other = (part[chosen].tolist() for part in edges)
    adjacency = [[] for _ in range(nodes)]
    for index in range(len(height)):
        adjacency[low[index]].append((high[index], index))
        adjacency[high[index]].append((low[index], index))
    parent = [-1] * nodes
    passes = [(-1, -1)] * nodes
    level = [-numpy.inf] * nodes
    lake_of = list(range(nodes))
    visited = [False] * nodes
    pit_heights = [float(flat[pit]) for pit in pits]
    closed = sorted(range(1, nodes), key=lambda node: (ordered_bits(numpy.array([pit_heights[node - 1]]))[0], node))
    for start in [SEA] + closed:
        if visited[start]:
            continue
        visited[start] = True
        if start != SEA:
            level[start] = pit_heights[start - 1]
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for following, index in adjacency[node]:
                if visited[following]:
                    continue
                visited[following] = True
                inside, across = (cell[index], other[index]) if basin[cell[index]] == following else (other[index], cell[index])
                parent[following] = node
                passes[following] = (inside, across)
                above = level[node]
                own = height[index] >= above
                level[following] = height[index] if own else above
                lake_of[following] = following if own else lake_of[node]
                queue.append(following)
    return parent, passes, level, lake_of


def route(grid, heights, receivers, ordering, carve):
    """Lake routing. The basins come from the receivers alone; ordering is accepted so both
    engines share one signature."""
    flat = flat_heights(heights)
    status = grid.status(flat)
    receivers = numpy.asarray(receivers, dtype=numpy.int64).ravel()
    if ((status != INTERIOR) & (receivers >= 0)).any():
        raise ValueError("outlets and no-data cells must have no receiver")
    basin, pits = basin_labels(grid, receivers, status)
    basins = len(pits)
    parent, passes, level, lake_of = [-1] * (basins + 1), [(-1, -1)] * (basins + 1), [-numpy.inf] * (basins + 1), list(range(basins + 1))
    if basins:
        parent, passes, level, lake_of = spanning_tree(flat, basin, pits, basin_edges(grid, flat, basin))
    routed = receivers.copy()
    for child in range(1, basins + 1):
        if parent[child] < 0:
            continue
        inside, across = passes[child]
        bottom = int(pits[child - 1])
        if not carve:
            routed[bottom] = across
            continue
        previous, current = across, inside
        while True:
            following = int(receivers[current])
            routed[current] = previous
            if current == bottom or following < 0:
                break
            previous, current = current, following
    level_array = numpy.array(level, dtype=numpy.float64)
    lake_array = numpy.array(lake_of, dtype=numpy.int64)
    valid = basin != NO_BASIN
    cell_level = numpy.where(valid, level_array[numpy.maximum(basin, 0)], -numpy.inf)
    flooded = valid & (flat < cell_level)
    lake = numpy.where(flooded, lake_array[numpy.maximum(basin, 0)], 0)
    water = numpy.where(flooded, cell_level, flat)
    spill = numpy.full(grid.count + 1, -1, dtype=numpy.int64)
    spill_to = numpy.full(grid.count + 1, -1, dtype=numpy.int64)
    lakes = 0
    for child in range(1, basins + 1):
        if parent[child] >= 0:
            spill[child], spill_to[child] = passes[child]
            lakes += lake_of[child] == child
    return Lakes(routed.astype(numpy.int32), basin.astype(numpy.int32), lake.astype(numpy.int32), water.reshape(grid.shape), spill.astype(numpy.int32), spill_to.astype(numpy.int32), basins, lakes)
