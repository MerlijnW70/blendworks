"""Uplift fields and lithology bands for the fluvial model."""

import math

import numpy

UPLIFT_SHAPES = ("block", "range", "tilted", "dome", "array")


def cell_centres(shape, spacing):
    """World x and y of every cell, x along columns and y along rows, the grid's corner at the origin."""
    rows, columns = shape
    x = numpy.arange(columns, dtype=numpy.float64) * spacing[0]
    y = numpy.arange(rows, dtype=numpy.float64) * spacing[1]
    return numpy.meshgrid(x, y)


def resample(values, shape):
    """Bilinear resampling of a grid onto another number of rows and columns over the same extent."""
    values = numpy.asarray(values, dtype=numpy.float64)
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError(f"a field must be a 2-D grid of at least 2 x 2 values, got shape {values.shape}")
    if values.shape == tuple(shape):
        return values.copy()

    def axis(count, wanted):
        position = numpy.linspace(0.0, count - 1.0, wanted)
        index = numpy.minimum(numpy.floor(position).astype(numpy.int64), count - 2)
        return index, position - index

    rows, row_part = axis(values.shape[0], shape[0])
    columns, column_part = axis(values.shape[1], shape[1])
    across = values[rows] * (1.0 - row_part)[:, None] + values[rows + 1] * row_part[:, None]
    return across[:, columns] * (1.0 - column_part)[None, :] + across[:, columns + 1] * column_part[None, :]


