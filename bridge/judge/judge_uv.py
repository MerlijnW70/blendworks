import os
from array import array
from math import floor

from judge_common import JudgeError

GRID = 512
SATURATING_INCREMENT = bytes(min(value + 1, 2) for value in range(256))


class UvGrid:
    def __init__(self, size=GRID):
        self.size = size
        self.counts = bytearray(size * size)
        self.triangles = 0

    def add_mesh(self, mesh):
        layer = mesh.uv_layers.active
        if layer is None or not mesh.loop_triangles:
            return False
        uvs = array("f", [0.0]) * (len(mesh.loops) * 2)
        layer.uv.foreach_get("vector", uvs)
        loops = array("i", [0]) * (len(mesh.loop_triangles) * 3)
        mesh.loop_triangles.foreach_get("loops", loops)
        size = self.size
        for start in range(0, len(loops), 3):
            corners = []
            for loop in loops[start : start + 3]:
                corners.append((uvs[loop * 2] * size, uvs[loop * 2 + 1] * size))
            self.fill(corners[0], corners[1], corners[2])
        return True

    def fill(self, a, b, c):
        doubled_area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if doubled_area == 0:
            return
        if doubled_area < 0:
            b, c = c, b
        self.triangles += 1
        size = self.size
        edges = ((a, b), (b, c), (c, a))
        lowest = max(0, floor(min(a[1], b[1], c[1]) - 0.5))
        highest = min(size - 1, floor(max(a[1], b[1], c[1]) - 0.5) + 1)
        for row in range(lowest, highest + 1):
            span = row_span(edges, row + 0.5, size)
            if span is None:
                continue
            start = row * size + span[0]
            end = row * size + span[1] + 1
            self.counts[start:end] = self.counts[start:end].translate(SATURATING_INCREMENT)

    def save(self, path):
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
        return grid

    def coverage(self):
        return 1.0 - self.counts.count(0) / len(self.counts)

    def overlap(self):
        covered = len(self.counts) - self.counts.count(0)
        return self.counts.count(2) / covered if covered else 0.0


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
