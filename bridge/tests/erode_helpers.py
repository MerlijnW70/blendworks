import math

import bpy
import numpy

NOISE = {"seed": 5, "scale": 32.0, "octaves": 4, "hurst": 0.8, "mode": "ridged", "ridge_offset": 1.0}
TILE = {"size": [64.0, 64.0], "resolution": 33, "height": 30.0, "base_height": 40.0, "form": "none", **NOISE}
NEIGHBOUR_STEPS = ((0, 1), (1, 0), (1, 1), (1, -1))


def make_tile(bridge, name, tile=(0, 0), **overrides):
    return bridge.ok("heightfield", name=name, tile=list(tile), **{**TILE, **overrides})


def surface_heights(name, resolution):
    obj = bpy.data.objects[name]
    coordinates = numpy.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", coordinates)
    return coordinates.reshape(-1, 3)[: resolution * resolution, 2].reshape(resolution, resolution) + obj.location.z


def attribute_values(name, attribute):
    mesh = bpy.data.objects[name].data
    values = numpy.empty(len(mesh.attributes[attribute].data))
    mesh.attributes[attribute].data.foreach_get("value", values)
    return values


def interior_max_slope(heights, spacing):
    core = heights[1:-1, 1:-1]
    rows, columns = core.shape
    steepest = 0.0
    for row, column in NEIGHBOUR_STEPS:
        first = core[: rows - row, max(0, -column) : columns - max(0, column)]
        second = core[row:, max(0, column) : columns - max(0, -column)]
        steepest = max(steepest, float(numpy.abs(first - second).max() / math.hypot(column * spacing, row * spacing)))
    return math.degrees(math.atan(steepest))
