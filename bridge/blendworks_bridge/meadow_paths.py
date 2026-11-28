"""Worn paths as least-time routes.

Worn paths: least-time routes between the meadow's gates and its water, by Tobler's hiking function, joined as a
minimum spanning tree and routed one after the other so later paths follow the trodden ones (Helbing's active walkers)."""
import heapq
import math

import numpy

from .meadow_grid import NEIGHBOURS

PATH_CELLS = 160
GATE_SPACING = 400.0
FEWEST_GATES = 2
MOST_GATES = 6
GATE_SEARCH = 0.15
TOBLER_SPEED = 6.0
TOBLER_RATE = 3.5
TOBLER_OFFSET = 0.05
TRAIL_DISCOUNT = 0.5
STEEPEST = 1.0
SMOOTHING_PASSES = 3


def walking_time(rise, run):
    """Hours to walk run metres while rising rise metres (Tobler 1993: 6 exp(-3.5 |s + 0.05|) km/h)."""
    speed = TOBLER_SPEED * math.exp(-TOBLER_RATE * abs(rise / run + TOBLER_OFFSET))
    return run / 1000.0 / speed


class PathGrid:
    """The field grid thinned to at most PATH_CELLS cells a side, with water cells closed."""

    def __init__(self, grid, water):
        self.stride = max(1, int(math.ceil(max(grid.shape) / PATH_CELLS)))
        self.heights = grid.heights[::self.stride, ::self.stride]
        self.water = water[::self.stride, ::self.stride]
        self.cell = grid.cell * self.stride
        self.low = grid.low
        self.rows, self.columns = self.heights.shape

    def point(self, row, column):
        base = self.cell / self.stride
        return [float(self.low[0] + (column * self.stride + 0.5) * base), float(self.low[1] + (row * self.stride + 0.5) * base), float(self.heights[row, column])]

    def cell_of(self, xy):
        base = self.cell / self.stride
        column = int(numpy.clip(round(((xy[0] - self.low[0]) / base - 0.5) / self.stride), 0, self.columns - 1))
        row = int(numpy.clip(round(((xy[1] - self.low[1]) / base - 0.5) / self.stride), 0, self.rows - 1))
        return row, column

    def step_time(self, row, column, other_row, other_column):
        run = self.cell * math.hypot(other_row - row, other_column - column)
        rise = float(self.heights[other_row, other_column] - self.heights[row, column])
        if abs(rise) / run > STEEPEST:
            return math.inf
        return walking_time(rise, run)

    def slope(self, row, column):
        window = self.heights[max(0, row - 1):row + 2, max(0, column - 1):column + 2]
        return float(window.max() - window.min()) / (2.0 * self.cell)


def dijkstra(grid, start, trodden):
    """Least walking time from start to every cell, and each cell's predecessor."""
    times = numpy.full((grid.rows, grid.columns), math.inf)
    previous = numpy.full((grid.rows, grid.columns, 2), -1, dtype=numpy.int64)
    times[start] = 0.0
    queue = [(0.0, start[0], start[1])]
    water = grid.water
    while queue:
        time, row, column = heapq.heappop(queue)
        if time > times[row, column]:
            continue
        for dr, dc in NEIGHBOURS:
            r, c = row + dr, column + dc
            if r < 0 or c < 0 or r >= grid.rows or c >= grid.columns or water[r, c]:
                continue
            step = grid.step_time(row, column, r, c)
            if trodden is not None and trodden[r, c]:
                step *= TRAIL_DISCOUNT
            total = time + step
            if total < times[r, c]:
                times[r, c] = total
                previous[r, c] = (row, column)
                heapq.heappush(queue, (total, r, c))
    return times, previous


def traced(previous, start, end):
    cells = [end]
    while cells[-1] != start:
        row, column = previous[cells[-1]]
        if row < 0:
            return None
        cells.append((int(row), int(column)))
    return cells[::-1]


def border_cells(grid):
    rows, columns = grid.rows, grid.columns
    ring = [(0, c) for c in range(columns)] + [(r, columns - 1) for r in range(1, rows)]
    ring += [(rows - 1, c) for c in range(columns - 2, -1, -1)] + [(r, 0) for r in range(rows - 2, 0, -1)]
    return ring


