import json
import math
import os
import struct

import bpy
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
FLOAT = 5126


def make_plane(bridge, name="Ground", size=10.0, cuts=0, location=(0.0, 0.0, 0.0)):
    bridge.ok("add_primitive", type="plane", name=name, size=size, location=list(location))
    if cuts:
        bridge.ok("subdivide", name=name, cuts=cuts)


def make_soil(bridge, target="Ground"):
    bridge.ok("material_procedural", name="Soil", soil={})
    bridge.ok("assign_material", name=target, material="Soil")


def points_of(name):
    mesh = bpy.data.objects[name].data
    values = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", values)
    return values.reshape(-1, 3)


def attribute_of(name, attribute, width=1):
    mesh = bpy.data.objects[name].data
    data = mesh.attributes[attribute].data
    kind = numpy.int32 if mesh.attributes[attribute].data_type == "INT" else numpy.float32
    values = numpy.empty(len(data) * width, dtype=kind)
    data.foreach_get("value", values)
    return values if width == 1 else values.reshape(len(data), width)


def evaluated_instances(parent_name):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    found = []
    for instance in depsgraph.object_instances:
        if instance.is_instance and instance.parent is not None and instance.parent.original.name == parent_name:
            found.append((numpy.array(instance.matrix_world), instance.object.original.data.name if instance.object.original.data else instance.object.data.name))
    return found


def world_tree(name):
    bpy.context.view_layer.update()
    obj = bpy.data.objects[name]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        corners = [(obj.matrix_world @ vertex.co).copy() for vertex in mesh.vertices]
        faces = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
    finally:
        evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(corners, faces)


def surface_below(tree, point):
    origin = Vector((point[0], point[1], point[2] + 50.0))
    location, normal, _, _ = tree.ray_cast(origin, Vector((0.0, 0.0, -1.0)), 200.0)
    return location, normal


def slope_at(tree, point):
    _, normal, _, _ = tree.find_nearest(Vector(point))
    return math.degrees(math.acos(max(-1.0, min(1.0, abs(normal.z)))))


def base_points(mesh_name, band=0.002):
    mesh = bpy.data.meshes[mesh_name]
    values = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", values)
    values = values.reshape(-1, 3)
    return values[values[:, 2] <= values[:, 2].min() + band]


def glb_document(path):
    with open(path, "rb") as handle:
        data = handle.read()
    length = struct.unpack("<I", data[12:16])[0]
    document = json.loads(data[20:20 + length])
    offset = 20 + length
    binary = data[offset + 8:offset + 8 + struct.unpack("<I", data[offset:offset + 4])[0]] if offset < len(data) else b""
    return document, binary


def accessor_values(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    assert accessor["componentType"] == FLOAT
    width = COMPONENTS[accessor["type"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", 4 * width)
    rows = [struct.unpack_from(f"<{width}f", binary, start + row * stride) for row in range(accessor["count"])]
    return numpy.array(rows)


def instanced_translations(document, binary):
    rows = []
    for node in document["nodes"]:
        extension = node.get("extensions", {}).get("EXT_mesh_gpu_instancing")
        if extension is not None:
            rows.append(accessor_values(document, binary, extension["attributes"]["TRANSLATION"]))
    return numpy.concatenate(rows) if rows else numpy.zeros((0, 3))


def sorted_rows(values, digits=4):
    rounded = numpy.round(values, digits)
    return rounded[numpy.lexsort(rounded.T[::-1])]


def workspace_file(bridge, name):
    return os.path.join(bridge.workspace, name)
