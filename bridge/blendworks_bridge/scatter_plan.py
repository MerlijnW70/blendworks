import math

import numpy

from .errors import bad_args
from .poisson import pair_clearance, thin_to_disks
from .scatter_frames import instance_matrices, instance_rotations
from .scatter_masks import mask_values
from .scatter_sizes import draw_sizes, fit_power_exponent, power_sizes, size_histogram

DARTS_PER_DISK = 64
POWER_FILL = 0.25
QUADRATURE_POINTS = 4096
DARTS_PER_INSTANCE_LIMIT = 40
MAX_POWER_RATIO = 32.0


class ScatterPlan:
    def __init__(self, points, normals, sizes, source_ids, matrices, report):
        self.points = points
        self.normals = normals
        self.sizes = sizes
        self.source_ids = source_ids
        self.matrices = matrices
        self.report = report


def mean_square_size(low, high, exponent):
    quantiles = (numpy.arange(QUADRATURE_POINTS) + 0.5) / QUADRATURE_POINTS
    return float(numpy.mean((power_sizes(quantiles, low, high, exponent) / low) ** 2))


def dart_count(area, radius, density, limit, power, fill):
    if power:
        wanted = math.ceil(POWER_FILL * area / (math.pi * radius * radius * fill))
        wanted = wanted if density is None else math.ceil(density * area)
    else:
        saturating = math.ceil(DARTS_PER_DISK * area / (math.pi * radius * radius))
        wanted = saturating if density is None else min(saturating, math.ceil(density * area))
    return max(1, min(wanted, DARTS_PER_INSTANCE_LIMIT * limit))


def check_sizes(args):
    low, high = args["scale_range"]
    if low > high:
        raise bad_args("scale_range must be [smallest, largest]")
    if args["scale_distribution"] == "power" and high / low > MAX_POWER_RATIO:
        raise bad_args(f"with power, the largest scale may be at most {MAX_POWER_RATIO:g} times the smallest")
    return low, high


def plan_scatter(surface, args, masks, weights, heights):
    low, high = check_sizes(args)
    power = args["scale_distribution"] == "power"
    limit = args["max_count"]
    if surface.area <= 0.0:
        raise bad_args("the target has no surface area to scatter on")
    base_radius = 0.5 * args["min_distance"]
    fill = mean_square_size(low, high, args["scale_exponent"]) if power else 1.0
    count = dart_count(surface.area, base_radius, args.get("density"), limit, power, fill)
    rng = numpy.random.default_rng([args["seed"], 0x5CA77E2])
    triangle, barycentric = surface.pick(rng.uniform(size=count), rng.uniform(size=count), rng.uniform(size=count))
    points = surface.positions(triangle, barycentric).astype(numpy.float32).astype(numpy.float64)
    coin = rng.uniform(size=count)
    sizes = draw_sizes(rng, count, args["scale_distribution"], (low, high), args["scale_exponent"])
    source_ids = numpy.searchsorted(numpy.cumsum(weights) / weights.sum(), rng.uniform(size=count), side="right").clip(0, len(weights) - 1)
    priority = rng.uniform(size=count)
    density = mask_values(surface, args, masks, triangle, barycentric, points)
    alive = numpy.nonzero(coin < density)[0]
    radii = base_radius * sizes / low if power else numpy.full(count, base_radius)
    order = alive[numpy.lexsort((alive, -sizes[alive]))] if power else alive
    kept = numpy.array(thin_to_disks(points, radii, order, None if power else limit), dtype=numpy.int64)
    if len(kept) > limit:
        kept = kept[numpy.argsort(priority[kept], kind="stable")[:limit]]
    kept = numpy.sort(kept)
    kept_points, kept_radii, kept_sizes = points[kept], radii[kept], sizes[kept]
    rotations = instance_rotations(surface.surface_normals(triangle[kept], barycentric[kept]), args, rng)
    offsets = -args["embed"] * heights[source_ids[kept]] * kept_sizes
    placed = kept_points + rotations[:, :, 2] * offsets[:, None]
    smallest, tightest = pair_clearance(kept_points, kept_radii)
    report = {
        "count": int(len(kept)),
        "surface_area": round(surface.area, 6),
        "candidates": int(count),
        "masked_out": round(float(1.0 - len(alive) / count), 6),
        "min_pair_distance": None if smallest is None else round(smallest, 9),
        "min_spacing_ratio": None if tightest is None else round(tightest, 9),
        "size_histogram": size_histogram(kept_sizes, low, high),
    }
    if power and len(kept) > 1 and high > low:
        report["fitted_exponent"] = round(fit_power_exponent(kept_sizes, low, high), 3)
    return ScatterPlan(kept_points, rotations[:, :, 2], kept_sizes, source_ids[kept], instance_matrices(placed, rotations, kept_sizes), report)
