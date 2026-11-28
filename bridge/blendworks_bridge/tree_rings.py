"""Tube rings for branches: strips, UVs and domes."""

import math

import numpy

from .tree_axes import CUT

BARK = 0
WOOD = 1
ROOTS = 2
DOME_ANGLES = (math.radians(35.0), math.radians(65.0))
BASE_ANGLES = (math.radians(20.0), math.radians(40.0), math.radians(60.0), math.radians(78.0))
TIP_DEPTH = 0.8
BASE_DEPTH = 0.6
FOLD_KEEP = 0.25
FOLD_WINDOW = 4


class Tube:
    def __init__(self, axis_index):
        self.axis_index = axis_index
        self.blocks = []
        self.points = []
        self.count = 0

    def add_points(self, points):
        start = self.count
        points = numpy.asarray(points, dtype=float).reshape(-1, 3)
        self.points.append(points)
        self.count += len(points)
        return numpy.arange(start, self.count)

    def add_faces(self, corners, uvs, radii, tangents, material):
        corners = numpy.asarray(corners, dtype=numpy.int64)
        shape = corners.shape
        self.blocks.append({
            "faces": corners,
            "uvs": numpy.asarray(uvs, dtype=float).reshape(shape + (2,)),
            "radii": numpy.broadcast_to(numpy.asarray(radii, dtype=float), shape).copy(),
            "tangents": numpy.broadcast_to(numpy.asarray(tangents, dtype=float), shape + (3,)).copy(),
            "materials": numpy.full(shape[0], material, dtype=numpy.int64),
        })

    def vertices(self):
        return numpy.vstack(self.points)


def clamp_folds(frame, radius):
    samples, tangents, directions = frame.samples, frame.tangents, frame.directions
    limit = numpy.full(radius.shape, numpy.inf)
    for gap in range(1, min(FOLD_WINDOW, len(samples) - 1) + 1):
        back = numpy.einsum("jc,jc->j", samples[gap:] - samples[:-gap], tangents[:-gap])
        lean = numpy.einsum("jkc,jc->jk", directions[gap:], tangents[:-gap])
        room = numpy.where(lean < 0, (1.0 - FOLD_KEEP) * numpy.maximum(back, 0.0)[:, None] / numpy.maximum(-lean, 1e-12), numpy.inf)
        limit[gap:] = numpy.minimum(limit[gap:], room)
        ahead = numpy.einsum("jc,jc->j", samples[gap:] - samples[:-gap], tangents[gap:])
        lean = numpy.einsum("jkc,jc->jk", directions[:-gap], tangents[gap:])
        room = numpy.where(lean > 0, (1.0 - FOLD_KEEP) * numpy.maximum(ahead, 0.0)[:, None] / numpy.maximum(lean, 1e-12), numpy.inf)
        limit[:-gap] = numpy.minimum(limit[:-gap], room)
    return numpy.minimum(radius, limit)


def ring_lengths(points):
    edges = numpy.linalg.norm(numpy.roll(points, -1, axis=1) - points, axis=2)
    return numpy.concatenate([numpy.zeros((len(points), 1)), numpy.cumsum(edges, axis=1)], axis=1)


def quad_strip(first, second, segments):
    k = numpy.arange(segments)
    following = (k + 1) % segments
    return numpy.stack([first[k], first[following], second[following], second[k]], axis=1)


def strip_uvs(u_first, v_first, u_second, v_second, segments):
    k = numpy.arange(segments)
    return numpy.stack([
        numpy.stack([u_first[k], numpy.full(segments, v_first)], axis=1),
        numpy.stack([u_first[k + 1], numpy.full(segments, v_first)], axis=1),
        numpy.stack([u_second[k + 1], numpy.full(segments, v_second)], axis=1),
        numpy.stack([u_second[k], numpy.full(segments, v_second)], axis=1),
    ], axis=1)


def build_tube(frame, factors, material):
    axis = frame.axis
    segments = frame.segments
    radius = clamp_folds(frame, frame.radii[:, None] * frame.polygon * factors)
    points = frame.samples[:, None, :] + radius[..., None] * frame.directions
    tube = Tube(axis.index)
    rings = tube.add_points(points.reshape(-1, 3)).reshape(len(points), segments)
    edge = 2.0 * frame.radii * frame.polygon * math.sin(math.pi / segments)
    u = edge[:, None] * numpy.arange(segments + 1)[None, :]
    v = numpy.concatenate([[0.0], numpy.cumsum(numpy.linalg.norm(numpy.diff(points, axis=0), axis=2).mean(axis=1))])
    for j in range(len(points) - 1):
        tube.add_faces(quad_strip(rings[j], rings[j + 1], segments), strip_uvs(u[j], v[j], u[j + 1], v[j + 1], segments),
                       numpy.repeat([[frame.radii[j], frame.radii[j], frame.radii[j + 1], frame.radii[j + 1]]], segments, axis=0),
                       numpy.repeat([[frame.tangents[j], frame.tangents[j], frame.tangents[j + 1], frame.tangents[j + 1]]], segments, axis=0), material)
    return tube, rings, u, v, radius


