"""Crown envelopes (revolution and mesh) and rejection sampling."""

import math

import numpy

from .errors import bad_args

SHAPES = ("conical", "spherical", "hemispherical", "cylindrical", "tapered_cylindrical", "flame", "inverse_conical", "tend_flame")
PROFILE_SAMPLES = 129
SAMPLE_BATCH = 4096
MAX_SAMPLE_ROUNDS = 400
RAY_DIRECTION = (0.2672612419124244, 0.5345224838248488, 0.8017837257372732)
PARITY_CELLS = 1_000_000


def shape_ratio(shape, ratio):
    ratio = numpy.clip(numpy.asarray(ratio, dtype=float), 0.0, 1.0)
    if shape == "conical":
        return 0.2 + 0.8 * ratio
    if shape == "spherical":
        return 0.2 + 0.8 * numpy.sin(math.pi * ratio)
    if shape == "hemispherical":
        return 0.2 + 0.8 * numpy.sin(0.5 * math.pi * ratio)
    if shape == "cylindrical":
        return numpy.ones_like(ratio)
    if shape == "tapered_cylindrical":
        return 0.5 + 0.5 * ratio
    if shape == "flame":
        return numpy.where(ratio <= 0.7, ratio / 0.7, (1.0 - ratio) / 0.3)
    if shape == "inverse_conical":
        return 1.0 - 0.8 * ratio
    if shape == "tend_flame":
        return numpy.where(ratio <= 0.7, 0.5 + 0.5 * ratio / 0.7, 0.5 + 0.5 * (1.0 - ratio) / 0.3)
    raise bad_args(f"unknown crown shape {shape}; use one of {', '.join(SHAPES)}")


def segment_distances(points, starts, ends):
    span = ends - starts
    lengths = numpy.maximum(numpy.einsum("ij,ij->i", span, span), 1e-300)
    offsets = points[:, None, :] - starts[None, :, :]
    along = numpy.clip(numpy.einsum("pij,ij->pi", offsets, span) / lengths, 0.0, 1.0)
    nearest = starts[None, :, :] + along[:, :, None] * span[None, :, :]
    return numpy.sqrt(((points[:, None, :] - nearest) ** 2).sum(axis=2)).min(axis=1)


class RevolutionEnvelope:
    def __init__(self, shape, bottom, top, radius, widest_at_top=False):
        if not top > bottom:
            raise bad_args("the envelope needs a top above its bottom")
        self.shape = shape
        self.bottom = float(bottom)
        self.top = float(top)
        self.radius = float(radius)
        heights = numpy.linspace(self.bottom, self.top, PROFILE_SAMPLES)
        ratio = (heights - self.bottom) / (self.top - self.bottom) if widest_at_top else (self.top - heights) / (self.top - self.bottom)
        self.heights = heights
        self.radii = self.radius * shape_ratio(shape, ratio)
        outline = numpy.column_stack([self.radii, heights])
        corners = numpy.vstack([[0.0, self.bottom], outline, [0.0, self.top]])
        self.starts = corners[:-1]
        self.ends = corners[1:]

    def describe(self):
        return {"shape": self.shape, "bottom": self.bottom, "top": self.top, "radius": self.radius}

    def profile_radius(self, heights):
        return numpy.interp(heights, self.heights, self.radii)

    def inside(self, points):
        points = numpy.atleast_2d(points)
        spread = numpy.hypot(points[:, 0], points[:, 1])
        within = (points[:, 2] >= self.bottom) & (points[:, 2] <= self.top)
        return within & (spread <= self.profile_radius(points[:, 2]))

    def outside_distance(self, points):
        points = numpy.atleast_2d(points)
        planar = numpy.column_stack([numpy.hypot(points[:, 0], points[:, 1]), points[:, 2]])
        distances = numpy.zeros(len(points))
        outside = ~self.inside(points)
        if outside.any():
            distances[outside] = segment_distances(planar[outside], self.starts, self.ends)
        return distances

    def bounds(self):
        reach = float(self.radii.max())
        return numpy.array([-reach, -reach, self.bottom]), numpy.array([reach, reach, self.top])

    def sample(self, rng, count):
        return rejection_sample(self, rng, count)


