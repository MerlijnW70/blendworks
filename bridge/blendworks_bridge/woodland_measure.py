"""Measures of a woodland plan.

Measures of a woodland plan: regularity of the mature stems inside each stand, clustering of all stems at the stand
scale, the share of each age class, and the edge profile (density and mean height of each layer against the signed
distance to the rim)."""
import math

import numpy

from .woodland_pattern import besag_l, nearest_distances, quadrat_dispersion
from .woodland_species import CLASSES

PROFILE_STEP = 2.0
AREA_SAMPLES = 40_000
LAYER_NAMES = {0: "mature", 1: "young", 2: "sapling", 3: "shrubs", 4: "herbs", 5: "ferns"}


def interior_regularity(plants, footprint, stand, depth_from, seed):
    """Clark and Evans' R of the mature stems at least depth_from inside the rim, against all mature stems as
    neighbours, so the rim adds no edge effect; the intensity is that of the interior, measured by sampling its area."""
    mature = (plants["klass"] == 0) & (plants["stand"] == stand)
    inner = mature & (plants["depth"] >= depth_from)
    if inner.sum() < 5:
        return None
    rng = numpy.random.default_rng(seed)
    low, high = footprint.bounds(0.0)
    samples = low + rng.random((AREA_SAMPLES, 2)) * (high - low)
    area = float(numpy.prod(high - low)) * float((footprint.signed(samples) >= depth_from).mean())
    if area <= 0.0:
        return None
    every = plants["xy"][mature]
    distances = []
    for point in plants["xy"][inner]:
        gaps = numpy.linalg.norm(every - point, axis=1)
        gaps = gaps[gaps > 1e-9]
        distances.append(float(gaps.min()) if len(gaps) else 0.0)
    intensity = inner.sum() / area
    return round(float(numpy.mean(distances)) / (0.5 / math.sqrt(intensity)), 4)


def clustering(points, radii, side):
    if len(points) < 3:
        return {"l_minus_r": [None for _ in radii], "radii": list(radii), "dispersion": None, "quadrat": side}
    low, high = points.min(axis=0) - 1.0, points.max(axis=0) + 1.0
    return {"radii": [round(float(value), 2) for value in radii], "l_minus_r": besag_l(points, low, high, radii),
            "dispersion": round(quadrat_dispersion(points, low, high, side) or 0.0, 4), "quadrat": side}


def class_counts(plants):
    trees = plants["layer"] == 0
    counts = {name: int((plants["klass"][trees] == index).sum()) for index, name in enumerate(CLASSES)}
    total = max(sum(counts.values()), 1)
    return counts, {name: round(count / total, 4) for name, count in counts.items()}


def edge_profile(plants, footprints, edge, seed):
    """Density per square metre and mean height of each layer in bands of PROFILE_STEP metres of depth, over every
    stand; each band's area is measured by sampling the stands' bounds."""
    start = -edge["fringe"] - 6.0
    stop = edge["mantle"] + edge["transition"] + 10.0
    bands = numpy.arange(start, stop + 1e-9, PROFILE_STEP)
    areas = numpy.zeros(len(bands) - 1)
    rng = numpy.random.default_rng(seed)
    for footprint, _, _ in footprints:
        low, high = footprint.bounds(-start)
        samples = low + rng.random((AREA_SAMPLES, 2)) * (high - low)
        depth = footprint.signed(samples)
        counts, _ = numpy.histogram(depth, bands)
        areas += counts * float(numpy.prod(high - low)) / AREA_SAMPLES
    result = {"depth": [round(float(0.5 * (a + b)), 2) for a, b in zip(bands[:-1], bands[1:])], "area": [round(float(value), 1) for value in areas]}
    tall = numpy.zeros(len(areas))
    weight = numpy.zeros(len(areas))
    for klass, name in LAYER_NAMES.items():
        chosen = plants["klass"] == klass
        counts, _ = numpy.histogram(plants["depth"][chosen], bands)
        result[name] = [round(float(count / area), 5) if area > 0 else 0.0 for count, area in zip(counts, areas)]
        heights, _ = numpy.histogram(plants["depth"][chosen], bands, weights=plants["height"][chosen])
        tall += heights
        weight += counts
    result["mean_height"] = [round(float(total / count), 3) if count else 0.0 for total, count in zip(tall, weight)]
    return result


def measured(plants, footprints, edge, seed):
    report = {"stands": []}
    for index, (footprint, _, _) in enumerate(footprints):
        report["stands"].append({"regularity": interior_regularity(plants, footprint, index, edge["mantle"], seed + index)})
    stems = plants["xy"][plants["layer"] == 0]
    spacing = float(nearest_distances(stems).mean()) if len(stems) > 1 else 1.0
    report["clustering"] = clustering(stems, [0.5 * spacing, 4.0 * spacing, 10.0 * spacing], 6.0 * spacing)
    report["classes"], report["class_shares"] = class_counts(plants)
    report["edge_profile"] = edge_profile(plants, footprints, edge, seed)
    return report
