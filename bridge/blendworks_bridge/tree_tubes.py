import math

import numpy

from .tree_axes import CUT
from .tree_frames import first_normal, polygon_factor, sample_tangents, seam_angle, smoothstep, spline_samples, transported_normals

FLARE_RESOLUTION = 16.0
LOBE_POWER = 4
LOBE_REACH = 2.0
CUT_STUB = 0.5
UP = numpy.array([0.0, 0.0, 1.0])
START_SHRINK = 0.6
THICK_LATERAL = 0.9


class Settings:
    def __init__(self, args, skeleton, density=1.0):
        rings = args["ring_segments"]
        self.minimum = rings["min"]
        self.maximum = max(rings["min"], rings["max"])
        self.per_metre = rings["per_metre"] * density
        self.rings_per_segment = max(1, int(round(args["rings_per_segment"] * density)))
        self.density = density
        base = float(skeleton.radii[0])
        flare = args["flare"]
        self.flare_amount = flare["amount"]
        self.flare_height = flare.get("height", 3.0 * base)
        self.lobes = flare["lobes"]
        roots = args["root_flare"]
        self.root_flare = roots["amount"]
        self.root_length = roots.get("length", 3.0 * base)
        self.collar = args["collar"]
        view = numpy.asarray(args["view"], dtype=float)
        self.away = -view / max(float(numpy.linalg.norm(view)), 1e-12)

    def resolved(self):
        return {
            "flare": {"amount": self.flare_amount, "height": round(self.flare_height, 6), "lobes": self.lobes},
            "root_flare": {"amount": self.root_flare, "length": round(self.root_length, 6)},
        }


def ring_count(settings, radius):
    return int(min(settings.maximum, max(settings.minimum, round(2.0 * math.pi * radius * settings.per_metre))))


def node_radii(skeleton, axis):
    radii = skeleton.radii[axis.nodes].astype(float)
    if axis.lateral:
        radii[0] = radii[1]
    return radii


def is_base_root(axis):
    return axis.lateral and axis.kind == 1 and axis.nodes[0] == 0


def segment_counts(points, radii, segments, settings, zone):
    lengths = numpy.linalg.norm(numpy.diff(points, axis=0), axis=1)
    edges = 2.0 * math.pi * 0.5 * (radii[:-1] + radii[1:]) / segments
    counts = numpy.clip(numpy.round(lengths / numpy.maximum(edges, 1e-9)), 1, settings.rings_per_segment).astype(int)
    if zone:
        start = numpy.concatenate([[0.0], numpy.cumsum(lengths)])[:-1]
        inside = start < zone
        finer = numpy.ceil(lengths[inside] * FLARE_RESOLUTION / zone).astype(int)
        counts[inside] = numpy.maximum(counts[inside], numpy.minimum(finer, 4 * max(1, settings.rings_per_segment)))
    return counts


def predicted_triangles(skeleton, axes, settings):
    total = 0
    for axis in axes:
        points = skeleton.positions[axis.nodes]
        radii = node_radii(skeleton, axis)
        segments = ring_count(settings, float(radii.max()))
        counts = segment_counts(points, radii, segments, settings, flare_zone(axis, settings))
        total += 2 * segments * int(counts.sum()) + 4 * segments
    return total


def flare_zone(axis, settings):
    if axis.index == 0:
        return settings.flare_height if settings.flare_amount > 0 else None
    if is_base_root(axis):
        return settings.root_length if settings.root_flare > 0 else None
    return None


def ground_aligned(tangents, along, height):
    share = smoothstep(0.0, height, along)[:, None]
    blended = (1.0 - share) * UP[None, :] + share * tangents
    return blended / numpy.linalg.norm(blended, axis=1, keepdims=True)


