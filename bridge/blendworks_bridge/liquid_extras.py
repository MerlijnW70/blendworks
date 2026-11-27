import math

import numpy

from .errors import bad_args

GRAVITY = 9.81
SPILL_SEGMENTS = 192
SPILL_HARMONICS = 24
SPILL_SLOPE = 1.3
SPILL_SHORTEST = 0.45
EDGE_STEPS = (0.0, 0.15, 0.35, 0.6, 0.9, 1.3, 1.8, 2.5, 3.4, 4.6, 6.2, 8.5)
CENTRE_RINGS = 8
RING_WIDTH = 0.6
RING_FADE = 0.6
STREAM_SIDES = 14
DT = 0.004
PROFILE_STEPS = 400
PROFILE_LAST = 1e-4


def outline(area, seed, roughness):
    """A closed, organic spill outline: a circle perturbed by seeded harmonics whose amplitude falls as k^-1.3 (lobes, then a
    ragged edge), kept star-shaped around its centre (no radius below 0.45 of the mean) and scaled to exactly area."""
    rng = numpy.random.default_rng([seed, 0x5B11])
    theta = numpy.linspace(0.0, 2.0 * math.pi, SPILL_SEGMENTS, endpoint=False)
    wobble = numpy.zeros_like(theta)
    for k in range(2, SPILL_HARMONICS + 1):
        wobble += roughness * rng.uniform(0.3, 1.0) / k ** SPILL_SLOPE * numpy.cos(k * theta + rng.uniform(0.0, 2.0 * math.pi))
    lowest = float(wobble.min())
    if lowest < SPILL_SHORTEST - 1.0:
        wobble *= (SPILL_SHORTEST - 1.0) / lowest
    radius = 1.0 + wobble
    points = numpy.column_stack([radius * numpy.cos(theta), radius * numpy.sin(theta)])
    return points * math.sqrt(area / polygon_area(points))


def polygon_area(points):
    x, y = points[:, 0], points[:, 1]
    return 0.5 * abs(float(numpy.dot(x, numpy.roll(y, -1)) - numpy.dot(y, numpy.roll(x, -1))))


def puddle_thickness(capillary, contact_angle):
    """Thickness of a large gravity puddle: e = 2 l_c sin(theta / 2) (de Gennes, Brochard-Wyart and Quere 2004)."""
    return 2.0 * capillary * math.sin(math.radians(contact_angle) / 2.0)


def edge_profile(distance, capillary, contact_angle):
    """Height of a puddle's surface at the given distances from its contact line (de Gennes, Brochard-Wyart and Quere 2004,
    section 1.2: the static capillary equation integrates once to (e - z)^2 = 2 l_c^2 (1 - cos phi), phi the slope angle of
    the surface, so z = e - 2 l_c sin(phi / 2) with e = 2 l_c sin(theta / 2)). The distance at which the slope has fallen to
    phi is x = l_c [ln tan(theta / 4) + 2 cos(theta / 2) - ln tan(phi / 4) - 2 cos(phi / 2)]: a wedge of angle theta at the
    contact line, flattening to the plateau over a few capillary lengths."""
    theta = math.radians(contact_angle)
    thickness = puddle_thickness(capillary, contact_angle)
    slope = theta * numpy.geomspace(1.0, PROFILE_LAST, PROFILE_STEPS)
    reach = capillary * (math.log(math.tan(theta / 4.0)) + 2.0 * math.cos(theta / 2.0) - numpy.log(numpy.tan(slope / 4.0)) - 2.0 * numpy.cos(slope / 2.0))
    height = thickness - 2.0 * capillary * numpy.sin(slope / 2.0)
    return numpy.interp(distance, reach, height, left=0.0, right=thickness)


def contour_distance(points, outline):
    """Distance of each plane point to the closed outline: to the nearest of its segments."""
    start = outline
    along = numpy.roll(outline, -1, axis=0) - outline
    length2 = numpy.maximum(numpy.einsum("ij,ij->i", along, along), 1e-30)
    result = numpy.full(len(points), math.inf)
    for block in range(0, len(points), 512):
        chunk = points[block:block + 512]
        offset = chunk[:, None, :] - start[None, :, :]
        share = numpy.clip(numpy.einsum("ijk,jk->ij", offset, along) / length2[None, :], 0.0, 1.0)
        gap = offset - share[:, :, None] * along[None, :, :]
        result[block:block + 512] = numpy.sqrt(numpy.einsum("ijk,ijk->ij", gap, gap).min(axis=1))
    return result


def spill_rings(shape, capillary):
    """Shares of the outline radius for each ring, outermost first: fine steps over the first few capillary lengths from the
    edge, where the film rises and the coffee ring lies, then even steps to the centre. Every ring shrinks along the same rays,
    so rings never cross and the sheet is one disc without folds or holes."""
    radius = numpy.linalg.norm(shape, axis=1)
    shortest = float(radius.min())
    rings = []
    for step in EDGE_STEPS:
        inward = step * capillary
        if inward >= 0.6 * shortest:
            break
        rings.append(1.0 - inward / radius)
    last = rings[-1]
    for share in numpy.linspace(1.0, 0.0, CENTRE_RINGS + 1)[1:-1]:
        rings.append(last * share)
    return rings


