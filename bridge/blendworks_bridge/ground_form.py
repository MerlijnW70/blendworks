"""Worn hillslopes on a heightfield grid: slope failures, rills along the flow, and tussock hummocks.

Sources (docs/research/bank-form.md):
- Slope failure: soil and regolith stand at most at their angle of internal friction, about 30 to 38 degrees (Selby 1993,
  Hillslope Materials and Processes); steeper ground fails down to that angle, leaving bare scars.
- Rills: overland flow concentrates where the drainage area A and slope S give a stream power A^0.5 S above a threshold
  (Montgomery and Dietrich 1988, 1994); rills are at most about 0.3 m deep, deeper channels are gullies (Poesen et al. 2003).
- Tussocks: tussock grasses such as Deschampsia cespitosa form hummocks of 0.2 to 0.5 m across and 0.1 to 0.3 m high
  about half a metre to a metre apart (Davy 1980, Biological Flora of the British Isles).
Every step uses the native terrain kernels for flow; the forms fade out over the outermost EDGE_CELLS so tiles still meet.
"""
import math

import numpy

from . import terrain_kernels

FRICTION_DEGREES = 34.0
SCAR_DEPTH = 0.01
RILL_THRESHOLD = 1.2
RILL_GAIN = 0.05
RILL_MAX = 0.3
TUSSOCK_SPACING = 0.75
TUSSOCK_RADIUS = (0.1, 0.25)
TUSSOCK_HEIGHT = (0.08, 0.25)
TUSSOCK_SLOPE = 20.0
TUSSOCK_SHARE = 0.55
EDGE_CELLS = 6
ROUGHNESS = {"turf": 0.015, "soil": 0.008, "gravel": 0.02, "mud": 0.004}


def edge_fade(shape):
    rows, columns = numpy.indices(shape)
    inside = numpy.minimum(numpy.minimum(rows, shape[0] - 1 - rows), numpy.minimum(columns, shape[1] - 1 - columns))
    return numpy.clip(inside / float(EDGE_CELLS), 0.0, 1.0)


def slope_of(heights, spacing):
    rise_y, rise_x = numpy.gradient(heights, spacing[0], spacing[1])
    return numpy.sqrt(rise_x * rise_x + rise_y * rise_y)


def fail_slopes(heights, spacing):
    """Cells that stand above a neighbour more steeply than the angle of friction fail: the surface is lowered to the
    steepest stable surface (the threshold-hillslope kernel, an exact eikonal of critical slopes; the failed material is
    carried off by the flow below), and the cells that lost more than SCAR_DEPTH are bare scars."""
    tangent = math.tan(math.radians(FRICTION_DEGREES))
    settled, _ = terrain_kernels.threshold(heights, tangent, spacing=spacing)
    settled = numpy.asarray(settled).reshape(heights.shape)
    return settled, (heights - settled) > SCAR_DEPTH


def rills(heights, spacing):
    """Drainage area by D8 flow over the pit-filled surface (native kernels), and a rill cut along every cell whose stream
    power A^0.5 S passes RILL_THRESHOLD: deeper the more it passes, at most RILL_MAX, and half as deep in its neighbours across
    the flow so the cut has a V section."""
    filled, _ = terrain_kernels.priority_flood(heights)
    receivers, _ = terrain_kernels.d8(filled, spacing=spacing)
    ordering = terrain_kernels.order(receivers, heights.shape)
    area = terrain_kernels.accumulate(ordering, numpy.full(heights.size, spacing[0] * spacing[1])).reshape(heights.shape)
    power = numpy.sqrt(area) * slope_of(heights, spacing)
    depth = numpy.clip(RILL_GAIN * (power - RILL_THRESHOLD), 0.0, RILL_MAX)
    side = 0.5 * numpy.maximum.reduce([numpy.roll(depth, shift, axis) for shift in (-1, 1) for axis in (0, 1)])
    return numpy.maximum(depth, side), area, power


