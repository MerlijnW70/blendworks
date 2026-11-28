"""Seeded noise functions: lattice hash, Perlin and feature points."""

import numpy

SALT = (numpy.uint64(0x9E3779B97F4A7C15), numpy.uint64(0xC2B2AE3D27D4EB4F), numpy.uint64(0x165667B19E3779F9), numpy.uint64(0x27D4EB2F165667C5))
MIX = (numpy.uint64(0xFF51AFD7ED558CCD), numpy.uint64(0xC4CEB9FE1A85EC53))
GRADIENTS = numpy.array(
    [(1, 1, 0), (-1, 1, 0), (1, -1, 0), (-1, -1, 0), (1, 0, 1), (-1, 0, 1), (1, 0, -1), (-1, 0, -1), (0, 1, 1), (0, -1, 1), (0, 1, -1), (0, -1, -1)],
    dtype=numpy.float64,
)
CORNERS = tuple((dx, dy, dz) for dx in (0, 1) for dy in (0, 1) for dz in (0, 1))
PERLIN_BOUND = 1.04
BASES = ("perlin", "worley_f1", "worley_f2_minus_f1")
UNIT_BITS = 21
UNIT_SCALE = 1.0 / (1 << UNIT_BITS)


def finalize(h):
    h = h ^ (h >> numpy.uint64(33))
    h = h * MIX[0]
    h = h ^ (h >> numpy.uint64(33))
    h = h * MIX[1]
    return h ^ (h >> numpy.uint64(33))


def lattice_hash(ix, iy, iz, seed):
    h = finalize(numpy.uint64((int(seed) * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF) + ix.astype(numpy.int64).astype(numpy.uint64) * SALT[1])
    h = finalize(h + iy.astype(numpy.int64).astype(numpy.uint64) * SALT[2])
    return finalize(h + iz.astype(numpy.int64).astype(numpy.uint64) * SALT[3])


def fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def perlin_raw(q, seed):
    cell = numpy.floor(q)
    frac = q - cell
    base = cell.astype(numpy.int64)
    smooth = fade(frac)
    total = numpy.zeros(len(q))
    for dx, dy, dz in CORNERS:
        h = lattice_hash(base[:, 0] + dx, base[:, 1] + dy, base[:, 2] + dz, seed)
        gradient = GRADIENTS[((h >> numpy.uint64(32)) % numpy.uint64(len(GRADIENTS))).astype(numpy.int64)]
        offset = frac - (dx, dy, dz)
        weight = (smooth[:, 0] if dx else 1.0 - smooth[:, 0]) * (smooth[:, 1] if dy else 1.0 - smooth[:, 1]) * (smooth[:, 2] if dz else 1.0 - smooth[:, 2])
        total += weight * numpy.einsum("ij,ij->i", gradient, offset)
    return total


def perlin(q, seed):
    return perlin_raw(q, seed) / PERLIN_BOUND


def feature_points(cell, seed):
    h = lattice_hash(cell[:, 0], cell[:, 1], cell[:, 2], seed ^ 0x5EED)
    mask = numpy.uint64((1 << UNIT_BITS) - 1)
    parts = [((h >> numpy.uint64(UNIT_BITS * axis)) & mask).astype(numpy.float64) * UNIT_SCALE for axis in range(3)]
    return cell + numpy.stack(parts, axis=1)


def shell_offsets(radius):
    span = range(-radius, radius + 1)
    inner = radius - 1 if radius > 1 else -1
    return [(dx, dy, dz) for dx in span for dy in span for dz in span if inner < max(abs(dx), abs(dy), abs(dz)) <= radius]


def worley_distances(q, seed):
    count = len(q)
    nearest = numpy.full(count, numpy.inf)
    second = numpy.full(count, numpy.inf)
    active = numpy.arange(count)
    base = numpy.floor(q).astype(numpy.int64)
    radius = 1
    while len(active) and radius <= 8:
        points = q[active]
        cells = base[active]
        first = nearest[active]
        runner = second[active]
        for offset in shell_offsets(radius):
            distance = numpy.linalg.norm(feature_points(cells + offset, seed) - points, axis=1)
            closer = distance < first
            between = ~closer & (distance < runner)
            runner = numpy.where(closer, first, numpy.where(between, distance, runner))
            first = numpy.where(closer, distance, first)
        nearest[active] = first
        second[active] = runner
        active = active[runner > radius]
        radius += 1
    return nearest, second


def basis_value(basis, q, seed):
    if basis == "perlin":
        return perlin(q, seed)
    first, second = worley_distances(q, seed)
    if basis == "worley_f1":
        return 2.0 * numpy.minimum(first, 1.0) - 1.0
    if basis == "worley_f2_minus_f1":
        return 2.0 * numpy.minimum(second - first, 1.0) - 1.0
    raise ValueError(f"unknown basis {basis}")
