import bisect
import math

from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

from .errors import failed
from .outlines import inside, orientation, signed_area

CDT_INSIDE_CONSTRAINTS = 1
CDT_EPSILON = 1e-12
AREA_AGREEMENT = 1e-6
UV_PROBE = 1e-5
UV_JUMP = 0.01


def crossing(start, end, fold):
    share = (fold - start[0]) / (end[0] - start[0])
    return (fold, start[1] + (end[1] - start[1]) * share)


def folded_loop(loop, folds, snap):
    out = []
    for index, start in enumerate(loop):
        end = loop[(index + 1) % len(loop)]
        out.append(start)
        low, high = sorted((start[0], end[0]))
        chosen = folds[bisect.bisect_right(folds, low + snap) : bisect.bisect_left(folds, high - snap)]
        if end[0] < start[0]:
            chosen = list(reversed(chosen))
        out.extend(crossing(start, end, fold) for fold in chosen)
    return out


def fold_segments(loops, folds, snap):
    segments = []
    for fold in folds:
        stops = []
        for loop_index, loop in enumerate(loops):
            for index, point in enumerate(loop):
                if abs(point[0] - fold) <= snap:
                    stops.append((point[1], loop_index, index))
        stops.sort()
        for (low, *first), (high, *second) in zip(stops, stops[1:]):
            if high - low > snap and sum(1 for loop in loops if inside((fold, (low + high) / 2.0), loop)) % 2 == 1:
                segments.append((tuple(first), tuple(second)))
    return segments


def loop_edges(loops):
    edges = []
    base = 0
    for loop in loops:
        edges.extend((base + index, base + (index + 1) % len(loop)) for index in range(len(loop)))
        base += len(loop)
    return edges


def filled(loops, a, b, c):
    centre = ((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0)
    return sum(1 for loop in loops if inside(centre, loop)) % 2 == 1


def triangulate(loops, extra_edges=()):
    flat = [point for loop in loops for point in loop]
    starts = [0]
    for loop in loops:
        starts.append(starts[-1] + len(loop))
    edges = loop_edges(loops) + [(starts[a[0]] + a[1], starts[b[0]] + b[1]) for a, b in extra_edges]
    vertices, _, faces, sources, _, _ = delaunay_2d_cdt([Vector(point) for point in flat], edges, [], CDT_INSIDE_CONSTRAINTS, CDT_EPSILON)
    if len(vertices) != len(flat) or any(len(source) != 1 for source in sources):
        raise failed("the outline touches itself, so it could not be triangulated cleanly")
    original = [source[0] for source in sources]
    triangles = []
    area = 0.0
    for face in faces:
        a, b, c = (original[index] for index in face)
        if not filled(loops, flat[a], flat[b], flat[c]):
            continue
        doubled = orientation(flat[a], flat[b], flat[c])
        if doubled < 0:
            b, c = c, b
            doubled = -doubled
        area += doubled / 2.0
        triangles.append((a, b, c))
    expected = abs(signed_area(loops[0])) - sum(abs(signed_area(hole)) for hole in loops[1:])
    if abs(area - expected) > AREA_AGREEMENT * max(expected, 1e-12):
        raise failed("the outline could not be triangulated cleanly")
    return flat, triangles


def boundary_edges(triangles):
    directed = {(tri[index], tri[(index + 1) % 3]) for tri in triangles for index in range(3)}
    return [(a, b) for a, b in directed if (b, a) not in directed]


def folded_shape(outline, holes, shift, surface, snap, tolerance):
    loops = [[(x + shift[0], y + shift[1]) for x, y in loop] for loop in [outline] + holes]
    low = min(x for x, _ in loops[0])
    high = max(x for x, _ in loops[0])
    folds = surface.folds(low, high, tolerance, max(abs(y) for _, y in loops[0]))
    loops = [folded_loop(loop, folds, snap) for loop in loops]
    return triangulate(loops, fold_segments(loops, folds, snap))


def inward_directions(points, triangles):
    sums = {}
    for a, b in boundary_edges(triangles):
        dx, dy = points[b][0] - points[a][0], points[b][1] - points[a][1]
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        for index in (a, b):
            x, y = sums.get(index, (0.0, 0.0))
            sums[index] = (x - dy / length, y + dx / length)
    return {index: (x / math.hypot(x, y), y / math.hypot(x, y)) for index, (x, y) in sums.items() if math.hypot(x, y) > 0}


def wall_points(surface, points, mapped, triangles, down, up):
    raised, sunk = {}, {}
    for index, (x, y) in inward_directions(points, triangles).items():
        position = mapped[index][0]
        step = surface.point(points[index][0] + x * UV_PROBE, points[index][1] + y * UV_PROBE)[0] - position
        direction = step.normalized() if step.length > 0 else step
        raised[index] = position - direction * up
        sunk[index] = position + direction * down
    return raised, sunk


def face_uvs(sampler, corners, surface_points):
    centre = sum(surface_points, surface_points[0] * 0.0) / len(surface_points)
    reference = sampler.nearest(centre)
    out = []
    for corner, anchor in zip(corners, surface_points * len(corners)):
        far = sampler.uv(corner, reference)
        near = sampler.uv(corner, sampler.nearest(anchor))
        out.append(near if (near - far).length <= UV_JUMP else far)
    return out


def add_solid(data, shapes, surface, shift, down, up, material, snap, tolerance, sampler=None):
    for outline, holes in shapes:
        points, triangles = folded_shape(outline, holes, shift, surface, snap, tolerance)
        mapped = [surface.point(x, y) for x, y in points]
        high = [data.vertex(position + normal * up) for position, normal in mapped]
        low = [data.vertex(position - normal * down) for position, normal in mapped]
        base = [position for position, _ in mapped]
        raised, sunk = wall_points(surface, points, mapped, triangles, down, up) if sampler is not None else ({}, {})
        for a, b, c in triangles:
            uvs = face_uvs(sampler, [base[a], base[b], base[c]], [base[a], base[b], base[c]]) if sampler is not None else None
            data.face((high[a], high[b], high[c]), uvs, 0, material, False)
            data.face((low[c], low[b], low[a]), list(reversed(uvs)) if uvs else None, 0, material, False)
        for a, b in boundary_edges(triangles):
            uvs = face_uvs(sampler, [raised[a], sunk[a], sunk[b], raised[b]], [base[a], base[b]]) if sampler is not None else None
            data.face((high[a], low[a], low[b], high[b]), uvs, 0, material, False)
    return data
