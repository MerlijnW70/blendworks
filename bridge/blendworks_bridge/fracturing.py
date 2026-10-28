import math

import numpy

from .polyhedron import split

CENTROID_SPREAD = 0.25
ATTEMPTS = 60
SMALLEST_SHARE = 1e-9
CORNER_SHARE = 0.35
SHARP_DEGREES = 20.0
TILT = 0.55


def random_direction(rng):
    vector = rng.normal(size=3)
    return vector / numpy.linalg.norm(vector)


def binary_pieces(solid, count, rng, min_size, fresh):
    pieces = [(diagonal(solid), solid)]
    closed = []
    while len(pieces) + len(closed) < count and pieces:
        pieces.sort(key=lambda entry: entry[0])
        size, piece = pieces.pop()
        children = cut_once(piece, piece.volume(), rng, min_size, fresh)
        if children is None:
            closed.append((size, piece))
            continue
        pieces.extend((diagonal(child), child) for child in children)
    return [piece for _, piece in pieces + closed]


def diagonal(piece):
    return float(numpy.linalg.norm(numpy.ptp(piece.used_points(), axis=0)))


def cut_once(piece, volume, rng, min_size, fresh):
    centre = piece.centroid()
    spread = CENTROID_SPREAD * diagonal(piece)
    for _ in range(ATTEMPTS):
        normal = random_direction(rng)
        point = centre + rng.normal(size=3) * spread
        children = split(piece, normal, float(normal @ point), fresh)
        if len(children) != 2:
            continue
        parts = list(children.values())
        if min(part.volume() for part in parts) <= SMALLEST_SHARE * volume:
            continue
        if min_size > 0.0 and min(part.min_width() for part in parts) < min_size:
            continue
        return parts
    return None


def seed_points(solid, count, rng, min_size):
    low, high = solid.used_points().min(axis=0), solid.used_points().max(axis=0)
    margin = min_size / 2.0
    found = []
    for _ in range(count * 400):
        if len(found) == count:
            break
        point = low + rng.random(3) * (high - low)
        if not inside_with_margin(solid, point, margin):
            continue
        if any(numpy.linalg.norm(point - other) < min_size for other in found):
            continue
        found.append(point)
    return found


def inside_with_margin(solid, point, margin):
    return all(float((point - origin) @ normal) <= -margin for normal, origin in solid.planes())


def voronoi_cells(solid, seeds, fresh):
    cells = []
    for index, seed in enumerate(seeds):
        cell = solid
        others = sorted((numpy.linalg.norm(other - seed), number) for number, other in enumerate(seeds) if number != index)
        for distance, number in others:
            if distance / 2.0 > float(numpy.max(numpy.linalg.norm(cell.used_points() - seed, axis=1))):
                break
            other = seeds[number]
            normal = (other - seed) / distance
            children = split(cell, normal, float(normal @ (seed + other) / 2.0), fresh, sides=(1,))
            if 1 in children:
                cell = children[1]
        cells.append(cell)
    return cells


def edge_features(solid):
    sharp = []
    limit = math.cos(math.radians(SHARP_DEGREES))
    for (a, b), owners in solid.edges().items():
        if len(owners) != 2:
            continue
        first, second = (solid.face_normal(solid.faces[number]) for number in owners)
        if float(first @ second) < limit:
            sharp.append((a, b, first + second))
    return sharp


def chip_once(solid, rng, depth, fresh):
    edges = edge_features(solid)
    if not edges:
        return None
    lengths = numpy.array([numpy.linalg.norm(solid.points[b] - solid.points[a]) for a, b, _ in edges])
    for attempt in range(ATTEMPTS):
        shrink = 0.9 ** (attempt // 4)
        if rng.random() < CORNER_SHARE:
            a, b, outward = edges[int(rng.choice(len(edges), p=lengths / lengths.sum()))]
            point = solid.points[a if rng.random() < 0.5 else b]
            outward = corner_direction(solid, point)
        else:
            a, b, outward = edges[int(rng.choice(len(edges), p=lengths / lengths.sum()))]
            point = solid.points[a] + (solid.points[b] - solid.points[a]) * rng.random()
        outward = outward / numpy.linalg.norm(outward)
        normal = outward + TILT * random_direction(rng)
        normal /= numpy.linalg.norm(normal)
        reach = float(rng.uniform(0.5, 1.0)) * depth * shrink
        children = split(solid, normal, float(normal @ point) - reach, fresh)
        if len(children) != 2:
            continue
        removed, kept = children[-1], children[1]
        if float(numpy.max(numpy.linalg.norm(removed.used_points() - point, axis=1))) > depth:
            continue
        return kept, removed
    return None


def corner_direction(solid, point):
    total = numpy.zeros(3)
    for face in solid.faces:
        if any(numpy.allclose(solid.points[index], point, atol=1e-9) for index in face):
            total += solid.face_normal(face)
    return total if numpy.linalg.norm(total) > 0.0 else numpy.array([0.0, 0.0, 1.0])
