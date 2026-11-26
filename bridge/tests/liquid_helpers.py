import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from sky_helpers import luminance, render

SQRT2 = math.sqrt(2.0)


def clear_walls(name):
    """Give a container walls that let light through without refracting, so only the liquid bends rays."""
    material = bpy.data.materials.new(f"{name}_clear")
    material.use_nodes = True
    tree = material.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    tree.links.new(transparent.outputs[0], output.inputs["Surface"])
    obj = bpy.data.objects[name]
    obj.data.materials.clear()
    obj.data.materials.append(material)


def tank(bridge, name, half, height, wall=0.003, location=(0.0, 0.0, 0.0), clear=True):
    """An open square tank of inner half-width half: a four-sided lathe turned by 45 degrees, faces along the axes."""
    outer = (half + wall) * SQRT2
    inner = half * SQRT2
    profile = [[0.0, 0.0], [outer, 0.0], [outer, height], [inner, height], [inner, wall], [0.0, wall]]
    bridge.ok("lathe", name=name, profile=profile, segments=4)
    bridge.ok("transform", name=name, location=list(location), rotation=[0.0, 0.0, 45.0])
    bridge.ok("apply_transform", name=name, rotation=True)
    if clear:
        clear_walls(name)
    return name


def cup(bridge, name, radius, height, wall=0.002, location=(0.0, 0.0, 0.0), segments=64):
    profile = [[0.0, 0.0], [radius + wall, 0.0], [radius + wall, height], [radius, height], [radius, wall], [0.0, wall]]
    bridge.ok("lathe", name=name, profile=profile, segments=segments)
    bridge.ok("transform", name=name, location=list(location))
    return name


def emitter(bridge, name, size, location, strength=1.0, rotation=(0.0, 0.0, 0.0)):
    material = f"{name}_light"
    bridge.ok("add_material", name=material, base_color=[0.0, 0.0, 0.0], roughness=1.0, emission_color=[1.0, 1.0, 1.0], emission_strength=strength)
    bridge.ok("add_primitive", type="plane", name=name, size=size, location=list(location), rotation=list(rotation))
    bridge.ok("assign_material", name=name, material=material)


def dark_world(bridge):
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)


def ortho(bridge, name, location, rotation, scale):
    bridge.ok("add_camera", name=name, location=list(location), rotation=list(rotation), orthographic_scale=scale)
    bpy.data.objects[name].data.clip_start = 0.001
    return name


def mesh_points(name):
    obj = bpy.data.objects[name]
    mesh = obj.data
    points = np.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    matrix = np.array(obj.matrix_world)
    return points.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]


def attribute(name, key):
    mesh = bpy.data.objects[name].data
    layer = mesh.attributes[key]
    values = np.zeros(len(layer.data), dtype=np.float32)
    layer.data.foreach_get("value", values)
    return values.astype(float)


def top_faces(name):
    mesh = bpy.data.objects[name].data
    flags = np.zeros(len(mesh.polygons), dtype=bool)
    mesh.attributes["lq_top"].data.foreach_get("value", flags)
    return flags


def edge_position(row, width=7):
    """Sub-pixel position where a bright-to-dark row, box-filtered against noise, crosses halfway at its steepest step."""
    row = np.convolve(np.asarray(row, dtype=float), np.ones(width) / width, mode="same")[width:-width]
    high, low = np.percentile(row, 95), np.percentile(row, 5)
    middle = 0.5 * (high + low)
    above = row >= middle
    crossings = np.nonzero(above[:-1] != above[1:])[0]
    if not len(crossings):
        return None
    steps = np.abs(row[crossings + 1] - row[crossings])
    index = int(crossings[np.argmax(steps)]) if len(crossings) > 1 else int(crossings[0])
    a, b = row[index], row[index + 1]
    return width + index + (a - middle) / (a - b)


def render_luminance(bridge, name, size, samples, camera, height=None):
    return luminance(render(bridge, name, size, samples, camera, height))


def dimple(name, size, cells, radius, curvature):
    """A flat square with a paraboloid hollow: z = (r^2 - radius^2) / (2 curvature) inside radius, 0 outside."""
    import bmesh

    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=cells, y_segments=cells, size=size / 2.0)
    for vertex in bm.verts:
        r2 = vertex.co.x ** 2 + vertex.co.y ** 2
        vertex.co.z = min((r2 - radius * radius) / (2.0 * curvature), 0.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj
