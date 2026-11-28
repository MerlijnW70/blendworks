"""Stand footprints in plan.

Stand footprints in plan. A copse or grove is a disc with a wavy rim, a hedgerow a band along a line, a forest a
polygon or the patches of a distant forest's field. Each gives the signed distance to its rim, positive inside, so the
edge zones of a stand (docs/DESIGN.md, Woodland stands) are functions of that one number. A seeded noise moves every rim
by up to rim_wander metres over rim_wavelength, so no edge runs straight."""
import math

import numpy
from mathutils.kdtree import KDTree

from .forest_place import PATCH_EDGE, patch_noise
from .land_field import smoothstep
from .noise_stack import octave_value

RIM_STREAM = 41
FIELD_CELL = 2.0
FIELD_LEVEL = 0.5


def rim_noise(xy, wavelength, seed):
    points = numpy.column_stack([xy, numpy.zeros(len(xy))])
    first = octave_value("perlin", "fbm", 1.0, points, wavelength, 1.0, seed * 977 + RIM_STREAM, 0)
    second = octave_value("perlin", "fbm", 1.0, points, wavelength / 2.7, 1.0, seed * 977 + RIM_STREAM, 1)
    return numpy.clip(first + 0.4 * second, -1.0, 1.0)


def segment_distance(xy, starts, ends):
    """Distance from every point to the nearest of the segments, and the index of that segment."""
    best = numpy.full(len(xy), numpy.inf)
    which = numpy.zeros(len(xy), dtype=numpy.int64)
    for index, (start, end) in enumerate(zip(starts, ends)):
        along = end - start
        length2 = max(float(along @ along), 1e-12)
        share = numpy.clip(((xy - start) @ along) / length2, 0.0, 1.0)
        distance = numpy.linalg.norm(xy - (start + share[:, None] * along), axis=1)
        closer = distance < best
        best[closer] = distance[closer]
        which[closer] = index
    return best, which


