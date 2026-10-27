import math

import numpy

from .errors import bad_args

DISTRIBUTIONS = ("uniform", "lognormal", "power")
HISTOGRAM_BINS = 8
LOGNORMAL_SPAN = 4.0


def power_sizes(uniform, low, high, exponent):
    if high <= low:
        return numpy.full(len(uniform), low)
    if abs(exponent + 1.0) < 1e-9:
        return low * (high / low) ** uniform
    shift = exponent + 1.0
    return (low**shift + uniform * (high**shift - low**shift)) ** (1.0 / shift)


def lognormal_sizes(rng, count, low, high):
    if high <= low:
        return numpy.full(count, low)
    centre = 0.5 * (math.log(low) + math.log(high))
    spread = (math.log(high) - math.log(low)) / LOGNORMAL_SPAN
    values = rng.normal(centre, spread, count)
    outside = (values < math.log(low)) | (values > math.log(high))
    while outside.any():
        values[outside] = rng.normal(centre, spread, int(outside.sum()))
        outside = (values < math.log(low)) | (values > math.log(high))
    return numpy.exp(values)


def draw_sizes(rng, count, distribution, scale_range, exponent):
    low, high = scale_range
    if low > high:
        raise bad_args("scale_range must be [smallest, largest]")
    if distribution == "uniform":
        return rng.uniform(low, high, count)
    if distribution == "lognormal":
        return lognormal_sizes(rng, count, low, high)
    return power_sizes(rng.uniform(0.0, 1.0, count), low, high, exponent)


def fit_power_exponent(sizes, low, high):
    logs = numpy.log(sizes)
    mean_log = float(logs.mean())

    def expected_log(exponent):
        shift = exponent + 1.0
        if abs(shift) < 1e-9:
            return 0.5 * (math.log(low) + math.log(high))
        top, bottom = high**shift, low**shift
        return (top * math.log(high) - bottom * math.log(low)) / (top - bottom) - 1.0 / shift

    left, right = -12.0, 8.0
    for _ in range(80):
        middle = 0.5 * (left + right)
        if expected_log(middle) < mean_log:
            left = middle
        else:
            right = middle
    return 0.5 * (left + right)


def size_histogram(sizes, low, high):
    if len(sizes) == 0:
        return []
    if high <= low:
        return [{"from": round(low, 6), "to": round(high, 6), "count": int(len(sizes))}]
    edges = numpy.geomspace(low, high, HISTOGRAM_BINS + 1)
    counts, _ = numpy.histogram(sizes, bins=edges)
    return [{"from": round(float(edges[index]), 6), "to": round(float(edges[index + 1]), 6), "count": int(counts[index])} for index in range(HISTOGRAM_BINS)]
