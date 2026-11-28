"""Foam and bubble materials for liquid surfaces."""

import math

import numpy

from . import liquid_shader
from .liquid_container import boundary_distance

SINK = 0.0008


def boundary_edges(faces):
    counts = {}
    for face in faces.tolist():
        for position in range(3):
            a, b = face[position], face[(position + 1) % 3]
            key = (min(a, b), max(a, b))
            counts[key] = counts.get(key, [0, (a, b)])
            counts[key][0] += 1
    return [edge for count, edge in counts.values() if count == 1]


def head(points, faces, top, height, seed):
    """A foam head on the liquid's surface: the cap lifted by height, a little lumpy, clinging to the wall, closed underneath."""
    cap = faces[top]
    used = numpy.unique(cap)
    remap = {int(old): new for new, old in enumerate(used.tolist())}
    base = points[used].copy()
    base[:, 2] -= SINK
    edges = boundary_edges(cap)
    a = numpy.array([points[edge[0]][:2] for edge in edges])
    b = numpy.array([points[edge[1]][:2] for edge in edges])
    distance = boundary_distance(base[:, :2], a, b)
    rng = numpy.random.default_rng([seed, 0xF0A])
    lumps = numpy.zeros(len(base))
    for _ in range(6):
        direction = rng.normal(size=2)
        direction /= numpy.linalg.norm(direction)
        wavelength = height * rng.uniform(1.5, 4.0)
        lumps += 0.05 * numpy.sin(base[:, :2] @ direction * 2.0 * math.pi / wavelength + rng.uniform(0, 2 * math.pi))
    rise = height * (1.0 - 0.3 * numpy.exp(-distance / (0.3 * height))) * (1.0 + lumps)
    lifted = base.copy()
    lifted[:, 2] = points[used][:, 2] + rise
    count = len(base)
    bottom = numpy.array([[remap[index] for index in face] for face in cap.tolist()])
    result_faces = [bottom[:, ::-1], bottom + count]
    sides = []
    for first, second in edges:
        i, j = remap[first], remap[second]
        sides.append((i, j, j + count))
        sides.append((i, j + count, i + count))
    result_faces.append(numpy.array(sides, dtype=int).reshape(-1, 3))
    return numpy.concatenate([base, lifted]), numpy.concatenate(result_faces)


def foam_material(name, entry):
    foam = entry.get("foam") or {}
    material = liquid_shader.fresh_material(name)
    graph = liquid_shader.LiquidGraph(material.node_tree)
    output = graph.node("ShaderNodeOutputMaterial")
    node = graph.node("ShaderNodeBsdfPrincipled", "lq_foam_head")
    node.subsurface_method = "RANDOM_WALK"
    node.inputs["Base Color"].default_value = list(foam.get("color", [0.93, 0.9, 0.82])) + [1.0]
    node.inputs["Roughness"].default_value = 0.55
    node.inputs["Subsurface Weight"].default_value = 1.0
    radius = foam.get("scatter_radius", 0.0015)
    node.inputs["Subsurface Radius"].default_value = (radius, radius * 0.85, radius * 0.6)
    node.inputs["Subsurface Scale"].default_value = 1.0
    material.node_tree.links.new(node.outputs[0], output.inputs["Surface"])
    material["blendworks_liquid"] = "foam"
    return material


def bubble_material(name, ior):
    material = liquid_shader.fresh_material(name)
    graph = liquid_shader.LiquidGraph(material.node_tree)
    output = graph.node("ShaderNodeOutputMaterial")
    surface = liquid_shader.clear_surface(graph, {"roughness": 0.0, "ior": 1.0 / ior}, None)
    material.node_tree.links.new(surface, output.inputs["Surface"])
    material["blendworks_liquid"] = "bubble"
    return material
