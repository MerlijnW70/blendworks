"""The ring mesh of distant land: closed rectangular loops around the region at growing offsets, joined loop to loop by
zipper strips. A loop's vertices run counter-clockwise from the corner (x0, y0); each side holds its two corners, so two
neighbouring loops of any vertex counts join without T-junctions and the mesh has no cracks. Ring k spans the loops
whose half size grows from rho0 2^k to rho0 2^(k+1); its vertices are rho0 2^k / detail apart, so detail falls with
distance in nested rings. Outside the camera's view the vertices along a loop are `behind` times farther apart."""
import math

import numpy

SIDE_SAMPLES = 1024
VIEW_EDGE = math.radians(25.0)


class Rect:
    def __init__(self, low, high):
        self.x0, self.y0 = float(low[0]), float(low[1])
        self.x1, self.y1 = float(high[0]), float(high[1])
        self.centre = ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)
        self.half = ((self.x1 - self.x0) / 2.0, (self.y1 - self.y0) / 2.0)
        self.rho0 = max(self.half)

    def corners(self, offset):
        x0, y0, x1, y1 = self.x0 - offset, self.y0 - offset, self.x1 + offset, self.y1 + offset
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def distance(self, xy):
        dx = numpy.maximum(numpy.maximum(self.x0 - xy[:, 0], xy[:, 0] - self.x1), 0.0)
        dy = numpy.maximum(numpy.maximum(self.y0 - xy[:, 1], xy[:, 1] - self.y1), 0.0)
        return numpy.hypot(dx, dy)

    def project(self, xy):
        return numpy.column_stack([numpy.clip(xy[:, 0], self.x0, self.x1), numpy.clip(xy[:, 1], self.y0, self.y1)])

    def perimeter_parameter(self, xy):
        """Arc length along the border from (x0, y0), counter-clockwise, of points on the border."""
        width, height = self.x1 - self.x0, self.y1 - self.y0
        x, y = xy[:, 0], xy[:, 1]
        bottom = numpy.isclose(y, self.y0, rtol=0.0, atol=1e-6) & (x < self.x1)
        right = numpy.isclose(x, self.x1, rtol=0.0, atol=1e-6) & ~bottom & (y < self.y1)
        top = numpy.isclose(y, self.y1, rtol=0.0, atol=1e-6) & ~bottom & ~right & (x > self.x0)
        return numpy.where(bottom, x - self.x0,
                           numpy.where(right, width + y - self.y0,
                                       numpy.where(top, width + height + self.x1 - x, 2.0 * width + height + self.y1 - y)))

    def perimeter(self):
        return 2.0 * ((self.x1 - self.x0) + (self.y1 - self.y0))


def ring_loops(rect, distance, detail):
    """(offset, spacing) of every loop after the border loop; the last one lies at distance."""
    loops = []
    offset = 0.0
    ring = 0
    while offset < distance - 1e-6:
        rho = rect.rho0 * 2.0 ** ring
        spacing = rho / detail
        end = min(2.0 * rho - rect.rho0, distance)
        steps = max(1, int(math.ceil((end - offset) / spacing - 1e-9)))
        step = (end - offset) / steps
        for index in range(1, steps + 1):
            loops.append((offset + index * step, step))
        offset = end
        ring += 1
    return loops


def view_factor(points, view, behind):
    if view is None or behind <= 1.0:
        return numpy.ones(len(points))
    origin, forward, half_angle = view
    direction = points - numpy.asarray(origin)[None, :]
    length = numpy.maximum(numpy.linalg.norm(direction, axis=1), 1e-9)
    cosine = (direction @ numpy.asarray(forward)) / length
    angle = numpy.arccos(numpy.clip(cosine, -1.0, 1.0))
    t = numpy.clip((angle - half_angle) / VIEW_EDGE, 0.0, 1.0)
    return 1.0 + (behind - 1.0) * t * t * (3.0 - 2.0 * t)


def side_points(start, end, spacing, view, behind):
    start, end = numpy.asarray(start), numpy.asarray(end)
    fractions = numpy.linspace(0.0, 1.0, SIDE_SAMPLES)
    samples = start[None, :] + fractions[:, None] * (end - start)[None, :]
    density = 1.0 / (spacing * view_factor(samples, view, behind))
    length = float(numpy.linalg.norm(end - start))
    steps = numpy.concatenate([[0.0], numpy.cumsum(0.5 * (density[1:] + density[:-1]) * length / (SIDE_SAMPLES - 1))])
    count = max(1, int(math.ceil(steps[-1] - 1e-9)))
    targets = numpy.linspace(0.0, steps[-1], count + 1)
    placed = numpy.interp(targets, steps, fractions)
    return start[None, :] + placed[:, None] * (end - start)[None, :]


