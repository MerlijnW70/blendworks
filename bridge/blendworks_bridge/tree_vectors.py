"""Plain vector maths used by tree code."""

import math

IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def add(first, second):
    return (first[0] + second[0], first[1] + second[1], first[2] + second[2])


def scaled(vector, factor):
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def dot(first, second):
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def cross(first, second):
    return (first[1] * second[2] - first[2] * second[1], first[2] * second[0] - first[0] * second[2], first[0] * second[1] - first[1] * second[0])


def norm(vector):
    return math.sqrt(dot(vector, vector))


def axis_angle(axis, angle):
    length = norm(axis)
    if length < 1e-12 or angle == 0.0:
        return IDENTITY
    x, y, z = (value / length for value in axis)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    rest = 1.0 - cosine
    return (
        cosine + x * x * rest, x * y * rest - z * sine, x * z * rest + y * sine,
        y * x * rest + z * sine, cosine + y * y * rest, y * z * rest - x * sine,
        z * x * rest - y * sine, z * y * rest + x * sine, cosine + z * z * rest,
    )


def mat_vec(matrix, vector):
    return (
        matrix[0] * vector[0] + matrix[1] * vector[1] + matrix[2] * vector[2],
        matrix[3] * vector[0] + matrix[4] * vector[1] + matrix[5] * vector[2],
        matrix[6] * vector[0] + matrix[7] * vector[1] + matrix[8] * vector[2],
    )


def mat_mul(first, second):
    return tuple(sum(first[3 * row + k] * second[3 * k + column] for k in range(3)) for row in range(3) for column in range(3))


def towards(heading, target, angle):
    axis = cross(heading, target)
    if angle <= 0.0 or norm(axis) < 1e-12:
        return IDENTITY
    between = math.atan2(norm(axis), dot(heading, target))
    return axis_angle(axis, min(angle, between))


def perpendicular(heading, azimuth):
    reference = (0.0, 0.0, 1.0) if abs(heading[2]) < 0.9 else (1.0, 0.0, 0.0)
    first = cross(heading, reference)
    first = scaled(first, 1.0 / norm(first))
    second = cross(heading, first)
    return add(scaled(first, math.cos(azimuth)), scaled(second, math.sin(azimuth)))
