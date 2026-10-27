import math

import numpy

TOLERANCE = 1e-7


class DiskGrid:
    def __init__(self, cell):
        self.cell = cell
        self.buckets = {}

    def span(self, point, radius):
        cell = self.cell
        low = [math.floor((point[axis] - radius) / cell) for axis in range(3)]
        high = [math.floor((point[axis] + radius) / cell) for axis in range(3)]
        return low, high

    def cells(self, point, radius):
        low, high = self.span(point, radius)
        for ix in range(low[0], high[0] + 1):
            for iy in range(low[1], high[1] + 1):
                for iz in range(low[2], high[2] + 1):
                    yield (ix, iy, iz)


def overlaps(point, radius, grid, kept_points, kept_radii):
    for key in grid.cells(point, radius):
        bucket = grid.buckets.get(key)
        if bucket is None:
            continue
        for other in bucket:
            reach = (radius + kept_radii[other]) * (1.0 + TOLERANCE)
            near = kept_points[other]
            dx, dy, dz = point[0] - near[0], point[1] - near[1], point[2] - near[2]
            if dx * dx + dy * dy + dz * dz < reach * reach:
                return True
    return False


def thin_to_disks(points, radii, order, limit=None):
    if len(points) == 0:
        return []
    grid = DiskGrid(2.0 * math.sqrt(float(radii.min()) * float(radii.max())))
    coordinates = points.tolist()
    sizes = radii.tolist()
    kept = []
    kept_points = {}
    kept_radii = {}
    for index in order.tolist():
        point, radius = coordinates[index], sizes[index]
        if overlaps(point, radius, grid, kept_points, kept_radii):
            continue
        kept.append(index)
        kept_points[index] = point
        kept_radii[index] = radius
        for key in grid.cells(point, radius):
            grid.buckets.setdefault(key, []).append(index)
        if limit is not None and len(kept) >= limit:
            break
    return kept


def pair_clearance(points, radii, block=512):
    count = len(points)
    if count < 2:
        return None, None
    smallest = math.inf
    tightest = math.inf
    for start in range(0, count, block):
        chunk = points[start:start + block]
        gaps = numpy.linalg.norm(chunk[:, None, :] - points[None, :, :], axis=2)
        reach = radii[start:start + block, None] + radii[None, :]
        rows = numpy.arange(len(chunk))
        gaps[rows, start + rows] = numpy.inf
        smallest = min(smallest, float(gaps.min()))
        tightest = min(tightest, float((gaps / reach).min()))
    return smallest, tightest
