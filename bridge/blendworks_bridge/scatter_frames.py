"""Scatter instance frames: axes, tilt and instance matrices."""

import math

import numpy

ALIGNMENTS = ("normal", "up", "blend")
WORLD_UP = numpy.array([0.0, 0.0, 1.0])


def axis_directions(normals, align, factor):
    up = numpy.broadcast_to(WORLD_UP, normals.shape)
    if align == "normal":
        return normals
    if align == "up":
        return up.copy()
    mixed = up * (1.0 - factor) + normals * factor
    length = numpy.linalg.norm(mixed, axis=1)
    return numpy.divide(mixed, length[:, None], out=up.copy(), where=length[:, None] > 1e-9)


def reference_frame(axes):
    other = numpy.where((numpy.abs(axes[:, 0]) < 0.9)[:, None], numpy.array([1.0, 0.0, 0.0]), numpy.array([0.0, 1.0, 0.0]))
    first = other - axes * numpy.einsum("ij,ij->i", other, axes)[:, None]
    first /= numpy.linalg.norm(first, axis=1)[:, None]
    return first, numpy.cross(axes, first)


def tilted(axes, tilt, rng):
    count = len(axes)
    angle = numpy.radians(tilt) * rng.uniform(0.0, 1.0, count)
    heading = rng.uniform(0.0, 2.0 * math.pi, count)
    first, second = reference_frame(axes)
    lean = first * numpy.cos(heading)[:, None] + second * numpy.sin(heading)[:, None]
    return axes * numpy.cos(angle)[:, None] + lean * numpy.sin(angle)[:, None]


def instance_rotations(normals, args, rng):
    count = len(normals)
    axes = axis_directions(normals, args["align"], args["align_factor"])
    if args["tilt"] > 0.0:
        axes = tilted(axes, args["tilt"], rng)
    first, second = reference_frame(axes)
    if args["random_yaw"]:
        yaw = rng.uniform(0.0, 2.0 * math.pi, count)
        cosine, sine = numpy.cos(yaw)[:, None], numpy.sin(yaw)[:, None]
        first, second = first * cosine + second * sine, second * cosine - first * sine
    return numpy.stack([first, second, axes], axis=2)


def instance_matrices(points, rotations, scales):
    matrices = numpy.zeros((len(points), 4, 4))
    matrices[:, :3, :3] = rotations * scales[:, None, None]
    matrices[:, :3, 3] = points
    matrices[:, 3, 3] = 1.0
    return matrices
