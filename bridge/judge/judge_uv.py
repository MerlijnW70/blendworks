import os
from array import array
from math import ceil, floor, isfinite

from judge_common import JudgeError

GRID = 512
SATURATING_INCREMENT = bytes(min(value + 1, 2) for value in range(256))
FULL_WEIGHT = 255
UNIT_SQUARE_SLACK = 1e-6
MAX_TILES = 64


def uv_area(corners):
    (u0, v0), (u1, v1), (u2, v2) = corners
    return abs((u1 - u0) * (v2 - v0) - (v1 - v0) * (u2 - u0)) / 2


def outside_unit_square(corners):
    low = -UNIT_SQUARE_SLACK
    high = 1 + UNIT_SQUARE_SLACK
    return any(not (low <= u <= high and low <= v <= high) for u, v in corners)


class UvGrid:
    def __init__(self, size=GRID):
        self.size = size
        self.counts = bytearray(size * size)
        self.weights = bytearray(size * size)
        self.pending = []
        self.surface = 0.0
        self.outside_surface = 0.0
        self.finished = False

    def add_mesh(self, mesh, triangle_areas, minimum_area):
        layer = mesh.uv_layers.active
        if layer is None or not mesh.loop_triangles:
            return False
        uvs = array("f", [0.0]) * (len(mesh.loops) * 2)
        layer.uv.foreach_get("vector", uvs)
        loops = array("i", [0]) * (len(mesh.loop_triangles) * 3)
        mesh.loop_triangles.foreach_get("loops", loops)
        for index, area in enumerate(triangle_areas):
            if area <= minimum_area:
                continue
            corners = tuple((uvs[loop * 2], uvs[loop * 2 + 1]) for loop in loops[index * 3 : index * 3 + 3])
            self.surface += area
            if not all(isfinite(value) for corner in corners for value in corner):
                self.outside_surface += area
                continue
            if outside_unit_square(corners):
                self.outside_surface += area
            self.pending.append((corners, area))
        return True

    def finish(self):
        if self.finished:
            return self
        self.finished = True
        total = sum(area for _, area in self.pending)
        weighted = []
        for corners, area in self.pending:
            mapped = uv_area(corners)
            if mapped == 0 or total == 0:
                continue
            weight = min(1.0, area / total / mapped)
            weighted.append((max(1, round(weight * FULL_WEIGHT)), corners))
        weighted.sort(key=lambda entry: entry[0])
        for weight, corners in weighted:
            self.rasterize_wrapped(corners, weight)
        self.pending = []
        return self

    def rasterize_wrapped(self, corners, weight):
        size = self.size
        us = [corner[0] for corner in corners]
        vs = [corner[1] for corner in corners]
        first_u, last_u = floor(min(us)), ceil(max(us)) - 1
        first_v, last_v = floor(min(vs)), ceil(max(vs)) - 1
        if (last_u - first_u + 1) * (last_v - first_v + 1) > MAX_TILES:
            self.cover_everything(weight)
            return
        for tile_u in range(first_u, last_u + 1):
            for tile_v in range(first_v, last_v + 1):
                shifted = [((u - tile_u) * size, (v - tile_v) * size) for u, v in corners]
                self.fill(shifted[0], shifted[1], shifted[2], weight)

    def cover_everything(self, weight):
        self.counts = bytearray(b"\x02") * len(self.counts)
        self.weights = bytearray(max(value, weight) for value in self.weights)

    def fill(self, a, b, c, weight=FULL_WEIGHT):
        doubled_area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if doubled_area == 0:
            return
        if doubled_area < 0:
            b, c = c, b
        size = self.size
        edges = ((a, b), (b, c), (c, a))
        lowest = max(0, floor(min(a[1], b[1], c[1]) - 0.5))
        highest = min(size - 1, floor(max(a[1], b[1], c[1]) - 0.5) + 1)
        stamp = bytes([weight])
        for row in range(lowest, highest + 1):
            span = row_span(edges, row + 0.5, size)
            if span is None:
                continue
            start = row * size + span[0]
            end = row * size + span[1] + 1
            self.counts[start:end] = self.counts[start:end].translate(SATURATING_INCREMENT)
            self.weights[start:end] = stamp * (end - start)

    def save(self, path):
        self.finish()
        temporary = path + ".partial"
        with open(temporary, "wb") as handle:
            handle.write(bytes(self.counts))
        os.replace(temporary, path)

    @classmethod
    def load(cls, path, size=GRID):
        grid = cls(size)
        try:
            with open(path, "rb") as handle:
                data = handle.read(size * size + 1)
        except OSError:
            raise JudgeError("usage", "the UV grid file is missing") from None
        if len(data) != size * size or max(data, default=0) > 2:
            raise JudgeError("usage", "the UV grid file is malformed")
        grid.counts = bytearray(data)
        grid.finished = True
        return grid

    def coverage(self):
        self.finish()
        return sum(self.weights) / (FULL_WEIGHT * len(self.weights))

    def overlap(self):
        self.finish()
        covered = len(self.counts) - self.counts.count(0)
        return self.counts.count(2) / covered if covered else 0.0

    def outside(self):
        return self.outside_surface / self.surface if self.surface else 0.0


def row_span(edges, centre_y, size):
    first = 0
    last = size - 1
    for start, end in edges:
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        if delta_y == 0:
            inside = delta_x * (centre_y - start[1])
            if inside < 0 or (inside == 0 and delta_x > 0):
                return None
            continue
        lower, upper = (start, end) if start[1] < end[1] else (end, start)
        crossing = lower[0] + (upper[0] - lower[0]) * (centre_y - lower[1]) / (upper[1] - lower[1])
        if delta_y > 0:
            last = min(last, floor(crossing - 0.5))
        else:
            first = max(first, floor(crossing - 0.5) + 1)
        if first > last:
            return None
    return first, last