def spill(centre, area, seed, capillary, contact_angle, height_at, overlap):
    """A spilled film: an organic outline of the given area, rising from nothing at the contact line to the puddle thickness
    along the capillary profile of a wedge at the contact angle, lying on the surface below. Returns the top sheet, its triangles, a 0-1 coffee-ring
    weight per point (the deposit at the contact line) and a report."""
    shape = outline(area, seed, 0.35)
    thickness = puddle_thickness(capillary, contact_angle)
    rings = spill_rings(shape, capillary)
    count = len(shape)
    points = []
    for share in rings:
        ring = shape * share[:, None] if numpy.ndim(share) else shape * share
        points.extend((centre[0] + x, centre[1] + y) for x, y in ring.tolist())
    inward = contour_distance(numpy.array(points) - numpy.array(centre[:2]), shape).tolist()
    points.append((centre[0], centre[1]))
    inward.append(math.inf)
    triangles = []
    for ring_index in range(len(rings) - 1):
        start, inner = ring_index * count, (ring_index + 1) * count
        for row in range(count):
            following = (row + 1) % count
            triangles.append((start + row, start + following, inner + following))
            triangles.append((start + row, inner + following, inner + row))
    last, centre_index = (len(rings) - 1) * count, len(points) - 1
    for row in range(count):
        triangles.append((last + row, last + (row + 1) % count, centre_index))
    inward = numpy.array(inward)
    distance = numpy.where(numpy.isinf(inward), 1e9, inward)
    lift = edge_profile(distance, capillary, contact_angle)
    fade = numpy.clip((distance - RING_WIDTH * capillary) / max(RING_FADE * capillary, 1e-9), 0.0, 1.0)
    deposit = 1.0 - fade * fade * (3.0 - 2.0 * fade)
    result = numpy.zeros((len(points), 3))
    for row, (x, y) in enumerate(points):
        ground = height_at(x, y)
        if math.isnan(ground):
            raise bad_args("the spill reaches past the edge of the surface under it")
        result[row] = (x, y, ground + lift[row] - overlap)
    footprint = polygon_area(shape)
    flat, faces = numpy.array(points), numpy.array(triangles, dtype=int)
    first, second, third = (flat[faces[:, corner]] for corner in range(3))
    cover = 0.5 * numpy.abs((second[:, 0] - first[:, 0]) * (third[:, 1] - first[:, 1]) - (second[:, 1] - first[:, 1]) * (third[:, 0] - first[:, 0]))
    volume = float(numpy.sum(cover * lift[faces].mean(axis=1)))
    report = {"area": footprint, "thickness": thickness, "volume": volume, "ring_width": (RING_WIDTH + 0.5 * RING_FADE) * capillary}
    return result, numpy.array(triangles, dtype=int), deposit, report


def stream_path(start, velocity, ray_cast, limit=4.0):
    """A free-falling jet: the ballistic path from start with the initial velocity until it meets a surface."""
    position = numpy.asarray(start, dtype=float)
    speed = numpy.asarray(velocity, dtype=float)
    path, speeds = [position.copy()], [float(numpy.linalg.norm(speed))]
    time = 0.0
    while time < limit:
        following = position + speed * DT + numpy.array([0.0, 0.0, -0.5 * GRAVITY * DT * DT])
        hit = ray_cast(position, following)
        speed = speed + numpy.array([0.0, 0.0, -GRAVITY * DT])
        if hit is not None:
            path.append(numpy.asarray(hit))
            speeds.append(float(numpy.linalg.norm(speed)))
            return numpy.array(path), numpy.array(speeds), True
        position = following
        path.append(position.copy())
        speeds.append(float(numpy.linalg.norm(speed)))
        time += DT
    return numpy.array(path), numpy.array(speeds), False


def stream_mesh(path, speeds, radius):
    """A tube along the jet whose radius narrows by continuity: r = r0 sqrt(v0 / v)."""
    radii = radius * numpy.sqrt(speeds[0] / numpy.maximum(speeds, 1e-6))
    tangent = numpy.gradient(path, axis=0)
    tangent /= numpy.maximum(numpy.linalg.norm(tangent, axis=1), 1e-12)[:, None]
    reference = numpy.array([0.0, 0.0, 1.0])
    points, triangles = [], []
    side = numpy.cross(tangent[0], reference)
    if numpy.linalg.norm(side) < 1e-6:
        side = numpy.array([1.0, 0.0, 0.0])
    for row, (centre, direction) in enumerate(zip(path, tangent)):
        side = side - direction * numpy.dot(side, direction)
        side /= max(numpy.linalg.norm(side), 1e-12)
        other = numpy.cross(direction, side)
        for k in range(STREAM_SIDES):
            angle = 2.0 * math.pi * k / STREAM_SIDES
            points.append(centre + radii[row] * (math.cos(angle) * side + math.sin(angle) * other))
    rows = len(path)
    for row in range(rows - 1):
        for k in range(STREAM_SIDES):
            a, b = row * STREAM_SIDES + k, row * STREAM_SIDES + (k + 1) % STREAM_SIDES
            triangles.append((a, b, b + STREAM_SIDES))
            triangles.append((a, b + STREAM_SIDES, a + STREAM_SIDES))
    for row, flip in ((0, True), (rows - 1, False)):
        centre_index = len(points)
        points.append(path[row])
        for k in range(STREAM_SIDES):
            a, b = row * STREAM_SIDES + k, row * STREAM_SIDES + (k + 1) % STREAM_SIDES
            triangles.append((b, a, centre_index) if flip else (a, b, centre_index))
    return numpy.array(points), numpy.array(triangles, dtype=int), radii


