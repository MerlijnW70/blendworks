"""3D path helpers: cleaning, lengths, turn angles and corner fillets."""

import math

import bpy
from mathutils import Quaternion, Vector

from .errors import bad_args, failed, not_found

MIN_SEGMENT = 1e-9
MAX_MITER = 10.0
STRAIGHT = 1e-6


def vectors(points):
    return [Vector(point) for point in points]


def clean_path(points, closed, what="the path"):
    points = vectors(points)
    if closed and len(points) > 2 and (points[0] - points[-1]).length < MIN_SEGMENT:
        points.pop()
    count = len(points)
    for index in range(count if closed else count - 1):
        if (points[(index + 1) % count] - points[index]).length < MIN_SEGMENT:
            raise bad_args(f"{what} has coinciding points {index} and {(index + 1) % count}")
    if closed and count < 3:
        raise bad_args(f"a closed {what} needs at least three points")
    return points


def drop_coinciding(points, closed):
    kept = [points[0]]
    for point in points[1:]:
        if (point - kept[-1]).length >= MIN_SEGMENT:
            kept.append(point)
    if closed and len(kept) > 1 and (kept[0] - kept[-1]).length < MIN_SEGMENT:
        kept.pop()
    return kept


def segment_lengths(points, closed):
    count = len(points)
    return [(points[(index + 1) % count] - points[index]).length for index in range(count if closed else count - 1)]


def path_length(points, closed):
    return sum(segment_lengths(points, closed))


def turn_angle(incoming, outgoing):
    return math.acos(max(-1.0, min(1.0, incoming.dot(outgoing))))


def fillet_path(points, radius, segments, closed):
    count = len(points)
    lengths = segment_lengths(points, closed)
    directions = [(points[(index + 1) % count] - points[index]) / lengths[index] for index in range(len(lengths))]
    corners = range(count) if closed else range(1, count - 1)
    reach = {}
    for corner in corners:
        incoming, outgoing = directions[corner - 1], directions[corner % len(directions)]
        turn = turn_angle(incoming, outgoing)
        if turn < STRAIGHT:
            continue
        if turn > math.pi - 1e-3:
            raise bad_args(f"the path turns back on itself at point {corner}")
        reach[corner] = (math.tan(turn / 2.0), turn)
    limit = math.inf
    for index, length in enumerate(lengths):
        needed = reach.get(index, (0.0, 0))[0] + reach.get((index + 1) % count, (0.0, 0))[0]
        if needed > 0:
            limit = min(limit, length / needed)
    if radius > limit * (1 + 1e-9):
        raise bad_args(f"fillet_radius {radius} does not fit; the largest radius this path allows is {limit:.6f}")
    out = []
    for index in range(count):
        if index not in reach:
            out.append(points[index].copy())
            continue
        tangent, turn = reach[index]
        incoming, outgoing = directions[index - 1], directions[index % len(directions)]
        start = points[index] - incoming * radius * tangent
        inward = (outgoing - incoming * incoming.dot(outgoing)).normalized()
        centre = start + inward * radius
        axis = incoming.cross(outgoing).normalized()
        for step in range(segments + 1):
            out.append(centre + Quaternion(axis, turn * step / segments) @ (start - centre))
    return out


def arc_fractions(points, closed):
    lengths = segment_lengths(points, closed)
    total = sum(lengths)
    cumulative = [0.0]
    for length in lengths[: len(points) - 1]:
        cumulative.append(cumulative[-1] + length)
    return [value / total for value in cumulative], total


def point_along(points, closed, distance):
    lengths = segment_lengths(points, closed)
    total = sum(lengths)
    if closed:
        distance %= total
    distance = min(max(distance, 0.0), total)
    count = len(points)
    walked = 0.0
    for index, length in enumerate(lengths):
        if walked + length >= distance - 1e-12 or index == len(lengths) - 1:
            fraction = (distance - walked) / length
            start, end = points[index], points[(index + 1) % count]
            return start.lerp(end, min(max(fraction, 0.0), 1.0)), (end - start) / length, index
        walked += length
    raise failed("the distance is beyond the path")


def curve_points(obj):
    if obj.type != "CURVE":
        raise bad_args(f"{obj.name} is a {obj.type.lower()}, not a curve")
    curve = obj.data
    if len(curve.splines) != 1:
        raise bad_args(f"{obj.name} has {len(curve.splines)} splines; give a curve with exactly one")
    saved = (curve.bevel_depth, curve.extrude, curve.bevel_object, curve.taper_object, curve.offset)
    curve.bevel_depth, curve.extrude, curve.bevel_object, curve.taper_object, curve.offset = 0.0, 0.0, None, None, 0.0
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
            edge_count = len(mesh.edges)
        finally:
            evaluated.to_mesh_clear()
    finally:
        curve.bevel_depth, curve.extrude, curve.bevel_object, curve.taper_object, curve.offset = saved
    if len(points) < 2:
        raise bad_args(f"{obj.name} has no usable points")
    closed = curve.splines[0].use_cyclic_u and edge_count >= len(points)
    return points, closed


def object_curve(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise not_found(f"no object named {name} in the scene")
    return curve_points(obj)
