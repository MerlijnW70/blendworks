"""Ground cover planning: drawing candidates, budgets and populations of placed instances."""

import math

import numpy
from mathutils import Vector

from .cover_masks import expensive_masks, population_masks, view_mask
from .cover_sampling import clumped_candidates, expected_count, uniform_candidates
from .scatter_frames import instance_rotations

CANDIDATE_FLOOR = 200_000
CANDIDATE_CEILING = 8_000_000
SEARCH_STEPS = 48
SMALLEST_COSINE = 0.2
BEND_CHECK = 0.0005
RIM_CHUNK = 20_000


class Draw:
    def __init__(self, candidates, uniforms, distances, masks, drawn):
        self.candidates = candidates
        self.uniforms = uniforms
        self.distances = distances
        self.masks = masks
        self.drawn = drawn

    def accepted(self, view, factor):
        return self.uniforms * self.candidates.bound < view.falloff(self.distances, factor) * self.masks


def candidate_limit(budget):
    return min(CANDIDATE_CEILING, max(3 * budget, CANDIDATE_FLOOR))


def drawing_factor(surface, populations, view, budget):
    def expected(factor):
        return sum(expected_count(surface, view, factor, population["density"]) for population in populations)

    limit = candidate_limit(budget)
    if expected(1.0) <= limit:
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(SEARCH_STEPS):
        middle = 0.5 * (low + high)
        if expected(middle) <= limit:
            low = middle
        else:
            high = middle
    return low


def draw_population(surface, tree, population, index, view, factor, seed, context):
    rng = numpy.random.default_rng([seed, index, 0x6C0E7])
    if "clumping" in population:
        candidates = clumped_candidates(surface, tree, rng, population["density"], population["clumping"], view, factor)
    else:
        candidates = uniform_candidates(surface, rng, population["density"], view, factor)
    drawn = len(candidates)
    uniforms = rng.uniform(size=drawn)
    distances = view.distances(candidates.points)
    open_now = uniforms * candidates.bound < view.falloff(distances, factor)
    keep = numpy.nonzero(open_now)[0]
    candidates, uniforms, distances = candidates.subset(keep), uniforms[keep], distances[keep]
    masks = population_masks(surface, population, candidates, context)
    if context["view_only"]:
        masks *= numpy.max([view_mask(candidates.points, camera, context["scene"], context["view_margin"]) for camera in context["cameras"]], axis=0)
    masks = numpy.where(uniforms * candidates.bound < view.falloff(distances, factor) * masks, masks, 0.0)
    masks = expensive_masks(population, candidates.points, context, masks)
    keep = numpy.nonzero(masks > 0.0)[0]
    return Draw(candidates.subset(keep), uniforms[keep], distances[keep], masks[keep], drawn)


def budget_factor(draws, view, start, budget):
    def total(factor):
        return sum(int(draw.accepted(view, factor).sum()) for draw in draws)

    if total(start) <= budget:
        return start
    low, high = 0.0, start
    for _ in range(SEARCH_STEPS):
        middle = 0.5 * (low + high)
        if total(middle) <= budget:
            low = middle
        else:
            high = middle
    return low


class Placed:
    def __init__(self, positions, matrices, pick, card, tint, key, footprint, triangle, distances, cards):
        self.positions = positions
        self.matrices = matrices
        self.pick = pick
        self.card = card
        self.tint = tint
        self.key = key
        self.footprint = footprint
        self.triangle = triangle
        self.distances = distances
        self.cards = cards

    def __len__(self):
        return len(self.positions)


def rim_lift(tree, points, rotations, stretch, bases):
    lifts = numpy.zeros(len(points))
    for start in range(0, len(points), RIM_CHUNK):
        part = slice(start, start + RIM_CHUNK)
        lifts[part] = rim_lift_chunk(tree, points[part], rotations[part], stretch[part], bases[part])
    return lifts


def rim_lift_chunk(tree, points, rotations, stretch, bases):
    count = len(points)
    offsets = numpy.einsum("nkj,nij->nki", bases * stretch[:, None, :], rotations)
    reach = 2.0 * numpy.linalg.norm(offsets, axis=2).max(axis=1) + 0.05
    axes = rotations[:, :, 2]
    rims = points[:, None, :] + offsets
    origins = (rims + (axes * reach[:, None])[:, None, :]).reshape(-1, 3).tolist()
    downs = numpy.repeat(-axes, offsets.shape[1], axis=0).tolist()
    lengths = numpy.repeat(2.0 * reach, offsets.shape[1]).tolist()
    hits = numpy.full((len(origins), 3), numpy.nan)
    for index, (origin, down, length) in enumerate(zip(origins, downs, lengths)):
        hit, _, _, _ = tree.ray_cast(origin, down, length)
        if hit is not None:
            hits[index] = hit[:]
    gaps = numpy.einsum("nki,ni->nk", rims - hits.reshape(count, -1, 3), axes)
    return numpy.maximum(numpy.nan_to_num(gaps, nan=0.0).max(axis=1), 0.0)