def smooth_step(value):
    value = numpy.clip(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def base_distance(shape, spacing, edges):
    """Distance in metres from every cell to the nearest base level side (edges are the kernels' edge bits)."""
    from .fluvial_model import outlet_cells

    x, y = cell_centres(shape, spacing)
    far = numpy.full(shape, numpy.inf)
    sides = outlet_cells((3, 3), edges)
    for open_side, distance in ((sides[0, 1], y), (sides[2, 1], y.max() - y), (sides[1, 0], x), (sides[1, 2], x.max() - x)):
        if open_side:
            far = numpy.minimum(far, distance)
    return far


def strike_variation(shape, spacing, amount, seed, waves=4):
    """A smooth random factor 1 +- amount: a few seeded cosine waves with wavelengths from a third of the domain to
    the whole of it, for uplift that varies along the range."""
    x, y = cell_centres(shape, spacing)
    extent = max(x.max(), y.max(), 1.0)
    rng = numpy.random.default_rng(seed)
    total = numpy.zeros(shape)
    for _ in range(waves):
        wavelength = extent * rng.uniform(1.0 / 3.0, 1.0)
        angle, phase = rng.uniform(0.0, math.pi), rng.uniform(0.0, 2.0 * math.pi)
        total += numpy.cos(2.0 * math.pi * (x * math.cos(angle) + y * math.sin(angle)) / wavelength + phase)
    return 1.0 + amount * total / max(float(numpy.abs(total).max()), 1e-12)


def range_profile(distance, crest, behind):
    """Uplift across a range, 0 to 1: rising from the base level to the crest at the share crest of the farthest
    distance, then falling to the share behind at the far side."""
    share = distance / max(float(distance.max()), 1e-12)
    rising = smooth_step(share / crest)
    falling = 1.0 - (1.0 - behind) * smooth_step((share - crest) / max(1.0 - crest, 1e-12))
    return numpy.where(share <= crest, rising, falling)


def uplift_field(shape, spacing, rate, kind="block", axis_angle=0.0, width=None, margin=None, values=None, edges=None,
                 crest=0.6, behind=0.5, along=0.0, seed=0):
    """Rock uplift rate in m/yr for every cell.

    block: rate everywhere. range: with edges (the kernels' base level bits), a range whose crest line runs parallel
    to the base level at the share crest of the farthest distance from it: the rate rises from zero at the base
    level to the crest and falls to behind times the rate at the far side; without edges, a belt through the
    centre whose axis runs at axis_angle degrees from +x, falling to zero over its half width (default a third of
    the domain). along (0 to 1) varies the rate by up to that share along the range with smooth seeded waves. tilted: rate rising linearly
    from zero at the low side (the side the axis angle points away from) to rate at the far side. dome: rate
    at the centre falling to zero at radius width (default half the shorter side). array: values (m/yr,
    resampled to the grid). margin (metres, default none) tapers every shape to zero towards the grid edges, so
    the base level is not cut by a cliff."""
    if kind not in UPLIFT_SHAPES:
        raise ValueError(f"uplift shape must be one of {', '.join(UPLIFT_SHAPES)}, got {kind!r}")
    x, y = cell_centres(shape, spacing)
    extent = (x.max(), y.max())
    centre = (extent[0] / 2.0, extent[1] / 2.0)
    direction = (math.cos(math.radians(axis_angle)), math.sin(math.radians(axis_angle)))
    if kind == "block":
        field = numpy.full(shape, float(rate))
    elif kind == "range" and edges:
        field = rate * range_profile(base_distance(shape, spacing, edges), crest, behind)
    elif kind == "range":
        half = width if width is not None else min(extent) / 3.0
        across = numpy.abs(-(x - centre[0]) * direction[1] + (y - centre[1]) * direction[0])
        field = rate * smooth_step(1.0 - across / half)
    elif kind == "tilted":
        position = (x - centre[0]) * direction[0] + (y - centre[1]) * direction[1]
        span = numpy.ptp(position) or 1.0
        field = rate * (position - position.min()) / span
    elif kind == "dome":
        radius = width if width is not None else min(extent) / 2.0
        field = rate * smooth_step(1.0 - numpy.hypot(x - centre[0], y - centre[1]) / radius)
    else:
        if values is None:
            raise ValueError("uplift shape 'array' needs values")
        field = resample(values, shape)
        if not numpy.isfinite(field).all() or (field < 0.0).any():
            raise ValueError("uplift values must be finite and at least 0 m/yr")
    if along:
        field = field * strike_variation(shape, spacing, along, seed)
    if margin:
        edge = numpy.minimum.reduce([x, extent[0] - x, y, extent[1] - y])
        field = field * smooth_step(edge / margin)
    return field


def lithology_bands(shape, spacing, erodibility, factors, band_width, angle=0.0, offset=0.0):
    """An erodibility field of parallel bands of rock: band i (counted along the direction at angle degrees from
    +x, from offset metres) has erodibility times factors[i % len(factors)]. Harder rock (a factor below 1)
    makes ridges, softer rock valleys."""
    if band_width <= 0.0:
        raise ValueError(f"lithology band width must be above 0 m, got {band_width}")
    factors = numpy.asarray(factors, dtype=numpy.float64)
    if factors.size == 0 or not numpy.isfinite(factors).all() or (factors <= 0.0).any():
        raise ValueError("lithology factors must be finite and above 0")
    x, y = cell_centres(shape, spacing)
    along = x * math.cos(math.radians(angle)) + y * math.sin(math.radians(angle)) - offset
    band = numpy.floor(along / band_width).astype(numpy.int64) % factors.size
    return erodibility * factors[band]


def weak_belts(shape, spacing, edges, shares, width_share, wander=0.0, seed=0):
    """True along belts of weak rock that run along strike, parallel to the base level sides: each belt lies at
    a share of the farthest distance from the base level, width_share of it wide, its line wandering by up to
    wander of that distance with smooth seeded waves. Longitudinal valleys follow such belts (fault zones and
    weak formations, as the Rhone and Inn valleys do)."""
    distance = base_distance(shape, spacing, edges)
    share = distance / max(float(distance.max()), 1e-12)
    if wander:
        share = share + wander * (strike_variation(shape, spacing, 1.0, seed + 1) - 1.0)
    inside = numpy.zeros(shape, dtype=bool)
    for centre in shares:
        inside |= numpy.abs(share - centre) <= width_share / 2.0
    return inside


def value_noise(shape, spacing, shortest, seed, octaves=5):
    """Seeded multi-octave value noise in [0, 1]: random grids from the domain scale down to wavelengths of about
    shortest metres, each resampled bilinearly and weighted by its wavelength."""
    rng = numpy.random.default_rng(seed)
    extent = max(shape[0] * spacing[1], shape[1] * spacing[0])
    total = numpy.zeros(shape)
    weight = 0.0
    for octave in range(octaves):
        wavelength = max(shortest, extent / 2.0 ** (octave + 1))
        side = max(2, int(round(extent / wavelength)) + 1)
        total += wavelength * resample(rng.random((side, side)), shape)
        weight += wavelength
    total /= weight
    low, high = float(total.min()), float(total.max())
    return (total - low) / max(high - low, 1e-12)


def critical_angles(shape, spacing, low, high, seed, weak=None, shortest=240.0):
    """Critical hillslope angles in degrees between low and high from seeded multi-octave noise down to wavelengths
    of about shortest metres (talus and threshold slopes stand at 30-38 degrees and vary with the rock's fractures
    from slope to slope); weak rock takes the lower half of the range."""
    variation = value_noise(shape, spacing, shortest, seed + 2)
    angles = low + (high - low) * variation
    if weak is not None:
        angles = numpy.where(weak, low + (angles - low) / 2.0, angles)
    return angles