class MeshEnvelope:
    def __init__(self, name, triangles):
        if len(triangles) == 0:
            raise bad_args(f"the envelope {name} has no faces")
        self.name = name
        vertices = triangles.reshape(-1, 3)
        self.origins = triangles[:, 0, :]
        self.edge_one = triangles[:, 1, :] - triangles[:, 0, :]
        self.edge_two = triangles[:, 2, :] - triangles[:, 0, :]
        self.edge_starts = triangles.reshape(-1, 3)
        self.edge_ends = triangles[:, [1, 2, 0], :].reshape(-1, 3)
        normals = numpy.cross(self.edge_one, self.edge_two)
        lengths = numpy.linalg.norm(normals, axis=1)
        self.normals = numpy.divide(normals, lengths[:, None], out=numpy.zeros_like(normals), where=lengths[:, None] > 1e-15)
        self.dot_one = numpy.einsum("tk,tk->t", self.edge_one, self.edge_one)
        self.dot_cross = numpy.einsum("tk,tk->t", self.edge_one, self.edge_two)
        self.dot_two = numpy.einsum("tk,tk->t", self.edge_two, self.edge_two)
        gram = self.dot_one * self.dot_two - self.dot_cross**2
        self.solid = gram > 1e-30
        self.gram_inverse = numpy.divide(1.0, gram, out=numpy.zeros_like(gram), where=self.solid)
        self.pvec = numpy.cross(numpy.array(RAY_DIRECTION), self.edge_two)
        determinant = numpy.einsum("tk,tk->t", self.edge_one, self.pvec)
        self.usable = numpy.abs(determinant) > 1e-15
        self.inverse = numpy.divide(1.0, determinant, out=numpy.zeros_like(determinant), where=self.usable)
        self.low = vertices.min(axis=0)
        self.high = vertices.max(axis=0)
        if numpy.any(self.high - self.low <= 0.0):
            raise bad_args(f"the envelope {name} is flat; it must enclose a volume")

    def describe(self):
        return {"mesh": self.name, "bottom": float(self.low[2]), "top": float(self.high[2])}

    def crossings(self, points):
        direction = numpy.array(RAY_DIRECTION)
        counts = numpy.zeros(len(points), dtype=numpy.int64)
        block = max(1, PARITY_CELLS // len(self.origins))
        for start in range(0, len(points), block):
            offsets = points[start : start + block, None, :] - self.origins[None, :, :]
            first = numpy.einsum("ptk,tk->pt", offsets, self.pvec) * self.inverse
            cross = numpy.cross(offsets, self.edge_one[None, :, :])
            second = numpy.einsum("ptk,k->pt", cross, direction) * self.inverse
            distance = numpy.einsum("ptk,tk->pt", cross, self.edge_two) * self.inverse
            hit = (first >= 0.0) & (second >= 0.0) & (first + second <= 1.0) & (distance > 0.0) & self.usable
            counts[start : start + block] = hit.sum(axis=1)
        return counts

    def inside(self, points):
        points = numpy.atleast_2d(points)
        boxed = numpy.all((points >= self.low) & (points <= self.high), axis=1)
        result = numpy.zeros(len(points), dtype=bool)
        if boxed.any():
            result[boxed] = self.crossings(points[boxed]) % 2 == 1
        return result

    def outside_distance(self, points):
        points = numpy.atleast_2d(points)
        inside = self.inside(points)
        distances = numpy.zeros(len(points))
        outside = numpy.flatnonzero(~inside)
        if len(outside):
            distances[outside] = numpy.minimum(segment_distances(points[outside], self.edge_starts, self.edge_ends), self.face_distances(points[outside]))
        return distances

    def face_distances(self, points):
        offsets = points[:, None, :] - self.origins[None, :, :]
        height = numpy.abs(numpy.einsum("ptk,tk->pt", offsets, self.normals))
        along_one = numpy.einsum("ptk,tk->pt", offsets, self.edge_one)
        along_two = numpy.einsum("ptk,tk->pt", offsets, self.edge_two)
        first = (self.dot_two * along_one - self.dot_cross * along_two) * self.gram_inverse
        second = (self.dot_one * along_two - self.dot_cross * along_one) * self.gram_inverse
        over = (first >= 0.0) & (second >= 0.0) & (first + second <= 1.0) & self.solid
        return numpy.where(over, height, numpy.inf).min(axis=1)

    def bounds(self):
        return self.low.copy(), self.high.copy()

    def sample(self, rng, count):
        return rejection_sample(self, rng, count)


def rejection_sample(envelope, rng, count):
    low, high = envelope.bounds()
    kept = []
    total = 0
    for _ in range(MAX_SAMPLE_ROUNDS):
        candidates = low + rng.random((SAMPLE_BATCH, 3)) * (high - low)
        inside = candidates[envelope.inside(candidates)]
        kept.append(inside)
        total += len(inside)
        if total >= count:
            return numpy.vstack(kept)[:count]
    raise bad_args("the envelope encloses too little of its bounding box to place the attraction points; close the mesh or use a built-in shape")


def canonical_order(points):
    points = numpy.asarray(points, dtype=float).reshape(-1, 3)
    order = numpy.lexsort((points[:, 2], points[:, 1], points[:, 0]))
    return points[order]