def ellipsoid(centre, axes, rings=8, segments=12):
    points, triangles = [], []
    points.append(centre - axes[2])
    for ring in range(1, rings):
        phi = math.pi * ring / rings - math.pi / 2.0
        for k in range(segments):
            theta = 2.0 * math.pi * k / segments
            points.append(centre + math.cos(phi) * (math.cos(theta) * axes[0] + math.sin(theta) * axes[1]) + math.sin(phi) * axes[2])
    points.append(centre + axes[2])
    top = len(points) - 1
    for k in range(segments):
        triangles.append((0, 1 + (k + 1) % segments, 1 + k))
    for ring in range(rings - 2):
        base = 1 + ring * segments
        for k in range(segments):
            a, b = base + k, base + (k + 1) % segments
            triangles.append((a, b, b + segments))
            triangles.append((a, b + segments, a + segments))
    base = 1 + (rings - 2) * segments
    for k in range(segments):
        triangles.append((base + k, base + (k + 1) % segments, top))
    return numpy.array(points), numpy.array(triangles, dtype=int)


def drips(outer, count, capillary, viscosity, seed, rim):
    """Beads running down the outside of the wall below the rim: elongated drops lying on the wall, longer for thicker liquids."""
    rng = numpy.random.default_rng([seed, 0xD819])
    centres, normals = outer
    if not len(centres):
        return numpy.zeros((0, 3)), numpy.zeros((0, 3), dtype=int), 0
    length_scale = 1.0 + max(math.log10(max(viscosity, 1e-4) / 1e-3), 0.0) / 2.0
    points, triangles = [], []
    chosen = rng.choice(len(centres), size=min(count, len(centres)), replace=False)
    for row in chosen.tolist():
        normal = normals[row] / max(numpy.linalg.norm(normals[row]), 1e-12)
        down = numpy.array([0.0, 0.0, -1.0]) - normal * (-normal[2])
        if numpy.linalg.norm(down) < 1e-6:
            continue
        down /= numpy.linalg.norm(down)
        lateral = numpy.cross(normal, down)
        radius = capillary * rng.uniform(0.35, 0.6)
        length = radius * rng.uniform(2.0, 4.0) * length_scale
        centre = centres[row] + down * length * rng.uniform(0.6, 1.4) + normal * radius * 0.25
        piece, faces = ellipsoid(centre, (lateral * radius, normal * radius * 0.55, down * length))
        triangles.extend((faces + len(points)).tolist())
        points.extend(piece.tolist())
    return numpy.array(points).reshape(-1, 3), numpy.array(triangles, dtype=int).reshape(-1, 3), len(chosen)


def outer_faces(points, triangles, rim, band, outside):
    """Steep faces just below the rim whose normal points into open air (outside tells, per point, whether it is outside)."""
    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    normals = numpy.cross(b - a, c - a)
    lengths = numpy.maximum(numpy.linalg.norm(normals, axis=1), 1e-30)
    outward = 1.0 if float(numpy.einsum("ij,ij->i", a, numpy.cross(b, c)).sum()) >= 0.0 else -1.0
    normals = normals / lengths[:, None] * outward
    centres = (a + b + c) / 3.0
    keep = (numpy.abs(normals[:, 2]) < 0.6) & (centres[:, 2] < rim) & (centres[:, 2] > rim - band)
    rows = [row for row in numpy.nonzero(keep)[0].tolist() if outside(centres[row], normals[row])]
    return centres[rows], normals[rows]


def bubbles(count, seed, contains, low, high, radius):
    rng = numpy.random.default_rng([seed, 0xB0B])
    points, triangles, placed = [], [], 0
    tries = 0
    while placed < count and tries < count * 50:
        tries += 1
        centre = rng.uniform(low, high)
        size = radius * rng.uniform(0.4, 1.0)
        if not contains(centre, size):
            continue
        piece, faces = ellipsoid(centre, (numpy.array([size, 0, 0]), numpy.array([0, size, 0]), numpy.array([0, 0, size])), 4, 6)
        triangles.extend((faces + len(points)).tolist())
        points.extend(piece.tolist())
        placed += 1
    return numpy.array(points).reshape(-1, 3), numpy.array(triangles, dtype=int).reshape(-1, 3), placed
