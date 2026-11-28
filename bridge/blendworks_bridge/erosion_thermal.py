"""Thermal erosion: material slides downhill past the talus angle."""

import math

import numpy

NEIGHBOURS = ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))
TOLERANCE_DEGREES = 0.05


def neighbour_slices(shape, row_step, column_step):
    rows, columns = shape
    donor = (slice(max(0, -row_step), rows - max(0, row_step)), slice(max(0, -column_step), columns - max(0, column_step)))
    receiver = (slice(max(0, row_step), rows - max(0, -row_step)), slice(max(0, column_step), columns - max(0, -column_step)))
    return donor, receiver


def distances(spacing):
    return [math.hypot(column * spacing[0], row * spacing[1]) for row, column in NEIGHBOURS]


def excesses(heights, weight, tangent, spacing):
    found = []
    for (row, column), distance in zip(NEIGHBOURS, distances(spacing)):
        donor, receiver = neighbour_slices(heights.shape, row, column)
        excess = numpy.zeros_like(heights)
        drop = heights[donor] - heights[receiver] - tangent * distance
        excess[donor] = numpy.where(drop > 0.0, drop, 0.0) * numpy.minimum(weight[donor], weight[receiver])
        found.append(excess)
    return found


def sweep(heights, weight, tangent, spacing, rate):
    found = excesses(heights, weight, tangent, spacing)
    total = sum(found)
    largest = numpy.maximum.reduce(found)
    scale = numpy.divide(rate * 0.5 * largest, total, out=numpy.zeros_like(total), where=total > 0.0)
    for (row, column), excess in zip(NEIGHBOURS, found):
        donor, receiver = neighbour_slices(heights.shape, row, column)
        moved = excess * scale
        heights[donor] -= moved[donor]
        heights[receiver] += moved[donor]
    return float(largest.max())


def max_slope_degrees(heights, weight, spacing):
    steepest = 0.0
    for (row, column), distance in zip(NEIGHBOURS, distances(spacing)):
        donor, receiver = neighbour_slices(heights.shape, row, column)
        both = (weight[donor] > 0.0) & (weight[receiver] > 0.0)
        if both.any():
            steepest = max(steepest, float(numpy.abs(heights[donor] - heights[receiver])[both].max() / distance))
    return math.degrees(math.atan(steepest))


def thermal_erode(heights, weight, spacing, talus_degrees, rate, iterations):
    tangent = math.tan(math.radians(talus_degrees))
    margin = (math.tan(math.radians(talus_degrees + TOLERANCE_DEGREES)) - tangent) * min(spacing)
    done = 0
    for done in range(1, iterations + 1):
        if sweep(heights, weight, tangent, spacing, rate) <= margin:
            return done, True
    return done, False