def gates(grid, rng):
    """Where paths enter the meadow: evenly round its border (one per GATE_SPACING metres, 2 to 6), each moved to the
    gentlest dry border cell within GATE_SEARCH of the border length."""
    ring = border_cells(grid)
    perimeter = len(ring) * grid.cell
    count = int(numpy.clip(round(perimeter / GATE_SPACING), FEWEST_GATES, MOST_GATES))
    start = rng.uniform(0.0, 1.0)
    reach = max(1, int(GATE_SEARCH * len(ring)))
    found = []
    for index in range(count):
        middle = int(((start + index) / count) * len(ring)) % len(ring)
        best = None
        for offset in range(-reach // 2, reach // 2 + 1):
            row, column = ring[(middle + offset) % len(ring)]
            if grid.water[row, column]:
                continue
            score = grid.slope(row, column) + 0.02 * abs(offset) / max(reach, 1)
            if best is None or score < best[0]:
                best = (score, (row, column))
        if best is not None and best[1] not in found:
            found.append(best[1])
    return found


def water_access(grid, ends):
    """Where paths reach the water: the dry cell beside the water that is quickest to walk to from the gates."""
    if not grid.water.any() or not ends:
        return []
    padded = numpy.pad(grid.water, 1)
    near = numpy.zeros_like(grid.water)
    for dr, dc in NEIGHBOURS:
        near |= padded[1 + dr:1 + dr + grid.rows, 1 + dc:1 + dc + grid.columns]
    shore = numpy.argwhere(near & ~grid.water)
    if not len(shore):
        return []
    times, _ = dijkstra(grid, ends[0], None)
    reachable = [tuple(cell) for cell in shore.tolist() if math.isfinite(times[cell[0], cell[1]])]
    if not reachable:
        return []
    return [min(reachable, key=lambda cell: times[cell] + grid.slope(*cell) * 0.01)]


def spanning_pairs(ends, times):
    """Prim's minimum spanning tree over the walking times between the ends."""
    joined = [0]
    pairs = []
    while len(joined) < len(ends):
        best = None
        for first in joined:
            for second in range(len(ends)):
                if second in joined:
                    continue
                cost = times[first][ends[second]]
                if math.isfinite(cost) and (best is None or cost < best[0]):
                    best = (cost, first, second)
        if best is None:
            break
        joined.append(best[2])
        pairs.append((best[1], best[2]))
    return pairs


def chaikin(points, passes=SMOOTHING_PASSES):
    points = numpy.asarray(points, dtype=float)
    for _ in range(passes):
        if len(points) < 3:
            break
        first = 0.75 * points[:-1] + 0.25 * points[1:]
        second = 0.25 * points[:-1] + 0.75 * points[1:]
        middle = numpy.empty((2 * len(first), points.shape[1]))
        middle[0::2], middle[1::2] = first, second
        points = numpy.concatenate([points[:1], middle, points[-1:]])
    return points


def path_network(grid, water, seed, given=None):
    """Polylines [[x, y, z], ...] of the worn paths over the grid: between the given points, or else between the gates and
    the water access."""
    paths = PathGrid(grid, water)
    rng = numpy.random.default_rng([seed, 0x9A7])
    if given:
        ends = []
        for point in given:
            cell = paths.cell_of(point)
            if not paths.water[cell] and cell not in ends:
                ends.append(cell)
    else:
        ends = gates(paths, rng)
        ends += [cell for cell in water_access(paths, ends) if cell not in ends]
    if len(ends) < 2:
        return []
    times = [dijkstra(paths, end, None)[0] for end in ends]
    trodden = numpy.zeros((paths.rows, paths.columns), dtype=bool)
    lines = []
    for first, second in spanning_pairs(ends, times):
        _, previous = dijkstra(paths, ends[first], trodden)
        cells = traced(previous, ends[first], ends[second])
        if cells is None or len(cells) < 2:
            continue
        for cell in cells:
            trodden[cell] = True
        smooth = chaikin([paths.point(*cell)[:2] for cell in cells])
        heights = grid.sample(grid.heights, smooth)
        lines.append([[round(float(x), 3), round(float(y), 3), round(float(z), 3)] for (x, y), z in zip(smooth, heights)])
    return lines


def densified(lines, spacing):
    """Points along the polylines at most spacing metres apart."""
    found = []
    for line in lines:
        points = numpy.asarray(line, dtype=float)
        for start, end in zip(points[:-1], points[1:]):
            steps = max(1, int(math.ceil(numpy.linalg.norm(end[:2] - start[:2]) / spacing)))
            for step in range(steps):
                found.append(start + (end - start) * step / steps)
        found.append(points[-1])
    return numpy.array(found) if found else numpy.zeros((0, 3))


def path_distance(lines, points, reach):
    """Horizontal distance from each point to the nearest path, at most reach."""
    from mathutils import kdtree

    result = numpy.full(len(points), reach)
    samples = densified(lines, 0.25)
    if not len(samples):
        return result
    tree = kdtree.KDTree(len(samples))
    for index, sample in enumerate(samples.tolist()):
        tree.insert((sample[0], sample[1], 0.0), index)
    tree.balance()
    for index, point in enumerate(points[:, :2].tolist()):
        _, _, distance = tree.find((point[0], point[1], 0.0))
        if distance is not None:
            result[index] = min(distance, reach)
    return result
