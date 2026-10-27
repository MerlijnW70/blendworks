import math

from mathutils import Euler, Matrix, Vector

from .errors import bad_args
from .profiles import resolve_profile


def raise_count(points, target):
    points = list(points)
    while len(points) < target:
        count = len(points)
        longest = max(range(count), key=lambda i: math.dist(points[i], points[(i + 1) % count]))
        a, b = points[longest], points[(longest + 1) % count]
        points.insert(longest + 1, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    return points


def section_matrix(section):
    rotation = Euler([math.radians(value) for value in section["rotation"]], "XYZ").to_matrix().to_4x4()
    return Matrix.Translation(Vector(section["position"])) @ rotation


def centroid(ring):
    return sum(ring, Vector((0.0, 0.0, 0.0))) / len(ring)


def travel_direction(centres, index, closed):
    count = len(centres)
    if closed:
        return centres[(index + 1) % count] - centres[index - 1]
    return centres[min(index + 1, count - 1)] - centres[max(index - 1, 0)]


def winding_normal(ring):
    normal = Vector((0.0, 0.0, 0.0))
    for index, a in enumerate(ring):
        b = ring[(index + 1) % len(ring)]
        normal += a.cross(b)
    return normal


def best_shift(ring, reference):
    count = len(ring)
    best, shift = math.inf, 0
    for candidate in range(count):
        cost = sum((ring[(i + candidate) % count] - reference[i]).length_squared for i in range(count))
        if cost < best - 1e-18:
            best, shift = cost, candidate
    return ring[shift:] + ring[:shift]


def loft_rings(sections, closed, samples, align):
    profiles = [resolve_profile(section, f"section {index}") for index, section in enumerate(sections)]
    target = max(len(profile) for profile in profiles)
    if samples is not None:
        if samples < target:
            raise bad_args(f"samples must be at least {target}, the largest section")
        target = samples
    rings = []
    for section, profile in zip(sections, profiles):
        matrix = section_matrix(section)
        scale = section["scale"]
        points = raise_count(profile, target)
        rings.append([matrix @ Vector((u * scale, v * scale, 0.0)) for u, v in points])
    centres = [centroid(ring) for ring in rings]
    directions = [travel_direction(centres, index, closed) for index in range(len(rings))]
    for index, ring in enumerate(rings):
        if directions[index].length < 1e-12:
            raise bad_args(f"section {index} has no distinct neighbours to define the loft direction")
        if winding_normal(ring).dot(directions[index]) < 0:
            ring.reverse()
    if align:
        for index in range(1, len(rings)):
            rings[index] = best_shift(rings[index], rings[index - 1])
    return rings, directions