def inside_polygon(xy, corners):
    inside = numpy.zeros(len(xy), dtype=bool)
    count = len(corners)
    for index in range(count):
        a, b = corners[index], corners[(index + 1) % count]
        crosses = (a[1] > xy[:, 1]) != (b[1] > xy[:, 1])
        with numpy.errstate(divide="ignore", invalid="ignore"):
            at = a[0] + (xy[:, 1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        inside ^= crosses & (xy[:, 0] < at)
    return inside


class Footprint:
    """A stand's plan: kind, signed distance and the rectangle that holds it with its outer fringe."""

    def __init__(self, kind, seed, wander, wavelength):
        self.kind, self.seed, self.wander, self.wavelength = kind, seed, wander, wavelength

    def signed(self, xy):
        xy = numpy.asarray(xy, dtype=numpy.float64).reshape(-1, 2)
        return self.exact(xy) + self.wander * rim_noise(xy, self.wavelength, self.seed)

    def bounds(self, margin):
        low, high = self.extent()
        reach = margin + self.wander
        return numpy.array(low) - reach, numpy.array(high) + reach


class Disc(Footprint):
    def __init__(self, kind, centre, radius, seed, wander, wavelength):
        super().__init__(kind, seed, min(wander, 0.35 * radius), wavelength)
        self.centre, self.radius = numpy.array(centre[:2], dtype=numpy.float64), float(radius)

    def exact(self, xy):
        return self.radius - numpy.linalg.norm(xy - self.centre, axis=1)

    def extent(self):
        return self.centre - self.radius, self.centre + self.radius

    def area(self):
        return math.pi * self.radius ** 2


class Band(Footprint):
    def __init__(self, kind, line, width, closed, seed, wander, wavelength):
        super().__init__(kind, seed, min(wander, 0.25 * width), wavelength)
        points = numpy.array([point[:2] for point in line], dtype=numpy.float64)
        self.starts = points if closed else points[:-1]
        self.ends = numpy.roll(points, -1, axis=0) if closed else points[1:]
        self.points, self.width = points, float(width)

    def exact(self, xy):
        return 0.5 * self.width - segment_distance(xy, self.starts, self.ends)[0]

    def extent(self):
        return self.points.min(axis=0) - 0.5 * self.width, self.points.max(axis=0) + 0.5 * self.width

    def area(self):
        return self.width * float(numpy.linalg.norm(self.ends - self.starts, axis=1).sum())


class Polygon(Footprint):
    def __init__(self, kind, outline, seed, wander, wavelength):
        super().__init__(kind, seed, wander, wavelength)
        self.corners = numpy.array([point[:2] for point in outline], dtype=numpy.float64)

    def exact(self, xy):
        distance, _ = segment_distance(xy, self.corners, numpy.roll(self.corners, -1, axis=0))
        return numpy.where(inside_polygon(xy, self.corners), distance, -distance)

    def extent(self):
        return self.corners.min(axis=0), self.corners.max(axis=0)

    def area(self):
        x, y = self.corners[:, 0], self.corners[:, 1]
        return 0.5 * abs(float(x @ numpy.roll(y, -1) - y @ numpy.roll(x, -1)))


class Raster(Footprint):
    """Signed distance on a grid of FIELD_CELL metres to the 0.5 level of a share field, read bilinearly."""

    def __init__(self, kind, low, high, share_of, seed, wander, wavelength):
        super().__init__(kind, seed, wander, wavelength)
        self.low = numpy.asarray(low, dtype=numpy.float64)
        columns = max(2, int(math.ceil((high[0] - low[0]) / FIELD_CELL)) + 1)
        rows = max(2, int(math.ceil((high[1] - low[1]) / FIELD_CELL)) + 1)
        grid_x, grid_y = numpy.meshgrid(low[0] + FIELD_CELL * numpy.arange(columns), low[1] + FIELD_CELL * numpy.arange(rows))
        cells = numpy.column_stack([grid_x.ravel(), grid_y.ravel()])
        inside = (share_of(cells) >= FIELD_LEVEL).reshape(rows, columns)
        self.inside_share = float(inside.mean())
        self.grid = distance_grid(inside, cells.reshape(rows, columns, 2))
        self.shape = (rows, columns)
        self.high = self.low + FIELD_CELL * numpy.array([columns - 1, rows - 1])

    def exact(self, xy):
        rows, columns = self.shape
        u = numpy.clip((xy[:, 0] - self.low[0]) / FIELD_CELL, 0.0, columns - 1.000001)
        v = numpy.clip((xy[:, 1] - self.low[1]) / FIELD_CELL, 0.0, rows - 1.000001)
        i, j = v.astype(int), u.astype(int)
        fv, fu = v - i, u - j
        g = self.grid
        return (g[i, j] * (1 - fu) + g[i, j + 1] * fu) * (1 - fv) + (g[i + 1, j] * (1 - fu) + g[i + 1, j + 1] * fu) * fv

    def extent(self):
        return self.low, self.high

    def area(self):
        return self.inside_share * float(numpy.prod(self.high - self.low))


def distance_grid(inside, cells):
    """Signed distance of every cell centre to the boundary between inside and outside cells."""
    padded = numpy.pad(inside, 1, mode="edge")
    border = numpy.zeros_like(inside)
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        border |= padded[1 + di:padded.shape[0] - 1 + di, 1 + dj:padded.shape[1] - 1 + dj] != inside
    flat = cells.reshape(-1, 2)
    if not border.any():
        far = float(numpy.ptp(flat[:, 0]) + numpy.ptp(flat[:, 1]))
        return numpy.where(inside, far, -far)
    edge = flat[border.ravel()]
    tree = KDTree(len(edge))
    for index, (x, y) in enumerate(edge.tolist()):
        tree.insert((x, y, 0.0), index)
    tree.balance()
    distance = numpy.array([tree.find((x, y, 0.0))[2] for x, y in flat.tolist()]).reshape(inside.shape)
    distance = numpy.maximum(distance - 0.5 * FIELD_CELL, 0.0)
    return numpy.where(inside, distance + 0.5 * FIELD_CELL, -distance - 0.5 * FIELD_CELL)


def forest_field(settings):
    """The forest share of a distant forest's rules and patch noise at plan points, the field the far forest grows
    from, so a near stand takes the same patches and runs on across the border into the far trees."""
    def share_of(xy):
        noise = patch_noise(xy, settings["patch_size"], settings["seed"])
        threshold = settings["threshold"]
        return smoothstep(threshold + PATCH_EDGE, threshold - PATCH_EDGE, noise)
    return share_of
