"""Exact digests of a scene: every object's transform, collections and data with all attributes, hidden ones such as
edge vertices and corner edges included, and the content of every material."""
import hashlib

import bpy
import numpy

LAYOUTS = {
    "BOOLEAN": ("value", numpy.bool_, 1), "INT8": ("value", numpy.int32, 1), "INT": ("value", numpy.int32, 1),
    "FLOAT": ("value", numpy.float32, 1), "INT16_2D": ("value", numpy.int32, 2), "INT32_2D": ("value", numpy.int32, 2), "FLOAT2": ("vector", numpy.float32, 2),
    "FLOAT_VECTOR": ("vector", numpy.float32, 3), "FLOAT_COLOR": ("color", numpy.float32, 4),
    "BYTE_COLOR": ("color", numpy.float32, 4), "QUATERNION": ("value", numpy.float32, 4), "FLOAT4X4": ("value", numpy.float32, 16),
}
SIZES = {"POINT": "vertices", "EDGE": "edges", "FACE": "polygons", "CORNER": "loops"}


def attribute_digest(mesh, attribute):
    if attribute.data_type == "STRING":
        return hashlib.sha256("\0".join(item.value for item in attribute.data).encode("utf-8")).hexdigest()[:16]
    field, kind, width = LAYOUTS[attribute.data_type]
    count = len(getattr(mesh, SIZES[attribute.domain]))
    values = numpy.empty(count * width, dtype=kind)
    if count:
        attribute.data.foreach_get(field, values)
    return hashlib.sha256(values.tobytes()).hexdigest()[:16]


def mesh_digest(mesh):
    parts = {f"{attribute.domain}:{attribute.name}": attribute_digest(mesh, attribute) for attribute in mesh.attributes}
    starts = numpy.empty(len(mesh.polygons), dtype=numpy.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    parts["FACE:loop_start"] = hashlib.sha256(starts.tobytes()).hexdigest()[:16]
    for layer in mesh.uv_layers:
        values = numpy.empty(len(mesh.loops) * 2, dtype=numpy.float32)
        layer.uv.foreach_get("vector", values)
        parts[f"UV:{layer.name}"] = hashlib.sha256(values.tobytes()).hexdigest()[:16]
    parts["materials"] = ",".join(material.name if material else "" for material in mesh.materials)
    return parts


def scene_digest():
    found = {}
    for obj in sorted(bpy.context.scene.objects, key=lambda item: item.name):
        entry = {"type": obj.type, "matrix": hashlib.sha256(numpy.array(obj.matrix_world, dtype=numpy.float64).tobytes()).hexdigest()[:16]}
        entry["collections"] = sorted(collection.name for collection in obj.users_collection)
        entry["hidden"] = bool(obj.hide_get()) if obj.name in bpy.context.view_layer.objects else None
        entry["parent"] = obj.parent.name if obj.parent else None
        if obj.type == "MESH":
            entry["counts"] = [len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)]
            entry["data"] = mesh_digest(obj.data)
        found[obj.name] = entry
    return found


def material_digest():
    from blendworks_bridge.blendfile import content_digest

    return {material.name: content_digest(material) for material in sorted(bpy.data.materials, key=lambda item: item.name)}
