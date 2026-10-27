import math

from mathutils import Vector

from .errors import bad_args
from .meshdata import MeshData
from .shading import hard_corners
from .skin import cap, newell_normal

ON_AXIS = 1e-9
AXES = {
    "z": (Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 1, 0))),
    "x": (Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0))),
}


def clean_profile(points, closed):
    cleaned = []
    for x, z in points:
        if cleaned and math.dist(cleaned[-1], (x, z)) < 1e-9:
            continue
        cleaned.append((x, z))
    if len(cleaned) > 1 and math.dist(cleaned[0], cleaned[-1]) < 1e-9:
        cleaned.pop()
    if len(cleaned) < 2 or (closed and len(cleaned) < 3):
        raise bad_args("the profile needs more distinct points")
    return cleaned


def split_axis(point, axis):
    x, z = point
    return (x, z) if axis == "z" else (z, x)


def validate_profile(profile, axis, closed):
    on_axis = []
    for index, point in enumerate(profile):
        radius, _ = split_axis(point, axis)
        if radius < -ON_AXIS:
            raise bad_args(f"profile point {index} is on the wrong side of the axis; keep it at {'x' if axis == 'z' else 'z'} >= 0")
        if radius <= ON_AXIS:
            on_axis.append(index)
    if closed and on_axis:
        raise bad_args("a closed profile cannot touch the axis; leave closed off and end the profile on the axis")
    for index in on_axis:
        if index not in (0, len(profile) - 1):
            raise bad_args(f"only the first and last profile point may lie on the axis, not point {index}")


def position(axis, radius, height, theta):
    along, first, second = AXES[axis]
    return along * height + (first * math.cos(theta) + second * math.sin(theta)) * radius


def lathe_data(points, axis, segments, angle_degrees, caps, seam_merge, closed):
    profile = clean_profile(points, closed)
    validate_profile(profile, axis, closed)
    split = [split_axis(point, axis) for point in profile]
    full = angle_degrees >= 360.0 - 1e-9
    total_angle = math.tau if full else math.radians(angle_degrees)
    wraps = full and seam_merge
    columns = segments if wraps else segments + 1
    widest = max(radius for radius, _ in split)
    data = MeshData()
    rings = []
    for radius, height in split:
        if radius <= ON_AXIS:
            rings.append([data.vertex(position(axis, 0.0, height, 0.0))])
        else:
            rings.append([data.vertex(position(axis, radius, height, total_angle * j / segments)) for j in range(columns)])
    heights = [0.0]
    for index in range(1, len(split)):
        heights.append(heights[-1] + math.dist(split[index - 1], split[index]))
    if closed:
        heights.append(heights[-1] + math.dist(split[-1], split[0]))
    count = len(split)
    strips = count if closed else count - 1

    def column(ring, j):
        return ring[j % len(ring)] if wraps else ring[j]

    def u_of(radius, j):
        return (widest * total_angle - radius * total_angle) / 2.0 + radius * total_angle * j / segments

    island = data.island_count()
    for strip in range(strips):
        a, b = strip, (strip + 1) % count
        (ra, _), (rb, _) = split[a], split[b]
        va, vb = heights[strip], heights[strip + 1]
        for j in range(segments):
            if ra <= ON_AXIS and rb <= ON_AXIS:
                continue
            if ra <= ON_AXIS:
                ub0, ub1 = u_of(rb, j), u_of(rb, j + 1)
                data.face((rings[a][0], column(rings[b], j + 1), column(rings[b], j)), [((ub0 + ub1) / 2, va), (ub1, vb), (ub0, vb)], island, 0, True)
            elif rb <= ON_AXIS:
                ua0, ua1 = u_of(ra, j), u_of(ra, j + 1)
                data.face((column(rings[a], j), column(rings[a], j + 1), rings[b][0]), [(ua0, va), (ua1, va), ((ua0 + ua1) / 2, vb)], island, 0, True)
            else:
                quad = (column(rings[a], j), column(rings[a], j + 1), column(rings[b], j + 1), column(rings[b], j))
                uvs = [(u_of(ra, j), va), (u_of(ra, j + 1), va), (u_of(rb, j + 1), vb), (u_of(rb, j), vb)]
                data.face(quad, uvs, island, 0, True)
    corners = hard_corners(split, closed)
    if caps and full and not closed:
        corners |= {0, count - 1}
    for index in corners:
        ring = rings[index]
        if len(ring) > 1:
            for j in range(len(ring) if wraps else len(ring) - 1):
                data.harden(ring[j], ring[(j + 1) % len(ring)])
    if caps:
        add_caps(data, rings, split, axis, full, segments, total_angle, closed)
    return data


def disc_direction(split, index, along):
    neighbour = split[1][1] if index == 0 else split[-2][1]
    height = split[index][1]
    if abs(neighbour - height) > 1e-12:
        return along * (1 if height > neighbour else -1)
    mean_height = sum(h for _, h in split) / len(split)
    return along * (1 if height > mean_height else -1)


def add_caps(data, rings, split, axis, full, segments, total_angle, closed):
    along, first, second = AXES[axis]
    if full:
        if closed:
            return
        for index in (0, len(split) - 1):
            if split[index][0] <= ON_AXIS:
                continue
            points = [data.verts[i] for i in rings[index]]
            cap(data, rings[index], points, disc_direction(split, index, along))
        return
    for j, direction in ((0, -1), (segments, 1)):
        theta = total_angle * j / segments
        tangent = -first * math.sin(theta) + second * math.cos(theta)
        indices = [ring[0] if len(ring) == 1 else ring[j] for ring in rings]
        points = [data.verts[i] for i in indices]
        if newell_normal(points).length > 1e-12:
            cap(data, indices, points, tangent * direction)
