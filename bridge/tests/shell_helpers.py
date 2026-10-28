import math

import bpy

from blendworks_bridge.registry import COMMANDS
from blendworks_bridge.schema import validate
from blendworks_bridge.shell import build_spiral


def spiral_for(**kwargs):
    return build_spiral(validate(COMMANDS["shell"].schema, {"name": "S", **kwargs}))


def build(bridge, name="S", **kwargs):
    return bridge.ok("shell", name=name, **kwargs)


def ring_coordinates(spiral, k):
    return spiral.coordinates((k - spiral.tail) * spiral.dt)


def mesh_ring(name, result, k):
    count = result["points_per_ring"]
    vertices = bpy.data.objects[name].data.vertices
    return [vertices[k * count + j].co.copy() for j in range(count)]


def main_ring(name, result, k):
    return mesh_ring(name, result, result["tail_rings"] + k)


def radius(point):
    return math.hypot(point.x, point.y)


def pairs(points):
    return [(radius(point), point.z) for point in points]


def middle(pairs_):
    radials, heights = [r for r, _ in pairs_], [z for _, z in pairs_]
    return (min(radials) + max(radials)) / 2.0, (min(heights) + max(heights)) / 2.0


def peaks(values):
    count = len(values)
    return sum(1 for i in range(count) if values[i] > values[i - 1] and values[i] > values[(i + 1) % count])
