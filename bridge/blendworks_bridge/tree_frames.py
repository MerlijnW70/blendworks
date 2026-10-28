import math

import numpy

ALPHA = 0.5
EPSILON = 1e-12


def unit(vectors):
    length = numpy.linalg.norm(vectors, axis=-1, keepdims=True)
    return numpy.divide(vectors, length, out=numpy.zeros_like(vectors), where=length > EPSILON)


def padded(points):
    first = 2.0 * points[0] - points[1]
    last = 2.0 * points[-1] - points[-2]
    return numpy.vstack([first, points, last])


def knot_gaps(a, b):
    return numpy.maximum(numpy.linalg.norm(b - a, axis=-1), EPSILON) ** ALPHA


def lerp(a, b, ta, tb, t):
    share = ((t - ta) / (tb - ta))[:, None]
    return a + (b - a) * share


def centripetal_segment(p0, p1, p2, p3, shares):
    t0 = numpy.zeros(len(shares))
    t1 = t0 + knot_gaps(p0, p1)
    t2 = t1 + knot_gaps(p1, p2)
    t3 = t2 + knot_gaps(p2, p3)
    t = t1 + (t2 - t1) * shares
    a1 = lerp(p0, p1, t0, t1, t)
    a2 = lerp(p1, p2, t1, t2, t)
    a3 = lerp(p2, p3, t2, t3, t)
    b1 = lerp(a1, a2, t0, t2, t)
    b2 = lerp(a2, a3, t1, t3, t)
    return lerp(b1, b2, t1, t2, t)


def spline_samples(points, counts):
    points = numpy.asarray(points, dtype=float)
    extended = padded(points)
    segment = numpy.repeat(numpy.arange(len(counts)), counts)
    shares = numpy.concatenate([numpy.arange(count) / count for count in counts])
    rows = segment + 1
    inner = centripetal_segment(extended[rows - 1], extended[rows], extended[rows + 1], extended[rows + 2], shares)
    samples = numpy.vstack([inner, points[-1:]])
    segment = numpy.append(segment, len(counts) - 1)
    shares = numpy.append(shares, 1.0)
    node_samples = numpy.concatenate([[0], numpy.cumsum(counts)])
    samples[node_samples] = points
    return samples, segment, shares, node_samples


def sample_tangents(samples):
    tangents = numpy.empty_like(samples)
    tangents[1:-1] = samples[2:] - samples[:-2]
    tangents[0] = samples[1] - samples[0]
    tangents[-1] = samples[-1] - samples[-2]
    return unit(tangents)


def first_normal(tangent):
    reference = numpy.array([0.0, 0.0, 1.0]) if abs(tangent[2]) < 0.9 else numpy.array([1.0, 0.0, 0.0])
    normal = reference - tangent * float(numpy.dot(reference, tangent))
    return normal / numpy.linalg.norm(normal)


def reflect(vector, axis, square):
    return vector - (2.0 / square) * (axis[0] * vector[0] + axis[1] * vector[1] + axis[2] * vector[2]) * numpy.asarray(axis)


def transported_normals(samples, tangents, start):
    normals = numpy.empty_like(samples)
    normals[0] = start
    current = numpy.asarray(start, dtype=float)
    for index in range(len(samples) - 1):
        step = samples[index + 1] - samples[index]
        square = float(step @ step)
        if square < EPSILON:
            normals[index + 1] = current
            continue
        reflected = reflect(current, step, square)
        turned = reflect(tangents[index], step, square)
        second = tangents[index + 1] - turned
        square_two = float(second @ second)
        current = reflected if square_two < EPSILON else reflect(reflected, second, square_two)
        current = current - tangents[index + 1] * float(current @ tangents[index + 1])
        current = current / max(float(numpy.linalg.norm(current)), EPSILON)
        normals[index + 1] = current
    return normals


def seam_angle(tangents, normals, binormals, weights, away):
    away = numpy.asarray(away, dtype=float)
    for direction in (away, numpy.array([0.0, 0.0, -1.0])):
        across = direction[None, :] - tangents * (tangents @ direction)[:, None]
        x = float(numpy.sum(weights * numpy.einsum("ij,ij->i", across, normals)))
        y = float(numpy.sum(weights * numpy.einsum("ij,ij->i", across, binormals)))
        if math.hypot(x, y) > 1e-6 * max(float(numpy.sum(weights)), EPSILON):
            return math.atan2(y, x)
    return 0.0


def polygon_factor(segments):
    return math.sqrt(2.0 * math.pi / (segments * math.sin(2.0 * math.pi / segments)))


def smoothstep(edge0, edge1, value):
    share = numpy.clip((value - edge0) / numpy.maximum(edge1 - edge0, EPSILON), 0.0, 1.0)
    return share * share * (3.0 - 2.0 * share)
