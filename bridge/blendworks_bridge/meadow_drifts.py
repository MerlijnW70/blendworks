"""Single-species flower drifts.

Flowers in drifts of one species. Drift centres fall as a Poisson process over the ground, one per DRIFT_AREA square
metres; each drift takes one species, drawn in proportion to the species' share and to how well the moisture at the centre
suits it: a Gaussian niche around the species' Ellenberg moisture value F (Ellenberg et al. 1991; Hill et al. 1999), one F
unit wide, with the meadow's moisture mapped onto F 3 (dry) to 9 (wet). A drift is a disc of the species' radius, so
inside it the flowers are as dense as their population allows and outside it only a few strays grow."""
import math

import numpy

DRIFT_AREA = 80.0
F_DRY = 3.0
F_WET = 9.0
NICHE_WIDTH = 1.0
LEAST_AFFINITY = 0.05
STRAYS = 0.04
EDGE_SHARE = 0.35
FINEST_CELL = 0.5
MOST_CELLS = 1500
FLOWER_COVER = 0.35
FULL_BLOOM = 8.0


def ellenberg(moisture):
    return F_DRY + (F_WET - F_DRY) * numpy.asarray(moisture)


def affinity(moisture, value):
    return numpy.exp(-0.5 * ((ellenberg(moisture) - value) / NICHE_WIDTH) ** 2)


class Drifts:
    """The drifts of one cover call, rasterized per species on a fine grid over the target."""

    def __init__(self, surface, moisture_corners, species, seed):
        self.species = species
        low = surface.corners[:, :, :2].min(axis=(0, 1))
        high = surface.corners[:, :, :2].max(axis=(0, 1))
        span = numpy.maximum(high - low, FINEST_CELL)
        self.cell = max(FINEST_CELL, float(span.max()) / MOST_CELLS)
        self.low = low
        self.shape = (int(math.ceil(span[1] / self.cell)) + 1, int(math.ceil(span[0] / self.cell)) + 1)
        self.masks = {entry["name"]: numpy.zeros(self.shape, dtype=numpy.float32) for entry in species}
        self.centres = {entry["name"]: [] for entry in species}
        if not species:
            return
        rng = numpy.random.default_rng([seed, 0xD21F7])
        count = int(rng.poisson(surface.area / DRIFT_AREA))
        if count == 0:
            return
        triangle, weights = surface.pick(rng.uniform(size=count), rng.uniform(size=count), rng.uniform(size=count))
        points = surface.positions(triangle, weights)
        moisture = surface.interpolate(moisture_corners, triangle, weights)
        table = numpy.array([[entry["share"] * float(affinity(value, entry["moisture"])) for entry in species] for value in moisture])
        draws = rng.uniform(size=count)
        sizes = rng.uniform(size=count)
        for index in range(count):
            row = table[index]
            if row.max() < LEAST_AFFINITY:
                continue
            chosen = species[int(numpy.searchsorted(numpy.cumsum(row) / row.sum(), draws[index], side="right").clip(0, len(species) - 1))]
            low_radius, high_radius = chosen["radius"]
            radius = low_radius + (high_radius - low_radius) * sizes[index]
            self.stamp(chosen["name"], points[index, :2], radius)
            self.centres[chosen["name"]].append((float(points[index, 0]), float(points[index, 1]), float(radius)))

    def stamp(self, name, centre, radius):
        mask = self.masks[name]
        low_c = max(0, int((centre[0] - radius - self.low[0]) / self.cell))
        high_c = min(self.shape[1], int((centre[0] + radius - self.low[0]) / self.cell) + 2)
        low_r = max(0, int((centre[1] - radius - self.low[1]) / self.cell))
        high_r = min(self.shape[0], int((centre[1] + radius - self.low[1]) / self.cell) + 2)
        if low_c >= high_c or low_r >= high_r:
            return
        xs = self.low[0] + (numpy.arange(low_c, high_c) + 0.5) * self.cell
        ys = self.low[1] + (numpy.arange(low_r, high_r) + 0.5) * self.cell
        gap = numpy.hypot(xs[None, :] - centre[0], ys[:, None] - centre[1])
        inside = numpy.clip((radius - gap) / (EDGE_SHARE * radius), 0.0, 1.0)
        mask[low_r:high_r, low_c:high_c] = numpy.maximum(mask[low_r:high_r, low_c:high_c], inside)

    def membership(self, name, points):
        mask = self.masks[name]
        column = numpy.clip(((points[:, 0] - self.low[0]) / self.cell).astype(int), 0, self.shape[1] - 1)
        row = numpy.clip(((points[:, 1] - self.low[1]) / self.cell).astype(int), 0, self.shape[0] - 1)
        return mask[row, column].astype(float)

    def mask(self, name, points):
        return STRAYS + (1.0 - STRAYS) * self.membership(name, points)

    def bloom(self, points):
        """Petal colour of the drifts at points and the share of the ground their flowers colour seen from afar."""
        colour = numpy.zeros((len(points), 3))
        weight = numpy.zeros(len(points))
        for entry in self.species:
            share = self.membership(entry["name"], points) * entry["cover"]
            colour += share[:, None] * numpy.asarray(entry["color"], dtype=float)[None, :3]
            weight += share
        amount = numpy.clip(weight, 0.0, 1.0)
        colour = numpy.divide(colour, weight[:, None], out=numpy.zeros_like(colour), where=weight[:, None] > 1e-9)
        return colour, FLOWER_COVER * amount


def drift_species(populations):
    """The drift entries of the flower populations that set drift."""
    found = []
    for population in populations:
        spec = population.get("drift")
        if spec is None:
            continue
        found.append({
            "name": population["name"],
            "moisture": spec["moisture"],
            "radius": spec["radius"],
            "share": spec["share"],
            "cover": min(1.0, population["density"] / FULL_BLOOM),
            "color": population["params"].get("petal_color", [0.8, 0.8, 0.75]),
        })
    return found


def clark_evans(points, area):
    """Clark and Evans' (1954) aggregation index R: the mean nearest-neighbour distance over its expectation
    0.5 / sqrt(density) for a random pattern; below 1 clustered, near 1 random, above 1 regular."""
    if len(points) < 2:
        return 1.0
    from mathutils import kdtree

    tree = kdtree.KDTree(len(points))
    for index, point in enumerate(points[:, :2].tolist()):
        tree.insert((point[0], point[1], 0.0), index)
    tree.balance()
    gaps = []
    for point in points[:, :2].tolist():
        nearest = tree.find_n((point[0], point[1], 0.0), 2)
        gaps.append(nearest[1][2])
    return float(numpy.mean(gaps) / (0.5 / math.sqrt(len(points) / area)))
