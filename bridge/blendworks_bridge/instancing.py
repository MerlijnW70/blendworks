"""Placement frames for instances along paths, edge chains, circles and points."""

import math

from mathutils import Euler, Matrix, Vector

from .errors import bad_args
from .kit_limits import MAX_INSTANCES
from .paths import clean_path, path_length, point_along
from .sweeping import transport_frames

def frame_matrix(position, forward, up):
    x = forward.normalized()
    z = (up - x * up.dot(x))
    if z.length < 1e-9:
        z = Vector((0.0, 0.0, 1.0)) if abs(x.z) < 0.9 else Vector((1.0, 0.0, 0.0))
        z = z - x * z.dot(x)
    z.normalize()
    y = z.cross(x)
    matrix = Matrix.Identity(4)
    for row in range(3):
        matrix[row][0], matrix[row][1], matrix[row][2], matrix[row][3] = x[row], y[row], z[row], position[row]
    return matrix


def normal_matrix(position, normal):
    z = normal.normalized()
    reference = Vector((1.0, 0.0, 0.0)) if abs(z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    x = (reference - z * reference.dot(z)).normalized()
    y = z.cross(x)
    matrix = Matrix.Identity(4)
    for row in range(3):
        matrix[row][0], matrix[row][1], matrix[row][2], matrix[row][3] = x[row], y[row], z[row], position[row]
    return matrix


def spaced_distances(total, closed, spacing, count, offset):
    if (spacing is None) == (count is None):
        raise bad_args("give the placement as exactly one of spacing or count")
    if count is not None:
        if offset:
            raise bad_args("offset works only with spacing")
        if closed:
            return [total * index / count for index in range(count)]
        if count == 1:
            return [0.0]
        return [total * index / (count - 1) for index in range(count)]
    distances = []
    index = 0
    limit = total - 1e-9 if closed else total + 1e-9
    if (limit - offset) / spacing > MAX_INSTANCES:
        raise bad_args(f"the spacing would place more than {MAX_INSTANCES} instances")
    while offset + index * spacing <= limit:
        distances.append(offset + index * spacing)
        index += 1
    if not distances:
        raise bad_args("no instance fits on the path; the spacing and offset leave no room")
    return distances


def path_placements(points, closed, spacing, count, offset, up, align):
    points = clean_path(points, closed)
    total = path_length(points, closed)
    directions, normals, _ = transport_frames(points, closed, up)
    placements = []
    for distance in spaced_distances(total, closed, spacing, count, offset):
        position, tangent, segment = point_along(points, closed, distance)
        height = tangent.cross(normals[segment])
        placements.append(frame_matrix(position, tangent, height) if align == "frame" else Matrix.Translation(position))
    return placements


def edge_chain(obj):
    mesh = obj.data
    neighbours = {}
    for edge in mesh.edges:
        a, b = edge.vertices
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
    if not neighbours:
        raise bad_args(f"{obj.name} has no edges")
    if any(len(links) > 2 for links in neighbours.values()):
        raise bad_args(f"{obj.name} has a vertex with more than two edges; the edges must form one path or loop")
    ends = [vertex for vertex, links in neighbours.items() if len(links) == 1]
    if len(ends) not in (0, 2):
        raise bad_args(f"{obj.name} has {len(ends)} loose ends; the edges must form one path or loop")
    start = ends[0] if ends else next(iter(neighbours))
    order = [start]
    visited = {start}
    while True:
        following = [vertex for vertex in neighbours[order[-1]] if vertex not in visited]
        if not following:
            break
        visited.add(following[0])
        order.append(following[0])
    if len(order) != len(neighbours):
        raise bad_args(f"{obj.name} has more than one separate edge chain")
    return [obj.matrix_world @ mesh.vertices[index].co for index in order], not ends


def circle_placements(circle, align):
    normal = Vector(circle["normal"])
    if normal.length == 0:
        raise bad_args("the circle normal must not be zero")
    normal.normalize()
    reference = Vector((1.0, 0.0, 0.0)) if abs(normal.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    first = (reference - normal * reference.dot(normal)).normalized()
    second = normal.cross(first)
    count = circle["count"]
    sweep = math.radians(circle["sweep"])
    full = circle["sweep"] >= 360.0 - 1e-9
    start = math.radians(circle["start_angle"])
    centre = Vector(circle["centre"])
    placements = []
    for index in range(count):
        fraction = index / count if full or count == 1 else index / (count - 1)
        angle = start + sweep * fraction
        radial = first * math.cos(angle) + second * math.sin(angle)
        position = centre + radial * circle["radius"]
        if align == "radial":
            placements.append(frame_matrix(position, radial, normal))
        elif align == "frame":
            placements.append(frame_matrix(position, normal.cross(radial), normal))
        else:
            placements.append(Matrix.Translation(position))
    return placements


def point_placements(points, normals, align):
    if normals is not None and len(normals) != len(points):
        raise bad_args(f"normals has {len(normals)} entries for {len(points)} points")
    placements = []
    for index, point in enumerate(points):
        position = Vector(point)
        if align == "frame" and normals is not None:
            if Vector(normals[index]).length == 0:
                raise bad_args(f"normal {index} is zero")
            placements.append(normal_matrix(position, Vector(normals[index])))
        else:
            placements.append(Matrix.Translation(position))
    return placements


def local_adjustment(rotation, scale):
    euler = Euler([math.radians(value) for value in rotation], "XYZ").to_matrix().to_4x4()
    return euler @ Matrix.Scale(scale, 4)


def extra_values(name, values, count):
    if values is not None and len(values) != count:
        raise bad_args(f"{name} has {len(values)} entries but there are {count} instances")


def finish_placements(placements, rotation, scale, rotations, scales):
    extra_values("rotations", rotations, len(placements))
    extra_values("scales", scales, len(placements))
    out = []
    for index, placement in enumerate(placements):
        local_rotation = rotations[index] if rotations is not None else rotation
        local_scale = scales[index] if scales is not None else scale
        out.append(placement @ local_adjustment(local_rotation, local_scale))
    return out