def dome(tube, frame, rings, u, v_levels, radius, end, depth_share, material, angles=DOME_ANGLES):
    index = -1 if end else 0
    sign = 1.0 if end else -1.0
    centre = frame.samples[index]
    tangent = frame.tangents[index]
    directions = frame.directions[index]
    base = radius[index]
    depth = depth_share * float(base.mean())
    previous_ring = rings[index]
    previous_u = u[index]
    previous_v = float(v_levels[index])
    previous_points = centre + base[:, None] * directions
    segments = frame.segments
    shell_radius = float(frame.radii[index])
    for angle in angles:
        layer = centre + sign * depth * math.sin(angle) * tangent + (base * math.cos(angle))[:, None] * directions
        ring = tube.add_points(layer)
        layer_u = ring_lengths(layer[None])[0]
        layer_v = previous_v + sign * float(numpy.linalg.norm(layer[0] - previous_points[0]))
        first, second = (previous_ring, ring) if end else (ring, previous_ring)
        uf, vf, us, vs = (previous_u, previous_v, layer_u, layer_v) if end else (layer_u, layer_v, previous_u, previous_v)
        tube.add_faces(quad_strip(first, second, segments), strip_uvs(uf, vf, us, vs, segments), shell_radius, tangent, material)
        previous_ring, previous_u, previous_v, previous_points = ring, layer_u, layer_v, layer
    pole_point = centre + sign * depth * tangent
    pole = tube.add_points(pole_point[None])[0]
    pole_v = previous_v + sign * float(numpy.linalg.norm(pole_point - previous_points[0]))
    k = numpy.arange(segments)
    following = (k + 1) % segments
    middle_u = 0.5 * (previous_u[k] + previous_u[k + 1])
    if end:
        corners = numpy.stack([previous_ring[k], previous_ring[following], numpy.full(segments, pole)], axis=1)
        uvs = numpy.stack([numpy.stack([previous_u[k], numpy.full(segments, previous_v)], 1), numpy.stack([previous_u[k + 1], numpy.full(segments, previous_v)], 1), numpy.stack([middle_u, numpy.full(segments, pole_v)], 1)], 1)
    else:
        corners = numpy.stack([numpy.full(segments, pole), previous_ring[following], previous_ring[k]], axis=1)
        uvs = numpy.stack([numpy.stack([middle_u, numpy.full(segments, pole_v)], 1), numpy.stack([previous_u[k + 1], numpy.full(segments, previous_v)], 1), numpy.stack([previous_u[k], numpy.full(segments, previous_v)], 1)], 1)
    tube.add_faces(corners, uvs, shell_radius, tangent, material)


def disc(tube, frame, rings, end, material):
    index = -1 if end else 0
    centre = frame.samples[index]
    ring = rings[index]
    points = tube.vertices()[ring]
    middle = tube.add_points(centre[None])[0]
    segments = frame.segments
    k = numpy.arange(segments)
    following = (k + 1) % segments
    local = points - centre
    plane = numpy.stack([local @ frame.normals[index], local @ frame.binormals[index]], axis=1)
    middle_uv = numpy.zeros((segments, 2))
    if end:
        corners = numpy.stack([ring[k], ring[following], numpy.full(segments, middle)], axis=1)
        uvs = numpy.stack([plane[k], plane[following], middle_uv], axis=1)
    else:
        corners = numpy.stack([numpy.full(segments, middle), ring[following], ring[k]], axis=1)
        uvs = numpy.stack([middle_uv, plane[following], plane[k]], axis=1)
    tube.add_faces(corners, uvs, float(frame.radii[index]), frame.tangents[index], material)


def closed_tube(frame, factors, has_roots):
    axis = frame.axis
    material = ROOTS if axis.kind == 1 else BARK
    tube, rings, u, v, radius = build_tube(frame, factors, material)
    if axis.lateral:
        disc(tube, frame, rings, False, material)
    elif has_roots:
        dome(tube, frame, rings, u, v, radius, False, BASE_DEPTH, ROOTS, BASE_ANGLES)
    else:
        disc(tube, frame, rings, False, BARK)
    if axis.end == CUT:
        disc(tube, frame, rings, True, WOOD)
    else:
        dome(tube, frame, rings, u, v, radius, True, TIP_DEPTH, material)
    return tube
