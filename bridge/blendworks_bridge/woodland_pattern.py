"""Stem spacing processes and measures.

Spacing of plants in stands. Trees compete for light and space, so within a stand they keep apart: a candidate stem is
kept only when it stands at least spacing times the sum of the two crown radii from every stem kept before it (a
sequential inhibition process, Diggle 2003; the hard-core models fitted to forest stands in Stoyan and Penttinen 2000).
Stands themselves are clusters: copse centres are a Poisson process thinned to a least gap (Matern's second hard-core
process), so the whole pattern is clustered at the stand scale and regular within a stand. The measures are Clark and
Evans' aggregation index with Donnelly's edge correction and Besag's L function with the translation edge correction."""
import math

import numpy

GRID_REACH = 1


class Inhibition:
    """Kept stems in a hash grid, so each candidate checks only its neighbours."""

    def __init__(self, cell):
        self.cell = max(float(cell), 1e-3)
        self.buckets = {}
        self.points = []
        self.radii = []

    def key(self, point):
        return int(math.floor(point[0] / self.cell)), int(math.floor(point[1] / self.cell))

    def add(self, point, radius):
        self.buckets.setdefault(self.key(point), []).append(len(self.points))
        self.points.append((float(point[0]), float(point[1])))
        self.radii.append(float(radius))

    def clear_of(self, point, radius, spacing, reach):
        column, row = self.key(point)
        steps = int(math.ceil(reach / self.cell))
        for i in range(column - steps, column + steps + 1):
            for j in range(row - steps, row + steps + 1):
                for index in self.buckets.get((i, j), ()):
                    other = self.points[index]
                    if math.hypot(point[0] - other[0], point[1] - other[1]) < spacing * (radius + self.radii[index]):
                        return False
        return True


def inhibit(candidates, radii, spacing, kept=None):
    """Indices of the candidates kept, in order, each clear of every stem kept before it and of kept (an Inhibition)."""
    largest = float(numpy.max(radii)) if len(radii) else 1.0
    grid = kept if kept is not None else Inhibition(2.0 * spacing * largest)
    reach = spacing * (largest + max(max(grid.radii, default=largest), largest))
    chosen = []
    for index, (point, radius) in enumerate(zip(candidates.tolist(), numpy.asarray(radii).tolist())):
        if grid.clear_of(point, radius, spacing, reach):
            grid.add(point, radius)
            chosen.append(index)
    return numpy.array(chosen, dtype=numpy.int64), grid


def poisson_rectangle(rng, low, high, density):
    area = float(numpy.prod(numpy.asarray(high) - numpy.asarray(low)))
    count = rng.poisson(max(density * area, 0.0))
    return numpy.asarray(low) + rng.random((count, 2)) * (numpy.asarray(high) - numpy.asarray(low))


def thomas(rng, low, high, parent_density, per_cluster, sigma):
    """A Thomas cluster process: Poisson parents, a Poisson number of children each at Gaussian offsets."""
    parents = poisson_rectangle(rng, low, high, parent_density)
    counts = rng.poisson(per_cluster, len(parents))
    children = numpy.repeat(parents, counts, axis=0) + rng.normal(0.0, sigma, (int(counts.sum()), 2))
    return children


def nearest_distances(points):
    if len(points) < 2:
        return numpy.zeros(len(points))
    best = numpy.full(len(points), numpy.inf)
    for start in range(0, len(points), 512):
        block = points[start:start + 512]
        distance = numpy.linalg.norm(block[:, None, :] - points[None, :, :], axis=2)
        distance[numpy.arange(len(block)), numpy.arange(start, start + len(block))] = numpy.inf
        best[start:start + len(block)] = distance.min(axis=1)
    return best


def clark_evans(points, area, perimeter):
    """R = observed mean nearest-neighbour distance over its expectation under complete spatial randomness, with
    Donnelly's (1978) edge correction: 1 is random, below 1 clustered, above 1 regular (2.149 hexagonal)."""
    count = len(points)
    if count < 3:
        return None
    observed = float(nearest_distances(points).mean())
    expected = 0.5 * math.sqrt(area / count) + (0.0514 + 0.041 / math.sqrt(count)) * perimeter / count
    return observed / expected


def besag_l(points, low, high, radii):
    """L(r) - r for a rectangular window: K(r) with the translation edge correction (Ohser and Stoyan 1981); below 0
    regular at that distance, above 0 clustered."""
    width, height = float(high[0] - low[0]), float(high[1] - low[1])
    count = len(points)
    if count < 3:
        return [None for _ in radii]
    radii = numpy.asarray(radii, dtype=numpy.float64)
    totals = numpy.zeros(len(radii))
    for start in range(0, count, 256):
        block = points[start:start + 256]
        dx = numpy.abs(block[:, None, 0] - points[None, :, 0])
        dy = numpy.abs(block[:, None, 1] - points[None, :, 1])
        distance = numpy.hypot(dx, dy)
        weight = 1.0 / numpy.maximum((width - dx) * (height - dy), 1e-9)
        same = numpy.zeros_like(distance, dtype=bool)
        same[numpy.arange(len(block)), numpy.arange(start, start + len(block))] = True
        weight[same] = 0.0
        for index, radius in enumerate(radii):
            totals[index] += float(weight[distance <= radius].sum())
    area = width * height
    k = totals * area * area / (count * (count - 1))
    return [round(float(math.sqrt(value / math.pi) - radius), 4) for value, radius in zip(k, radii)]


def quadrat_dispersion(points, low, high, side):
    """Variance over mean of the counts in squares of side metres: 1 random, above 1 clustered (Greig-Smith 1983)."""
    columns = max(1, int((high[0] - low[0]) // side))
    rows = max(1, int((high[1] - low[1]) // side))
    i = numpy.clip(((points[:, 0] - low[0]) // side).astype(int), 0, columns - 1)
    j = numpy.clip(((points[:, 1] - low[1]) // side).astype(int), 0, rows - 1)
    counts = numpy.bincount(i * rows + j, minlength=columns * rows).astype(numpy.float64)
    mean = float(counts.mean())
    return float(counts.var(ddof=1)) / mean if mean > 0.0 and len(counts) > 1 else None


def matern_centres(rng, candidates, weights, count, gap):
    """Up to count centres from weighted candidates in a seeded random order, each at least gap from those kept."""
    if len(candidates) == 0 or count <= 0:
        return numpy.zeros((0, 2))
    keys = rng.random(len(candidates)) ** (1.0 / numpy.maximum(weights, 1e-9))
    order = numpy.argsort(-keys)
    kept = []
    for index in order.tolist():
        point = candidates[index]
        if all(math.hypot(point[0] - other[0], point[1] - other[1]) >= gap for other in kept):
            kept.append(point)
            if len(kept) == count:
                break
    return numpy.array(kept).reshape(-1, 2)