def surface_creases(surface):
    cached = getattr(surface, "creases", None)
    if cached is not None:
        return cached
    count = len(surface.areas)
    edges = numpy.concatenate([numpy.sort(surface.vertex_ids[:, [first, second]], axis=1) for first, second in ((0, 1), (1, 2), (2, 0))])
    owners = numpy.tile(numpy.arange(count), 3)
    order = numpy.lexsort((edges[:, 1], edges[:, 0]))
    edges, owners = edges[order], owners[order]
    shared = numpy.nonzero(numpy.all(edges[1:] == edges[:-1], axis=1))[0]
    first, second = owners[shared], owners[shared + 1]
    turn = numpy.arccos(numpy.clip(numpy.einsum("ij,ij->i", surface.normals[first], surface.normals[second]), -1.0, 1.0))
    creases = numpy.zeros(count)
    numpy.maximum.at(creases, first, turn)
    numpy.maximum.at(creases, second, turn)
    widened = creases.copy()
    numpy.maximum.at(widened, first, creases[second])
    numpy.maximum.at(widened, second, creases[first])
    surface.creases = widened
    return widened


def chosen_forms(population, distances, view):
    if population["form"] == "geometry":
        return numpy.zeros(len(distances), dtype=bool)
    if population["form"] == "cards":
        return numpy.ones(len(distances), dtype=bool)
    if view.origin is None:
        return numpy.zeros(len(distances), dtype=bool)
    return distances > population["card_distance"]


def place_population(surface, tree, draw, population, index, view, factor, seed, elements):
    rng = numpy.random.default_rng([seed, index, 0x91ACE])
    accepted = numpy.nonzero(draw.accepted(view, factor))[0]
    candidates = draw.candidates.subset(accepted)
    distances = draw.distances[accepted]
    falloff = numpy.maximum(view.falloff(distances, factor), 1e-6)
    count = len(accepted)
    faces = surface.normals[candidates.triangle]
    rotations = instance_rotations(faces, {"align": "blend", "align_factor": population["align"], "tilt": population["tilt"], "random_yaw": True}, rng)
    low, high = population["scale_range"]
    scales = rng.uniform(low, high, count)
    widen = numpy.minimum(population["max_widen"], falloff ** -0.5) if population["widen"] else numpy.ones(count)
    variants = elements.variants
    variant = rng.integers(0, variants, count)
    cards = chosen_forms(population, distances, view)
    card_index = variant + (variants if elements.has_both else 0)
    pick = numpy.where(cards & elements.has_both, card_index, variant)
    radius = elements.base_radius[pick] * scales * widen
    axes = rotations[:, :, 2]
    cosine = numpy.clip(numpy.einsum("ij,ij->i", axes, faces), SMALLEST_COSINE, 1.0)
    sine = numpy.sqrt(1.0 - cosine * cosine)
    embed = population["embed"] * scales * elements.embedded[pick]
    sink = (embed + radius * sine) / cosine
    bend = surface_creases(surface)[candidates.triangle] * radius
    curved = numpy.nonzero(bend > BEND_CHECK)[0]
    if len(curved):
        stretch = numpy.stack([scales * widen, scales * widen, scales], axis=1)[curved]
        lift = rim_lift(tree, candidates.points[curved], rotations[curved], stretch, elements.padded_bases[pick[curved]])
        sink[curved] = embed[curved] + lift
    positions = candidates.points - axes * sink[:, None]
    matrices = numpy.zeros((count, 4, 4), dtype=numpy.float32)
    matrices[:, :3, :3] = rotations * numpy.stack([scales * widen, scales * widen, scales], axis=1)[:, None, :]
    matrices[:, :3, 3] = positions
    matrices[:, 3, 3] = 1.0
    tint = rng.uniform(-1.0, 1.0, count) * population["color_variation"]
    key = rng.uniform(size=count)
    footprint = elements.footprint[pick] * scales**2 / falloff
    return Placed(positions, matrices, pick.astype(numpy.int32), card_index.astype(numpy.int32), tint, key, footprint, candidates.triangle, distances, cards)


def population_report(population, draw, placed, view, factor, surface_area):
    report = {
        "name": population["name"],
        "element": population["element"],
        "count": len(placed),
        "density": population["density"],
        "candidates": int(draw.drawn),
        "mean_density": round(len(placed) / surface_area, 6) if surface_area > 0 else 0.0,
        "card_share": round(float(placed.cards.mean()), 6) if len(placed) else 0.0,
    }
    if view.origin is not None:
        report["near"] = round(factor * view.near, 6)
        report["farthest"] = round(float(placed.distances.max()), 6) if len(placed) else 0.0
    return report


def plan_cover(surface, tree, populations, view, budget, seed, context, elements):
    start = drawing_factor(surface, populations, view, budget)
    draws = [draw_population(surface, tree, population, index, view, start, seed, context) for index, population in enumerate(populations)]
    factor = budget_factor(draws, view, start, budget)
    placed = [place_population(surface, tree, draw, population, index, view, factor, seed, elements[population["name"]]) for index, (draw, population) in enumerate(zip(draws, populations))]
    reports = [population_report(population, draw, item, view, factor, surface.area) for population, draw, item in zip(populations, draws, placed)]
    return placed, reports, factor, start


def scale_note(factor):
    return None if math.isclose(factor, 1.0) else round(factor, 6)
