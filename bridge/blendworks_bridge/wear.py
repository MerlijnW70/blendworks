import math
import random

from mathutils import Vector


def vertex_key(co):
    return (round(co.x, 6), round(co.y, 6), round(co.z, 6))


def unit_ball(rng):
    while True:
        vector = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if vector.length_squared <= 1.0:
            return vector


def jitter_displacements(bm, allowed, amplitude, seed, along_normal, linear):
    moves = {}
    factors = {}
    for vert in bm.verts:
        if allowed is not None and vert.index not in allowed:
            continue
        key = vertex_key(vert.co)
        if key not in factors:
            rng = random.Random(f"jitter:{seed}:{key}")
            factors[key] = rng.uniform(-1.0, 1.0) if along_normal else unit_ball(rng)
        factor = factors[key]
        if along_normal:
            normal = linear @ vert.normal
            moves[vert.index] = normal.normalized() * (amplitude * factor) if normal.length > 0 else Vector((0.0, 0.0, 0.0))
        else:
            moves[vert.index] = factor * amplitude
    return moves


def smoothstep(edge0, edge1, x):
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def face_area(matrix, face):
    points = [matrix @ vert.co for vert in face.verts]
    total = Vector((0.0, 0.0, 0.0))
    for index in range(1, len(points) - 1):
        total += (points[index] - points[0]).cross(points[index + 1] - points[0])
    return total.length / 2.0


def pick_sites(faces, matrix, count, rng):
    areas = [face_area(matrix, face) for face in faces]
    if sum(areas) <= 0:
        return []
    normal_matrix = matrix.to_3x3().inverted_safe().transposed()
    sites = []
    for index in rng.choices(range(len(faces)), weights=areas, k=count):
        face = faces[index]
        centre = matrix @ face.calc_center_median()
        corner = matrix @ face.verts[rng.randrange(len(face.verts))].co
        sites.append((centre.lerp(corner, rng.uniform(0.0, 0.8)), (normal_matrix @ face.normal).normalized()))
    return sites


def dent_displacements(bm, matrix, faces, allowed, amplitude, radius, count, seed):
    rng = random.Random(f"dents:{seed}")
    sites = pick_sites(faces, matrix, count, rng)
    grid = {}
    world = {}
    for vert in bm.verts:
        if allowed is not None and vert.index not in allowed:
            continue
        position = matrix @ vert.co
        world[vert.index] = position
        cell = tuple(math.floor(position[i] / radius) for i in range(3))
        grid.setdefault(cell, []).append(vert.index)
    moves = {}
    for centre, normal in sites:
        depth = amplitude * rng.uniform(0.5, 1.0)
        reach = radius * rng.uniform(0.6, 1.0)
        random_direction = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        tilt_axis = normal.cross(random_direction)
        tilt_axis = tilt_axis.normalized() if tilt_axis.length > 1e-9 else Vector((1.0, 0.0, 0.0))
        tilt = rng.uniform(0.0, 0.35)
        low = [math.floor((centre[i] - reach) / radius) for i in range(3)]
        high = [math.floor((centre[i] + reach) / radius) for i in range(3)]
        for ix in range(low[0], high[0] + 1):
            for iy in range(low[1], high[1] + 1):
                for iz in range(low[2], high[2] + 1):
                    for index in grid.get((ix, iy, iz), ()):
                        offset = world[index] - centre
                        distance = offset.length
                        if distance >= reach:
                            continue
                        falloff = 1.0 - smoothstep(0.55, 1.0, distance / reach)
                        facet = max(0.0, 1.0 + tilt * offset.dot(tilt_axis) / reach)
                        push = -normal * (depth * min(falloff * facet, 1.0))
                        total = moves.get(index, Vector((0.0, 0.0, 0.0))) + push
                        moves[index] = total.normalized() * amplitude if total.length > amplitude else total
    return moves
