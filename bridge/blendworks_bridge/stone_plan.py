"""Stone placement plan: size bands, spacing and matrices."""

import math

import numpy
from mathutils import Vector

from . import liquid_masks
from .errors import bad_args
from .poisson import thin_to_disks
from .scatter_frames import instance_matrices, instance_rotations
from .scatter_sizes import power_sizes

NOTE_11 = "How stones lie along a shore, by natural rules: Where. Stones come in groups, not in rows: fall from a bank, a bar left by a flood, a lee behind a boulder. The groups are a Thomas cluster process (Neyman and Scott 1958; Diggle, Statistical Analysis of Spatial Point Patterns, section 4): parents at random in the shore band, each with a Poisson number of stones at Gaussian offsets of sigma metres. Which size. Grain sizes of fluvial gravel are lognormal in the size (Krumbein 1936: normal on the phi scale, phi = -log2 of the size in mm) and neighbouring stones are alike (a flood sorts what it carries): each group has its own mean log size, the stones vary about it, and the two together give the stated lognormal. A power law (a few big, many small, as Enquist and Niklas 2001 for communities) is the alternative. How lying. A stone lies on its broadest side, tilted by what it rests on, and is partly sunk in the ground; in the shallows it stands partly under water. How worked. Waves and swash rework stones in the water and along the water line and rarely higher up, so the stones nearer the water have travelled and turned round: the share falls off exponentially with the height above the water line (a stated decay, WORKED_DISTANCE), and each group has its own history."
BAND_SAMPLES = 40_000
FOOTPRINT = 0.85
CLUSTER_HISTORY = 0.2
TRANSPORT_JITTER = 0.08
SNAP_ATTEMPTS = 8
DOWN = Vector((0.0, 0.0, -1.0))
SQRT2 = math.sqrt(2.0)
LOGNORMAL_SPAN = 4.0


def clark_evans(points, area):
    """Clark and Evans (1954) nearest-neighbour index of points in the plane over a region of the given area: the mean distance to
    the nearest other point over the mean 0.5 / sqrt(density) of a random pattern. Random is 1, clustered below it, regular
    (a lattice of stones, a string of pearls) above, up to 2.15."""
    count = len(points)
    if count < 2 or area <= 0.0:
        return None
    nearest = numpy.empty(count)
    for start in range(0, count, 512):
        gaps = numpy.linalg.norm(points[start:start + 512, None, :2] - points[None, :, :2], axis=2)
        rows = numpy.arange(len(gaps))
        gaps[rows, start + rows] = numpy.inf
        nearest[start:start + 512] = gaps.min(axis=1)
    return float(nearest.mean() / (0.5 / math.sqrt(count / area)))


def normal_cdf(values):
    """The standard normal distribution function."""
    return 0.5 * (1.0 + numpy.vectorize(math.erf)(values / SQRT2))


def sizes_from(z, low, high, distribution, exponent):
    """Sizes from standard normal scores: lognormal with the range spanning LOGNORMAL_SPAN standard deviations of the log, or a
    power law of the exponent between low and high."""
    if distribution == "power":
        return power_sizes(numpy.clip(normal_cdf(z), 1e-9, 1.0 - 1e-9), low, high, exponent)
    centre = 0.5 * (math.log(low) + math.log(high))
    spread = (math.log(high) - math.log(low)) / LOGNORMAL_SPAN
    return numpy.exp(numpy.clip(centre + spread * z, math.log(low), math.log(high)))


def band_sample(surface, corners, args, rng):
    """Random surface points with the shore mask at them: where parents may stand, and the area of the band seen from above (the
    nearest-neighbour index is a measure of the plan, so the plan area is its region)."""
    triangle, weights = surface.pick(rng.uniform(size=BAND_SAMPLES), rng.uniform(size=BAND_SAMPLES), rng.uniform(size=BAND_SAMPLES))
    shore = liquid_masks.mask(corners, surface, triangle, weights, "shore", args["shore_width"], depth=args["shore_depth"])
    flat = numpy.abs(surface.normals[triangle][:, 2])
    return surface.positions(triangle, weights), shore, surface.area * float(numpy.mean(flat * (shore > 0.0)))