def loop_from_sides(sides):
    """A closed loop from four sides that each run corner to corner: (points, side start indices, side lengths)."""
    points, starts, counts = [], [], []
    for side in sides:
        starts.append(len(points))
        counts.append(len(side))
        points.extend(side[:-1].tolist())
    return numpy.array(points), starts, counts


def rect_loop(rect, offset, spacing, view, behind):
    corners = rect.corners(offset)
    sides = [side_points(corners[index], corners[(index + 1) % 4], spacing, view, behind) for index in range(4)]
    return loop_from_sides(sides)


def zipper(inner_ids, inner_t, outer_ids, outer_t):
    """Triangles that join two polylines from a shared start edge to a shared end edge, by their fractions along."""
    steps_a = numpy.column_stack([inner_t[1:], numpy.zeros(len(inner_t) - 1)])
    steps_b = numpy.column_stack([outer_t[1:], numpy.ones(len(outer_t) - 1)])
    steps = numpy.concatenate([steps_a, steps_b])
    order = numpy.lexsort((steps[:, 1], steps[:, 0]))
    from_outer = steps[order, 1] > 0.5
    i = numpy.concatenate([[0], numpy.cumsum(~from_outer)[:-1]])
    j = numpy.concatenate([[0], numpy.cumsum(from_outer)[:-1]])
    a, b = inner_ids, outer_ids
    first = numpy.where(from_outer, a[i], a[i])
    second = numpy.where(from_outer, b[numpy.minimum(j + 1, len(b) - 1)], a[numpy.minimum(i + 1, len(a) - 1)])
    third = b[j]
    return numpy.column_stack([first, second, third])


def side_ids(base, starts, counts, total, side):
    ids = base + starts[side] + numpy.arange(counts[side])
    ids[-1] = base + (starts[side] + counts[side] - 1) % total
    return ids


def fractions_along(points):
    gaps = numpy.linalg.norm(numpy.diff(points, axis=0), axis=1)
    run = numpy.concatenate([[0.0], numpy.cumsum(gaps)])
    return run / max(run[-1], 1e-12)


class RingMesh:
    def __init__(self, rect, border_sides, distance, detail, view=None, behind=1.0):
        self.rect = rect
        border, starts, counts = loop_from_sides(border_sides)
        loops = [(border, starts, counts, 0.0, 0.0)]
        for offset, spacing in ring_loops(rect, distance, detail):
            points, side_starts, side_counts = rect_loop(rect, offset, spacing, view, behind)
            loops.append((points, side_starts, side_counts, offset, spacing))
        vertices, spacing_of, bases = [], [], []
        for points, _, _, _, spacing in loops:
            bases.append(sum(len(entry) for entry in vertices))
            vertices.append(points)
            spacing_of.append(numpy.full(len(points), spacing))
        self.xy = numpy.concatenate(vertices)
        self.spacing = numpy.concatenate(spacing_of)
        if len(loops) > 1:
            self.spacing[: len(border)] = loops[1][4]
        self.border_count = len(border)
        self.loop_count = len(loops)
        triangles = []
        for index in range(len(loops) - 1):
            inner, outer = loops[index], loops[index + 1]
            for side in range(4):
                a = side_ids(bases[index], inner[1], inner[2], len(inner[0]), side)
                b = side_ids(bases[index + 1], outer[1], outer[2], len(outer[0]), side)
                triangles.append(zipper(a, fractions_along(self.xy[a]), b, fractions_along(self.xy[b])))
        faces = numpy.concatenate(triangles) if triangles else numpy.zeros((0, 3), dtype=numpy.int64)
        self.faces = upward(self.xy, faces)
        self.offsets = [loop[3] for loop in loops]


def upward(xy, faces):
    a, b, c = xy[faces[:, 0]], xy[faces[:, 1]], xy[faces[:, 2]]
    cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    flipped = faces.copy()
    flipped[cross < 0.0, 1], flipped[cross < 0.0, 2] = faces[cross < 0.0, 2], faces[cross < 0.0, 1]
    return flipped


def estimate_triangles(rect, border_count, distance, detail, view=None, behind=1.0):
    """Triangles of a ring mesh without building it: each strip has as many as its two loops have vertices."""
    counts = [border_count]
    for offset, spacing in ring_loops(rect, distance, detail):
        corners = rect.corners(offset)
        total = 0
        for index in range(4):
            total += len(side_points(corners[index], corners[(index + 1) % 4], spacing, view, behind)) - 1
        counts.append(total)
    return int(sum(counts[index] + counts[index + 1] for index in range(len(counts) - 1)))
