import math

from mathutils import Vector
from mathutils.geometry import tessellate_polygon

from .errors import bad_args, failed
from .kit_limits import MAX_SIMPLE_CHECK_POINTS

EPSILON = 1e-14


def signed_area(points):
    total = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return total / 2.0


def counter_clockwise(points):
    return list(points) if signed_area(points) >= 0 else list(reversed(points))


def clockwise(points):
    return list(points) if signed_area(points) <= 0 else list(reversed(points))


def drop_repeats(points, what):
    cleaned = []
    for point in points:
        if cleaned and math.dist(cleaned[-1], point) < 1e-9:
            continue
        cleaned.append((float(point[0]), float(point[1])))
    if len(cleaned) > 1 and math.dist(cleaned[0], cleaned[-1]) < 1e-9:
        cleaned.pop()
    if len(cleaned) < 3:
        raise bad_args(f"{what} needs at least three distinct points")
    return cleaned


def circle_points(radius, segments):
    return [(radius * math.cos(math.tau * i / segments), radius * math.sin(math.tau * i / segments)) for i in range(segments)]


def offset_loop(points, distance, miter_limit=4.0):
    count = len(points)
    out = []
    for index in range(count):
        previous, current, following = (Vector(points[(index + shift) % count]) for shift in (-1, 0, 1))
        first = (current - previous).normalized()
        second = (following - current).normalized()
        left_first = Vector((-first.y, first.x))
        left_second = Vector((-second.y, second.x))
        bisector = left_first + left_second
        bisector = bisector.normalized() if bisector.length > 1e-9 else left_first
        cosine = max(bisector.dot(left_first), 1.0 / miter_limit)
        moved = current + bisector * (distance / cosine)
        out.append((moved.x, moved.y))
    return out


def edge_directions_kept(before, after):
    count = len(before)
    for index in range(count):
        a0, a1 = before[index], before[(index + 1) % count]
        b0, b1 = after[index], after[(index + 1) % count]
        if (a1[0] - a0[0]) * (b1[0] - b0[0]) + (a1[1] - a0[1]) * (b1[1] - b0[1]) <= 0:
            return False
    return True


def orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def within(a, b, c):
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])


def segments_touch(p1, p2, p3, p4):
    d1, d2 = orientation(p3, p4, p1), orientation(p3, p4, p2)
    d3, d4 = orientation(p1, p2, p3), orientation(p1, p2, p4)
    if ((d1 > EPSILON and d2 < -EPSILON) or (d1 < -EPSILON and d2 > EPSILON)) and (
        (d3 > EPSILON and d4 < -EPSILON) or (d3 < -EPSILON and d4 > EPSILON)
    ):
        return True
    return (
        (abs(d1) <= EPSILON and within(p3, p4, p1))
        or (abs(d2) <= EPSILON and within(p3, p4, p2))
        or (abs(d3) <= EPSILON and within(p1, p2, p3))
        or (abs(d4) <= EPSILON and within(p1, p2, p4))
    )


def find_crossing(loops):
    segments = []
    for loop_index, loop in enumerate(loops):
        count = len(loop)
        for index in range(count):
            a, b = loop[index], loop[(index + 1) % count]
            segments.append((min(a[0], b[0]), max(a[0], b[0]), loop_index, index, count, a, b))
    segments.sort(key=lambda item: item[0])
    active = []
    for segment in segments:
        low = segment[0]
        active = [other for other in active if other[1] >= low]
        for other in active:
            same_loop = other[2] == segment[2]
            if same_loop:
                gap = abs(other[3] - segment[3])
                if gap <= 1 or gap == segment[4] - 1:
                    continue
            if segments_touch(segment[5], segment[6], other[5], other[6]):
                return (segment[2], segment[3]), (other[2], other[3])
        active.append(segment)
    return None


def require_simple(loops, what):
    if sum(len(loop) for loop in loops) > MAX_SIMPLE_CHECK_POINTS:
        return
    crossing = find_crossing(loops)
    if crossing is not None:
        (loop_a, edge_a), (loop_b, edge_b) = crossing
        raise bad_args(f"{what} crosses or touches itself near point {edge_a} of loop {loop_a} and point {edge_b} of loop {loop_b}")


def inside(point, polygon):
    x, y = point
    result = False
    count = len(polygon)
    for index in range(count):
        x0, y0 = polygon[index]
        x1, y1 = polygon[(index + 1) % count]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            result = not result
    return result


def require_holes_inside(outline, holes):
    for index, hole in enumerate(holes):
        if not inside(hole[0], outline):
            raise bad_args(f"hole {index} is not inside the outline")
        for other_index, other in enumerate(holes):
            if other_index != index and inside(hole[0], other):
                raise bad_args(f"hole {index} lies inside hole {other_index}")


def triangulate(outline, holes):
    loops = [outline] + holes
    flat = [point for loop in loops for point in loop]
    result = tessellate_polygon([[Vector((x, y, 0.0)) for x, y in loop] for loop in loops])
    triangles = []
    area = 0.0
    for a, b, c in result:
        doubled = orientation(flat[a], flat[b], flat[c])
        if doubled < 0:
            b, c = c, b
            doubled = -doubled
        area += doubled / 2.0
        triangles.append((a, b, c))
    expected = abs(signed_area(outline)) - sum(abs(signed_area(hole)) for hole in holes)
    if abs(area - expected) > 1e-6 * max(expected, 1e-12):
        raise failed("the outline could not be triangulated cleanly")
    return flat, triangles
