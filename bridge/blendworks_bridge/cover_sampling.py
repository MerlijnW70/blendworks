"""Ground cover sampling: view, candidate points, usable areas and barycentric draws."""

import math

import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .scatter_surface import DEGENERATE_AREA

CLUMP_REACH = 4.0
SNAP_SIDEWAYS = 0.5
MAX_RELIEF = 3.0


class View:
    def __init__(self, origins, near, far):
        self.origins = None if origins is None else numpy.asarray(origins, dtype=float).reshape(-1, 3)
        self.origin = None if origins is None else self.origins[0]
        self.near = near
        self.far = far

    def distances(self, points):
        if self.origin is None:
            return numpy.zeros(len(points))
        return numpy.min([numpy.linalg.norm(points - origin, axis=1) for origin in self.origins], axis=0)

    def falloff(self, distances, factor):
        if self.origin is None:
            return numpy.full(len(distances), factor)
        reach = factor * self.near
        values = numpy.minimum(1.0, (reach / numpy.maximum(distances, 1e-9)) ** 2)
        if self.far is not None:
            values = numpy.where(distances > self.far, 0.0, values)
        return values


class Candidates:
    def __init__(self, points, triangle, weights, bound):
        self.points = points
        self.triangle = triangle
        self.weights = weights
        self.bound = bound

    def __len__(self):
        return len(self.points)

    def subset(self, keep):
        return Candidates(self.points[keep], self.triangle[keep], self.weights[keep], self.bound[keep])


def triangle_reach(surface, view, factor, margin=0.0):
    if view.origin is None:
        return numpy.full(len(surface.areas), factor)
    centres = surface.corners.mean(axis=1)
    spans = numpy.linalg.norm(surface.corners - centres[:, None, :], axis=2).max(axis=1)
    nearest = numpy.maximum(0.0, view.distances(centres) - spans - margin)
    return view.falloff(nearest, factor)


def usable_areas(surface):
    return numpy.where(surface.areas > DEGENERATE_AREA, surface.areas, 0.0)


def expected_count(surface, view, factor, density, margin=0.0, share=None):
    """Elements expected at the bound: density times area times the falloff, and times share, an upper bound of the
    population's masks per triangle, when one is known."""
    weights = usable_areas(surface) * triangle_reach(surface, view, factor, margin)
    if share is not None:
        weights = weights * share
    return float(density * numpy.sum(weights))


def barycentric_draws(rng, count):
    root = numpy.sqrt(rng.uniform(size=count))
    second = rng.uniform(size=count)
    return numpy.column_stack([1.0 - root, root * (1.0 - second), root * second])


def weighted_triangles(rng, weights, count):
    cumulative = numpy.cumsum(weights)
    picks = numpy.searchsorted(cumulative, rng.uniform(size=count) * cumulative[-1], side="right")
    return numpy.minimum(picks, len(weights) - 1)


def uniform_candidates(surface, rng, density, view, factor, share=None):
    reach = triangle_reach(surface, view, factor)
    if share is not None:
        reach = reach * share
    expected = density * usable_areas(surface) * reach
    total = float(expected.sum())
    count = int(rng.poisson(total)) if total > 0 else 0
    if count == 0:
        return empty_candidates()
    triangle = weighted_triangles(rng, expected, count)
    weights = barycentric_draws(rng, count)
    return Candidates(surface.positions(triangle, weights), triangle, weights, reach[triangle])


def empty_candidates():
    return Candidates(numpy.zeros((0, 3)), numpy.zeros(0, dtype=numpy.int64), numpy.zeros((0, 3)), numpy.zeros(0))


def surface_tree(surface):
    corners = surface.corners.reshape(-1, 3)
    faces = numpy.arange(len(corners)).reshape(-1, 3)
    return BVHTree.FromPolygons([Vector(point) for point in corners.tolist()], faces.tolist())


def tangent_frames(normals):
    other = numpy.where((numpy.abs(normals[:, 0]) < 0.9)[:, None], numpy.array([1.0, 0.0, 0.0]), numpy.array([0.0, 1.0, 0.0]))
    first = other - normals * numpy.einsum("ij,ij->i", other, normals)[:, None]
    first /= numpy.linalg.norm(first, axis=1)[:, None]
    return first, numpy.cross(normals, first)


def barycentric_of(points, corners):
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    v0, v1, v2 = b - a, c - a, points - a
    d00 = numpy.einsum("ij,ij->i", v0, v0)
    d01 = numpy.einsum("ij,ij->i", v0, v1)
    d11 = numpy.einsum("ij,ij->i", v1, v1)
    d20 = numpy.einsum("ij,ij->i", v2, v0)
    d21 = numpy.einsum("ij,ij->i", v2, v1)
    denominator = numpy.where(numpy.abs(d00 * d11 - d01 * d01) > 1e-30, d00 * d11 - d01 * d01, 1e-30)
    second = (d11 * d20 - d01 * d21) / denominator
    third = (d00 * d21 - d01 * d20) / denominator
    weights = numpy.column_stack([1.0 - second - third, second, third])
    weights = numpy.clip(weights, 0.0, 1.0)
    return weights / weights.sum(axis=1)[:, None]


def clumped_candidates(surface, tree, rng, density, clumping, view, factor):
    sigma = 0.5 * clumping["radius"]
    per_clump = clumping["per_clump"]
    reach = triangle_reach(surface, view, factor, CLUMP_REACH * sigma)
    expected = density / per_clump * usable_areas(surface) * reach
    total = float(expected.sum())
    parents = int(rng.poisson(total)) if total > 0 else 0
    if parents == 0:
        return empty_candidates()
    triangle = weighted_triangles(rng, expected, parents)
    centres = surface.positions(triangle, barycentric_draws(rng, parents))
    sizes = rng.poisson(per_clump, parents)
    owner = numpy.repeat(numpy.arange(parents), sizes)
    first, second = tangent_frames(surface.normals[triangle[owner]])
    offsets = rng.normal(0.0, sigma, (len(owner), 2))
    wanted = centres[owner] + first * offsets[:, :1] + second * offsets[:, 1:]
    found = numpy.zeros((len(wanted), 3))
    faces = numpy.full(len(wanted), -1, dtype=numpy.int64)
    for index, point in enumerate(wanted.tolist()):
        location, _, face, _ = tree.find_nearest(point)
        if location is not None:
            found[index] = location[:]
            faces[index] = face
    away = wanted - found
    normals = surface.normals[triangle[owner]]
    relief = numpy.einsum("ij,ij->i", away, normals)
    sideways = numpy.linalg.norm(away - normals * relief[:, None], axis=1)
    keep = numpy.nonzero((faces >= 0) & (sideways <= SNAP_SIDEWAYS * sigma + 1e-4) & (numpy.abs(relief) <= MAX_RELIEF * sigma + 1e-4))[0]
    if not len(keep):
        return empty_candidates()
    points, triangles = found[keep], faces[keep]
    weights = barycentric_of(points, surface.corners[triangles])
    return Candidates(surface.positions(triangles, weights), triangles, weights, reach[triangle[owner[keep]]])


def clump_share(clumping):
    sigma = 0.5 * clumping["radius"]
    return 1.0 / (2.0 * math.pi * sigma * sigma)
