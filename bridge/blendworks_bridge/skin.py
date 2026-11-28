"""Skinning of ring sections into a surface with caps and planar UVs."""

from mathutils import Vector


def ring_distances(ring):
    count = len(ring)
    steps = [(ring[(index + 1) % count] - ring[index]).length for index in range(count)]
    cumulative = [0.0]
    for step in steps:
        cumulative.append(cumulative[-1] + step)
    return cumulative


def mean_gap(ring_a, ring_b):
    return sum((a - b).length for a, b in zip(ring_a, ring_b)) / len(ring_a)


def skin(data, rings, closed_v=False, island=None, material=0, smooth=True):
    indices = [[data.vertex(point) for point in ring] for ring in rings]
    skin_between(data, indices, rings, closed_v, island, material, smooth)
    return indices


def skin_between(data, indices, rings, closed_v=False, island=None, material=0, smooth=True):
    if island is None:
        island = data.island_count()
    count = len(rings)
    heights = [0.0]
    for index in range(1, count):
        heights.append(heights[-1] + mean_gap(rings[index - 1], rings[index]))
    if closed_v:
        heights.append(heights[-1] + mean_gap(rings[-1], rings[0]))
    around = [ring_distances(ring) for ring in rings]
    spans = count if closed_v else count - 1
    for k in range(spans):
        k2 = (k + 1) % count
        size = len(rings[k])
        for j in range(size):
            j2 = (j + 1) % size
            quad = (indices[k][j], indices[k][j2], indices[k2][j2], indices[k2][j])
            uvs = [
                (around[k][j], heights[k]),
                (around[k][j + 1], heights[k]),
                (around[k2][j + 1], heights[k + 1]),
                (around[k2][j], heights[k + 1]),
            ]
            data.face(quad, uvs, island, material, smooth)


def newell_normal(points):
    normal = Vector((0.0, 0.0, 0.0))
    count = len(points)
    for index in range(count):
        a, b = points[index], points[(index + 1) % count]
        normal.x += (a.y - b.y) * (a.z + b.z)
        normal.y += (a.z - b.z) * (a.x + b.x)
        normal.z += (a.x - b.x) * (a.y + b.y)
    return normal


def planar_uvs(points, normal):
    axis_u = (points[1] - points[0]).normalized() if len(points) > 1 else Vector((1, 0, 0))
    axis_u = (axis_u - normal * axis_u.dot(normal)).normalized()
    axis_v = normal.cross(axis_u)
    return [((point - points[0]).dot(axis_u), (point - points[0]).dot(axis_v)) for point in points]


def cap(data, indices, points, outward, material=0, smooth=False):
    normal = newell_normal(points)
    if normal.length < 1e-12:
        return None
    normal.normalize()
    order = list(range(len(points)))
    if normal.dot(outward) < 0:
        order.reverse()
        normal = -normal
    ordered_points = [points[i] for i in order]
    uvs = planar_uvs(ordered_points, normal)
    return data.face([indices[i] for i in order], uvs, data.island_count(), material, smooth)
