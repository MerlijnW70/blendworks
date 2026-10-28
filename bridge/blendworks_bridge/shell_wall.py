import math

from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .errors import failed

ROUNDS = 12
FOLDED = 0.4
MARGIN = 0.02
CAVITY_ROOM = 3.5
WINDOW = 2.5


def vertex_normals(rings):
    count = len(rings)
    normals = []
    for k, ring in enumerate(rings):
        size = len(ring)
        centre = sum(ring, Vector()) / size
        before, after = rings[max(k - 1, 0)], rings[min(k + 1, count - 1)]
        row = []
        for j in range(size):
            around = ring[(j + 1) % size] - ring[j - 1]
            along = after[j] - before[j]
            normal = around.cross(along)
            if normal.length < 1e-18:
                normal = ring[j] - centre
            normal.normalize()
            if normal.dot(ring[j] - centre) < 0:
                normal.negate()
            row.append(normal)
        normals.append(row)
    return normals


def surface_tree(rings):
    points = [point for ring in rings for point in ring]
    size = len(rings[0])
    quads = []
    for k in range(len(rings) - 1):
        for j in range(size):
            j2 = (j + 1) % size
            quads.append((k * size + j, k * size + j2, (k + 1) * size + j2, (k + 1) * size + j))
    return BVHTree.FromPolygons(points, quads)


def nearest_distance(points, tree):
    return min(tree.find_nearest(point)[3] for point in points)


def window_rings(outer, reach):
    gaps = [(sum(outer[k + 1], Vector()) - sum(outer[k], Vector())).length / len(outer[k]) for k in range(len(outer) - 1)]
    return min(len(outer), max(3, math.ceil(WINDOW * reach / max(min(gaps), 1e-12))))


def probes(rings, k):
    ring = rings[k]
    points = list(ring)
    if k + 1 < len(rings):
        following = rings[k + 1]
        size = len(ring)
        points.extend((ring[j] + ring[(j + 1) % size] + following[j] + following[(j + 1) % size]) / 4.0 for j in range(size))
    return points


def measured_walls(outer, inner, reach):
    window = window_rings(outer, reach)
    block = max(window, 8)
    walls = []
    for start in range(0, len(outer), block):
        low, high = max(0, start - window), min(len(outer), start + block + window)
        inner_tree, outer_tree = surface_tree(inner[low:high]), surface_tree(outer[low:high])
        for k in range(start, min(start + block, len(outer))):
            walls.append(min(nearest_distance(probes(outer, k), inner_tree), nearest_distance(probes(inner, k), outer_tree)))
    return walls


def cavity_start(spiral, thickness, thickening):
    smallest = min(spiral.profile.width, spiral.profile.height)
    times = spiral.times()[spiral.tail:]
    for index, t in enumerate(times):
        flare = 1.0 + (spiral.lip["flare"] * spiral.lip_factor(t) if spiral.lip else 0.0)
        if spiral.scale(t) * flare * smallest >= CAVITY_ROOM * thickness * thickening(t):
            return spiral.tail + index
    raise failed("thickness is too large for the final aperture; make it smaller than a third of the aperture size")


def inner_rings(spiral, outer, thickness, thickening):
    first = cavity_start(spiral, thickness, thickening)
    normals_all = vertex_normals(outer)
    times_all = spiral.times()
    peak = max(thickening(t) for t in times_all)
    factor = 1.0
    for _ in range(ROUNDS):
        rings, normals, times = outer[first:], normals_all[first:], times_all[first:]
        if len(rings) < 3:
            break
        inner = [[point - normal * (factor * thickness * thickening(t)) for point, normal in zip(ring, row)] for ring, row, t in zip(rings, normals, times)]
        walls = measured_walls(rings, inner, factor * thickness * peak)
        if min(walls) >= thickness * (1.0 + MARGIN):
            return first, inner, min(walls)
        folded = [index for index, wall in enumerate(walls) if wall < FOLDED * thickness]
        if folded:
            first += max(folded) + 1
        else:
            factor *= thickness * (1.0 + 4 * MARGIN) / min(walls)
    raise failed("the wall could not be made thick enough everywhere; lower thickness, the lip thickening, or the heights of ribs and spiral_ridges")