def snap(ground, points):
    """The points moved onto the ground straight below the top of it, with its normals; those that miss are marked."""
    found = numpy.zeros(len(points), dtype=bool)
    placed = numpy.zeros((len(points), 3))
    normals = numpy.zeros((len(points), 3))
    top = ground.high[2] + 1.0
    for index, (x, y) in enumerate(points[:, :2].tolist()):
        hit = ground.tree.ray_cast(Vector((x, y, top)), DOWN)
        if hit[0] is not None:
            found[index] = True
            placed[index] = hit[0][:]
            normals[index] = hit[1][:]
    return found, placed, normals


def plan(surface, ground, water, corners, args, classes, rng):
    """Where the stones go: the groups, and for each stone its size, its place and how it lies, how deep it is sunk and how
    worked it is. Returns the arrays and a report."""
    candidates, shore, band_area = band_sample(surface, corners, args, rng)
    if band_area <= 0.0 or not (shore > 0.0).any():
        raise bad_args("there is no shore band: no ground lies within shore_width above or shore_depth under the water line")
    parents = max(1, int(rng.poisson(args["cluster_density"] * band_area)))
    allowed = numpy.nonzero(rng.uniform(size=len(candidates)) < shore)[0]
    if not len(allowed):
        raise bad_args("the shore band is too thin to place stones in; widen shore_width or shore_depth")
    chosen = rng.choice(allowed, size=min(parents, len(allowed)), replace=False)
    centres = candidates[chosen]
    counts = numpy.maximum(1, rng.poisson(args["per_cluster"], len(centres)))
    group = numpy.repeat(numpy.arange(len(centres)), counts)
    offsets = rng.normal(0.0, args["cluster_radius"], (len(group), 2))
    offsets[numpy.cumsum(counts) - counts] = 0.0
    points = centres[group].copy()
    points[:, :2] += offsets
    found, points, normals = snap(ground, points)
    group, points, normals = group[found], points[found], normals[found]
    reach = args["shore_width"] + 2.0
    dry = -water.signed_depth(points, reach)
    alive = rng.uniform(size=len(points)) < liquid_masks.band(dry, "shore", args["shore_width"], liquid_masks.WATERLINE_EDGE, args["shore_depth"])
    group, points, normals, dry = group[alive], points[alive], normals[alive], dry[alive]
    if len(points) == 0:
        raise bad_args("no stone fits in the shore band; raise cluster_density or per_cluster")
    sorting = args["sorting"]
    mean_score = rng.normal(size=len(centres))
    scores = math.sqrt(sorting) * mean_score[group] + math.sqrt(1.0 - sorting) * rng.normal(size=len(group))
    low, high = args["size_range"]
    sizes = sizes_from(scores, low, high, args["size_distribution"], args["size_exponent"])
    order = numpy.lexsort((numpy.arange(len(sizes)), -sizes))
    kept = numpy.sort(numpy.array(thin_to_disks(points, 0.5 * FOOTPRINT * sizes, order, args["max_count"]), dtype=numpy.int64))
    group, points, normals, dry, sizes = group[kept], points[kept], normals[kept], dry[kept], sizes[kept]
    history = rng.normal(0.0, CLUSTER_HISTORY, len(centres))[group]
    transport = numpy.clip(numpy.exp(-numpy.maximum(dry, 0.0) / args["worked_distance"]) + history + rng.normal(0.0, TRANSPORT_JITTER, len(group)), 0.0, 1.0)
    shape_class = numpy.rint(transport * (classes - 1)).astype(int)
    lean = {"align": "blend", "align_factor": args["settle"], "random_yaw": True, "tilt": args["tilt"]}
    rotations = instance_rotations(normals, lean, rng)
    burial = rng.uniform(args["burial"][0], args["burial"][1], len(points))
    return {
        "points": points, "normals": normals, "rotations": rotations, "sizes": sizes, "dry": dry, "burial": burial,
        "group": group, "transport": transport, "class": shape_class, "clusters": int(len(numpy.unique(group))), "band_area": band_area,
        "index": clark_evans(points, band_area),
    }


def matrices(layout, heights, picks):
    """World matrices of the stones: a variant of height heights[pick] (its longest side is one metre) at the size, sunk along
    its own axis by the burial share of its height."""
    sunk = layout["points"] - layout["rotations"][:, :, 2] * (layout["burial"] * heights[picks] * layout["sizes"])[:, None]
    return instance_matrices(sunk, layout["rotations"], layout["sizes"])
