"""Where every plant stands.

Where every plant of the woodland stands: trees by age class with competition spacing, shrubs, tall herbs and ferns
by the edge profiles, species by moisture and light. The plan is plain arrays, built before any plant is grown, so it is
measured and tested on its own."""
import numpy

from . import woodland_edges as edges
from .woodland_pattern import Inhibition, inhibit, poisson_rectangle, thomas
from .woodland_species import BUILT_SHARE, CLASSES, HEIGHT_SHARE, class_shares, crown_radius, pick_species
from .tree_presets import PRESETS

LAYERS = ("tree", "shrub", "herb", "fern")
TREE_CANDIDATES = 4.0
SHRUB_DENSITY = 0.07
HERB_DENSITY = 1.2
HERB_CLUMP = (8.0, 0.7)
FERN_DENSITY = 0.45
FERN_CLUMP = (6.0, 1.0)
FERN_MOISTURE = 0.6
HERB_HEIGHT = (0.7, 1.4)
FERN_HEIGHT = (0.5, 1.0)
YOUNG_LIGHT = 0.65
MATURE_LIGHT = 0.45


class Plants:
    """Columns of the plan, one row per plant."""

    FIELDS = ("xy", "layer", "species", "klass", "share", "radius", "height", "stand", "depth", "turn", "key")

    def __init__(self):
        self.rows = {field: [] for field in self.FIELDS}

    def add(self, **columns):
        count = len(columns["xy"])
        for field in self.FIELDS:
            value = columns[field]
            self.rows[field].append(numpy.broadcast_to(numpy.asarray(value), (count,) + numpy.asarray(value).shape[1:]) if numpy.ndim(value) == 0 else numpy.asarray(value))

    def arrays(self):
        result = {}
        for field in self.FIELDS:
            parts = [part for part in self.rows[field] if len(part)]
            if parts:
                result[field] = numpy.concatenate(parts)
            else:
                result[field] = numpy.zeros((0, 2)) if field == "xy" else numpy.zeros(0)
        return result


def class_of(name):
    return CLASSES.index(name)


def uniform_share(rng, klass, count):
    low, high = HEIGHT_SHARE[klass]
    return low + (high - low) * rng.random(count)


def place_trees(rng, footprint, kind, site, species, settings, grid, plants, stand):
    low, high = footprint.bounds(settings["edge"]["fringe"] + 2.0)
    edge = settings["edge"]
    table = edges.KINDS[kind]
    largest = max(crown_radius(name, HEIGHT_SHARE["mature"][1]) for name in species)
    packing = 1.0 / (numpy.pi * (table["spacing"] * largest) ** 2)
    counts = {}
    for klass, profile, spacing, light in (
        ("mature", lambda d: edges.mature_profile(d, edge, kind), table["spacing"], lambda d: MATURE_LIGHT + (1.0 - MATURE_LIGHT) * edges.edge_light(d)),
        ("young", lambda d: edges.young_profile(d, edge) * table["young"], edges.YOUNG_SPACING, lambda d: YOUNG_LIGHT * edges.edge_light(d) + (1.0 - YOUNG_LIGHT) * 0.3),
        ("sapling", lambda d: edges.sapling_profile(d, edge) * table["saplings"], edges.SAPLING_SPACING, lambda d: YOUNG_LIGHT * edges.edge_light(d) + (1.0 - YOUNG_LIGHT) * 0.3),
    ):
        candidates = poisson_rectangle(rng, low, high, TREE_CANDIDATES * packing * (1.0 if klass == "mature" else settings["q"] ** class_of(klass)))
        candidates, depth, moisture = thinned(rng, footprint, candidates, profile, site)
        picked = pick_species(species, light(depth), moisture, rng.random(len(candidates)))
        share = uniform_share(rng, klass, len(candidates))
        radii = numpy.array([crown_radius(species[index], value) for index, value in zip(picked, share)])
        if klass == "mature":
            chosen, _ = inhibit(candidates, radii, spacing, grid)
            counts["mature"] = len(chosen)
        else:
            target = int(round(counts["mature"] * settings["q"] ** class_of(klass) * (table["young"] if klass == "young" else table["saplings"])))
            chosen = limited(candidates, radii, spacing, grid, target)
        heights = share[chosen] * numpy.array([PRESETS[species[index]]["height"] for index in picked[chosen]]) if len(chosen) else numpy.zeros(0)
        plants.add(xy=candidates[chosen], layer=0, species=numpy.array([species[index] for index in picked[chosen]], dtype=object),
                   klass=class_of(klass), share=share[chosen], radius=radii[chosen], height=heights, stand=stand, depth=depth[chosen],
                   turn=rng.random(len(chosen)) * 2.0 * numpy.pi, key=rng.random(len(chosen)))
    return counts


def thinned(rng, footprint, points, profile, site):
    """Keep each point with the probability its depth's profile gives (independent thinning), then only where the
    ground carries plants; returns the points, their depths and their moisture."""
    depth = footprint.signed(points)
    keep = rng.random(len(points)) < profile(depth)
    points, depth = points[keep], depth[keep]
    values = site(points) if len(points) else {"ok": numpy.zeros(0, dtype=bool), "moisture": numpy.zeros(0)}
    return points[values["ok"]], depth[values["ok"]], values["moisture"][values["ok"]]


