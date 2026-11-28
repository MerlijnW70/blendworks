"""Python reference of thermal slides: slope-limited mass transfer with a critical angle per cell."""

import numpy

from .terrain_grid import INTERIOR, OPPOSITE


def check_settings(heights, tangent, rate, iterations):
    valid = numpy.isfinite(heights)
    if not (numpy.isfinite(rate) and 0.0 < rate <= 1.0):
        raise ValueError(f"the slide rate must be in (0, 1], got {rate}")
    if not 0 <= iterations <= 1_000_000:
        raise ValueError(f"iterations must be 0 to 1000000, got {iterations}")
    if not (numpy.isfinite(tangent[valid]) & (tangent[valid] >= 0.0)).all():
        raise ValueError("the critical tangent must be finite and at least 0 on every valid cell")


def slide(grid, heights, tangent, rate, iterations):
    current = numpy.asarray(heights, dtype=numpy.float64).ravel().copy()
    tangent = numpy.asarray(tangent, dtype=numpy.float64).ravel()
    check_settings(current, tangent, rate, iterations)
    free = grid.status(current) == INTERIOR
    table = grid.neighbours()
    inside = table >= 0
    safe = numpy.maximum(table, 0)
    distances = grid.distances()
    with numpy.errstate(invalid="ignore"):
        for _ in range(iterations):
            around = numpy.where(inside, current[safe], numpy.nan)
            usable = inside & numpy.isfinite(around)
            total = numpy.zeros(grid.count)
            largest = numpy.zeros(grid.count)
            for slot in range(8):
                found = (current - around[slot]) - tangent * distances[slot]
                positive = usable[slot] & (found > 0.0)
                total = numpy.where(positive, total + found, total)
                largest = numpy.where(positive & (found > largest), found, largest)
            fraction = numpy.where(free & (total > 0.0), rate * largest / (2.0 * total), 0.0)
            sent = numpy.zeros(grid.count)
            received = numpy.zeros(grid.count)
            for slot in range(8):
                outgoing = (current - around[slot]) - tangent * distances[slot]
                sent = numpy.where(usable[slot] & (outgoing > 0.0), sent + fraction * outgoing, sent)
                incoming = (around[slot] - current) - tangent[safe[slot]] * distances[OPPOSITE[slot]]
                received = numpy.where(usable[slot] & (incoming > 0.0), received + fraction[safe[slot]] * incoming, received)
            current = numpy.where(free, current - sent + received, current)
    return current.reshape(grid.shape)