class Frame:
    def __init__(self, skeleton, axis, settings):
        points = skeleton.positions[axis.nodes].astype(float)
        radii = node_radii(skeleton, axis)
        self.axis = axis
        self.segments = ring_count(settings, float(radii.max()))
        counts = segment_counts(points, radii, self.segments, settings, flare_zone(axis, settings))
        self.samples, segment, shares, self.node_samples = spline_samples(points, counts)
        upper = numpy.minimum(segment + 1, len(radii) - 1)
        self.radii = radii[segment] + (radii[upper] - radii[segment]) * shares
        self.tangents = sample_tangents(self.samples)
        if axis.end == CUT:
            stub = self.samples[-1] + CUT_STUB * self.radii[-1] * self.tangents[-1]
            self.samples = numpy.vstack([self.samples, stub])
            self.radii = numpy.append(self.radii, self.radii[-1])
            self.tangents = numpy.vstack([self.tangents, self.tangents[-1]])
        steps = numpy.linalg.norm(numpy.diff(self.samples, axis=0), axis=1)
        self.along = numpy.concatenate([[0.0], numpy.cumsum(steps)])
        if axis.index == 0 and settings.flare_amount > 0:
            self.tangents = ground_aligned(self.tangents, self.along, settings.flare_height)
        self.normals = transported_normals(self.samples, self.tangents, first_normal(self.tangents[0]))
        self.binormals = numpy.cross(self.tangents, self.normals)
        weights = self.radii * numpy.concatenate([steps, [0.0]])
        self.seam = seam_angle(self.tangents, self.normals, self.binormals, weights, settings.away)
        turns = self.seam + 2.0 * math.pi * numpy.arange(self.segments) / self.segments
        self.directions = numpy.cos(turns)[None, :, None] * self.normals[:, None, :] + numpy.sin(turns)[None, :, None] * self.binormals[:, None, :]
        self.polygon = polygon_factor(self.segments)


def trunk_factors(frame, settings, root_directions):
    along = frame.along
    height = max(settings.flare_height, 1e-9)
    decay = numpy.where(along < height, (100.0 ** (1.0 - along / height) - 1.0) / 99.0, 0.0)
    weight = numpy.ones(frame.directions.shape[:2])
    if root_directions and settings.lobes > 0:
        raw = numpy.zeros(frame.directions.shape[:2])
        for direction, share in root_directions:
            across = direction[None, :] - frame.tangents * (frame.tangents @ direction)[:, None]
            across /= numpy.maximum(numpy.linalg.norm(across, axis=1, keepdims=True), 1e-12)
            raw += share * numpy.maximum(0.0, numpy.einsum("jkc,jc->jk", frame.directions, across)) ** LOBE_POWER
        mean = raw.mean(axis=1, keepdims=True)
        weight = (1.0 - settings.lobes) + settings.lobes * numpy.divide(raw, mean, out=numpy.ones_like(raw), where=mean > 1e-12)
    return 1.0 + settings.flare_amount * decay[:, None] * weight


def root_factors(frame, settings):
    share = numpy.clip(1.0 - frame.along / max(settings.root_length, 1e-12), 0.0, 1.0)
    swell = 1.0 + settings.root_flare * share * share
    return numpy.repeat(swell[:, None], frame.segments, axis=1)


def polyline_distance(points, line):
    starts = line[:-1]
    span = line[1:] - starts
    square = numpy.maximum(numpy.einsum("ij,ij->i", span, span), 1e-24)
    offsets = points[:, None, :] - starts[None, :, :]
    share = numpy.clip(numpy.einsum("pij,ij->pi", offsets, span) / square[None, :], 0.0, 1.0)
    nearest = starts[None, :, :] + share[..., None] * span[None, :, :]
    return numpy.linalg.norm(nearest - points[:, None, :], axis=2).min(axis=1)


def collar_factors(frame, settings, skeleton, parent_frame):
    parent_radius = float(skeleton.radii[frame.axis.nodes[0]])
    own = float(frame.radii[0])
    distance = polyline_distance(frame.samples, parent_frame.samples)
    strength = settings.collar * max(0.0, 1.0 - own / max(parent_radius, 1e-12))
    swell = 1.0 + strength * (1.0 - smoothstep(parent_radius, parent_radius + own, distance))
    if own >= THICK_LATERAL * parent_radius:
        swell[0] *= START_SHRINK
    return numpy.repeat(swell[:, None], frame.segments, axis=1)


def root_directions(skeleton, axes):
    found = []
    reach = LOBE_REACH * float(skeleton.radii[0])
    for axis in axes:
        if is_base_root(axis):
            offsets = skeleton.positions[axis.nodes] - skeleton.positions[0]
            far = numpy.flatnonzero(numpy.linalg.norm(offsets, axis=1) >= reach)
            found.append((offsets[far[0] if len(far) else -1], float(skeleton.radii[axis.nodes[1]]) ** 2))
    total = sum(share for _, share in found)
    return [(direction / max(float(numpy.linalg.norm(direction)), 1e-12), share / total) for direction, share in found] if total > 0 else []


def radius_factors(frame, settings, skeleton, frames, directions):
    axis = frame.axis
    if axis.index == 0:
        return trunk_factors(frame, settings, directions)
    if is_base_root(axis):
        return root_factors(frame, settings)
    return collar_factors(frame, settings, skeleton, frames[axis.parent])