def limited(candidates, radii, spacing, grid, target):
    chosen = []
    if target <= 0:
        return numpy.array(chosen, dtype=numpy.int64)
    largest = float(numpy.max(radii)) if len(radii) else 1.0
    reach = spacing * (largest + max(grid.radii, default=largest))
    for index, (point, radius) in enumerate(zip(candidates.tolist(), radii.tolist())):
        if grid.clear_of(point, radius, spacing, reach):
            grid.add(point, radius)
            chosen.append(index)
            if len(chosen) == target:
                break
    return numpy.array(chosen, dtype=numpy.int64)


def place_shrubs(rng, footprint, kind, site, shrubs, settings, grid, plants, stand):
    edge = settings["edge"]
    table = edges.KINDS[kind]
    low, high = footprint.bounds(edge["fringe"] + 2.0)
    candidates = poisson_rectangle(rng, low, high, SHRUB_DENSITY * settings["shrub_density"] * table["shrubs"])
    candidates, depth, moisture = thinned(rng, footprint, candidates, lambda d: edges.shrub_profile(d, edge), site)
    picked = pick_species(shrubs, edges.edge_light(depth), moisture, rng.random(len(candidates)))
    share = uniform_share(rng, "shrub", len(candidates))
    radii = numpy.array([crown_radius(shrubs[index], value) for index, value in zip(picked, share)])
    spacing = edges.HEDGEROW_SHRUB_SPACING if kind == "hedgerow" else edges.SHRUB_SPACING
    chosen, _ = inhibit(candidates, radii, spacing, grid)
    heights = share[chosen] * numpy.array([PRESETS[shrubs[index]]["height"] for index in picked[chosen]]) if len(chosen) else numpy.zeros(0)
    plants.add(xy=candidates[chosen], layer=1, species=numpy.array([shrubs[index] for index in picked[chosen]], dtype=object), klass=len(CLASSES),
               share=share[chosen], radius=radii[chosen], height=heights, stand=stand, depth=depth[chosen],
               turn=rng.random(len(chosen)) * 2.0 * numpy.pi, key=rng.random(len(chosen)))
    return len(chosen)


def place_ground_layer(rng, footprint, kind, site, settings, plants, stand, layer):
    edge = settings["edge"]
    table = edges.KINDS[kind]
    low, high = footprint.bounds(edge["fringe"] + 2.0)
    density, (per_clump, sigma) = (HERB_DENSITY * table["herbs"], HERB_CLUMP) if layer == "herb" else (FERN_DENSITY * table["ferns"], FERN_CLUMP)
    density *= settings["understorey_density"]
    if density <= 0.0:
        return 0
    points = thomas(rng, low, high, density / per_clump, per_clump, sigma)
    profile = (lambda d: edges.herb_profile(d, edge)) if layer == "herb" else (lambda d: edges.fern_profile(d, edge))
    points, depth, moisture = thinned(rng, footprint, points, profile, site)
    if layer == "fern":
        damp = rng.random(len(points)) < 1.0 - FERN_MOISTURE + FERN_MOISTURE * moisture
        points, depth = points[damp], depth[damp]
    low_height, high_height = HERB_HEIGHT if layer == "herb" else FERN_HEIGHT
    heights = low_height + (high_height - low_height) * rng.random(len(points))
    plants.add(xy=points, layer=LAYERS.index(layer), species=layer, klass=len(CLASSES) + LAYERS.index(layer) - 1, share=1.0,
               radius=0.4 * heights, height=heights, stand=stand, depth=depth, turn=rng.random(len(points)) * 2.0 * numpy.pi, key=rng.random(len(points)))
    return len(points)


def plan_woodland(footprints, site, settings):
    """Every plant of every stand. footprints are (Footprint, species, shrubs); site maps plan points to ok, z and
    moisture arrays."""
    plants = Plants()
    trees = Inhibition(8.0)
    stems = Inhibition(4.0)
    stand_reports = []
    for index, (footprint, species, shrubs) in enumerate(footprints):
        rng = numpy.random.default_rng([settings["seed"], index])
        kind = footprint.kind
        before = len(trees.points)
        counts = place_trees(rng, footprint, kind, site, species, settings, trees, plants, index)
        for point in trees.points[before:]:
            stems.add(point, edges.STEM_CLEARANCE)
        counts["shrubs"] = place_shrubs(rng, footprint, kind, site, shrubs, settings, stems, plants, index) if settings["shrubs"] else 0
        counts["herbs"] = place_ground_layer(rng, footprint, kind, site, settings, plants, index, "herb") if settings["understorey"] else 0
        counts["ferns"] = place_ground_layer(rng, footprint, kind, site, settings, plants, index, "fern") if settings["understorey"] else 0
        stand_reports.append({"kind": kind, "area": round(float(footprint.area()), 1), "species": list(species), "shrubs": list(shrubs), "counts": counts})
    return plants.arrays(), stand_reports


def built_scale(klass_name, share):
    return share / BUILT_SHARE[klass_name]


def expected_class_shares(q):
    return {key: round(float(value), 4) for key, value in class_shares(q).items()}