def tussocks(heights, spacing, columns, rows, seed):
    """Quartic hummocks (1 - r^2)^2 centred on a jittered lattice of TUSSOCK_SPACING in world metres (so tiles agree), on
    TUSSOCK_SHARE of its sites, each of a radius and height drawn from the cited ranges, only on slopes under
    TUSSOCK_SLOPE degrees; none when a hummock spans fewer than three cells."""
    if 2.0 * TUSSOCK_RADIUS[0] < 3.0 * min(spacing):
        return numpy.zeros_like(heights)
    gentle = slope_of(heights, spacing) < math.tan(math.radians(TUSSOCK_SLOPE))
    raised = numpy.zeros_like(heights)
    cell_x, cell_y = numpy.floor(columns / TUSSOCK_SPACING), numpy.floor(rows / TUSSOCK_SPACING)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            site_x, site_y = cell_x + dx, cell_y + dy
            draws = [site_hash(site_x, site_y, seed, salt) for salt in range(5)]
            centre_x = (site_x + 0.2 + 0.6 * draws[0]) * TUSSOCK_SPACING
            centre_y = (site_y + 0.2 + 0.6 * draws[1]) * TUSSOCK_SPACING
            radius = TUSSOCK_RADIUS[0] + draws[2] * (TUSSOCK_RADIUS[1] - TUSSOCK_RADIUS[0])
            height = TUSSOCK_HEIGHT[0] + draws[3] * (TUSSOCK_HEIGHT[1] - TUSSOCK_HEIGHT[0])
            reach = numpy.sqrt((columns - centre_x) ** 2 + (rows - centre_y) ** 2) / radius
            inside = 1.0 - numpy.minimum(reach, 1.0) ** 2
            bump = numpy.where((reach < 1.0) & (draws[4] < TUSSOCK_SHARE), height * inside * inside, 0.0)
            raised = numpy.maximum(raised, bump.reshape(heights.shape))
    return raised * gentle


def site_hash(x, y, seed, salt):
    """A uniform number in [0, 1) for each lattice site, from integer arithmetic only, the same on every platform."""
    value = (x.astype(numpy.int64) * 73856093) ^ (y.astype(numpy.int64) * 19349663) ^ ((seed * 83492791 + salt * 2654435761) % 2147483647)
    value = (value ^ (value >> 13)) * 1274126177
    return ((value ^ (value >> 16)) & 0xFFFFFF).astype(numpy.float64) / float(0x1000000)


def worn(flat_heights, resolution, size, columns, rows, seed):
    """The worn surface of a heightfield tile and its micro-relief amplitude per vertex (metres, by surface class: turf,
    bare soil on scars and rills), with a report of what was formed."""
    shape = (resolution, resolution)
    spacing = (size[1] / (resolution - 1), size[0] / (resolution - 1))
    heights = numpy.asarray(flat_heights, dtype=numpy.float64).reshape(shape)
    fade = edge_fade(shape)
    settled, scars = fail_slopes(heights, spacing)
    shaped = heights + (settled - heights) * fade
    cut, area, power = rills(shaped, spacing)
    shaped = shaped - cut * fade
    hummocks = tussocks(shaped, spacing, columns, rows, seed) * fade * (cut <= 0.0) * ~scars
    shaped = shaped + hummocks
    amplitude = numpy.where(scars | (cut > 0.0), ROUGHNESS["soil"], ROUGHNESS["turf"])
    report = {"scar_share": round(float(scars.mean()), 6), "rill_cells": int((cut > 0.0).sum()), "deepest_rill": round(float(cut.max()), 4),
              "tussocks_raised": round(float((hummocks > 0.0).mean()), 6), "highest_tussock": round(float(hummocks.max()), 4)}
    return shaped.ravel(), amplitude.ravel(), {"area": area, "power": power, "cut": cut, "scars": scars}, report


RELIEF_ATTRIBUTE = "ground_relief"
TERRAIN_FLAG = "blendworks_terrain"


def store_relief(obj, relief):
    """Keep the micro-relief amplitude (metres) on the mesh as a point attribute for render-time displacement, and flag
    the object as formed terrain."""
    mesh = obj.data
    values = numpy.zeros(len(mesh.vertices), dtype=numpy.float32)
    values[: len(relief)] = relief
    attribute = mesh.attributes.get(RELIEF_ATTRIBUTE) or mesh.attributes.new(RELIEF_ATTRIBUTE, "FLOAT", "POINT")
    attribute.data.foreach_set("value", values)
    obj[TERRAIN_FLAG] = True
