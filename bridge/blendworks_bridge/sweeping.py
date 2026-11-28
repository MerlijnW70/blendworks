"""Sweep maths: rotation-minimising frames, miters and rings along a path."""

import math

from mathutils import Quaternion, Vector

from .errors import bad_args
from .paths import MAX_MITER, arc_fractions, segment_lengths

CLOSED_TWIST_TOLERANCE = 1e-6


def initial_normal(direction, up):
    height = up - direction * up.dot(direction)
    if height.length < 1e-6:
        axis = min((Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), key=lambda a: abs(a.dot(direction)))
        height = axis - direction * axis.dot(direction)
    return height.normalized().cross(direction)


def orthogonal(normal, direction):
    return (normal - direction * normal.dot(direction)).normalized()


def transport_frames(points, closed, up):
    count = len(points)
    lengths = segment_lengths(points, closed)
    directions = [(points[(index + 1) % count] - points[index]) / lengths[index] for index in range(len(lengths))]
    normals = [initial_normal(directions[0], up)]
    for index in range(1, len(directions)):
        carried = directions[index - 1].rotation_difference(directions[index]) @ normals[-1]
        normals.append(orthogonal(carried, directions[index]))
    holonomy = 0.0
    if closed:
        wrapped = orthogonal(directions[-1].rotation_difference(directions[0]) @ normals[-1], directions[0])
        holonomy = math.atan2(directions[0].dot(normals[0].cross(wrapped)), normals[0].dot(wrapped))
    return directions, normals, holonomy


def miter_slide(offset, incoming, outgoing, where):
    along = incoming + outgoing
    base = incoming.dot(along)
    if base < 2.0 / (MAX_MITER ** 2):
        raise bad_args(f"the path bends too sharply at point {where} to join the sections; use fillet_radius")
    return incoming * (-offset.dot(along) / base)


def ring_frame(index, count, closed, directions, normals):
    if closed:
        if index == 0:
            return directions[0], directions[-1], normals[0]
        return directions[index - 1], directions[index], normals[index - 1]
    if index == 0:
        return directions[0], directions[0], normals[0]
    if index == count - 1:
        return directions[-1], directions[-1], normals[-1]
    return directions[index - 1], directions[index], normals[index - 1]


def sweep_rings(points, closed, profile, up, twist_degrees, scale_start, scale_end):
    count = len(points)
    directions, normals, holonomy = transport_frames(points, closed, up)
    fractions, total = arc_fractions(points, closed)
    twist = math.radians(twist_degrees)
    rings = []
    for index in range(count):
        incoming, other, normal = ring_frame(index, count, closed, directions, normals)
        fraction = fractions[index]
        angle = (twist - holonomy) * fraction if closed else twist * fraction
        scale = scale_start + (scale_end - scale_start) * fraction
        side = Quaternion(incoming, angle) @ normal
        binormal = incoming.cross(side)
        ring = []
        for u, v in profile:
            offset = (side * u + binormal * v) * scale
            ring.append(points[index] + offset + miter_slide(offset, incoming, other, index))
        rings.append(ring)
    return rings, total


def check_closed_arguments(twist_degrees, scale_start, scale_end):
    turns = twist_degrees / 360.0
    if abs(turns - round(turns)) > CLOSED_TWIST_TOLERANCE:
        raise bad_args("a closed path needs a twist that is a whole number of turns (a multiple of 360)")
    if abs(scale_start - scale_end) > 1e-12:
        raise bad_args("a closed path needs the same scale_start and scale_end")
