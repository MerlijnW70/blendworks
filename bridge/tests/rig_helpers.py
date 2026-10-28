import json
import os
import struct
import sys

import bpy
import numpy
from mathutils import Vector

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "examples")
if EXAMPLES not in sys.path:
    sys.path.insert(0, EXAMPLES)

import character_models


def builder(bridge):
    return lambda name, /, **args: bridge.ok(name, **args)


def hero(bridge):
    return character_models.hero(builder(bridge))


def fox(bridge):
    return character_models.fox(builder(bridge))


def chest(bridge):
    return character_models.chest(builder(bridge))


def evaluated_world(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        flat = numpy.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", flat)
        matrix = numpy.array(evaluated.matrix_world)
        points = flat.reshape(-1, 3)
        return points @ matrix[:3, :3].T + matrix[:3, 3]
    finally:
        evaluated.to_mesh_clear()


def dominant_vertices(obj, bones):
    names = {group.index: group.name for group in obj.vertex_groups}
    chosen = []
    for vertex in obj.data.vertices:
        if vertex.groups:
            best = max(vertex.groups, key=lambda element: element.weight)
            if names[best.group] in bones:
                chosen.append(vertex.index)
    return chosen


def weights_of(obj):
    names = {group.index: group.name for group in obj.vertex_groups}
    return [{names[element.group]: element.weight for element in vertex.groups if element.weight > 0} for vertex in obj.data.vertices]


def bone_world(armature, bone, end="head"):
    pose_bone = armature.pose.bones[bone]
    return armature.matrix_world @ (pose_bone.head if end == "head" else pose_bone.tail)


def gltf(path):
    with open(path, "rb") as handle:
        data = handle.read()
    length = struct.unpack("<I", data[12:16])[0]
    document = json.loads(data[20:20 + length])
    binary_start = 20 + length
    binary = data[binary_start + 8:] if len(data) > binary_start else b""
    return document, binary


def accessor_floats(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[accessor["type"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = struct.unpack_from(f"<{accessor['count'] * components}f", binary, start)
    return [values[index * components:(index + 1) * components] for index in range(accessor["count"])]


def import_glb(bridge, path):
    bridge.ok("new_scene")
    bridge.ok("import", path=path)
    return [obj for obj in bpy.context.scene.objects]


def distance(first, second):
    return (Vector(first) - Vector(second)).length
