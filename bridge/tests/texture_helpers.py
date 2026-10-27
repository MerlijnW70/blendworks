import json
import os
import struct

import bpy

from harness import snapshot

FORMATS = {".png": "PNG", ".jpg": "JPEG", ".exr": "OPEN_EXR", ".webp": "WEBP"}


def write_image(folder, name, width, height, rgba, float_buffer=False, pixels=None):
    image = bpy.data.images.new("writer", width, height, alpha=True, float_buffer=float_buffer)
    image.pixels.foreach_set(pixels if pixels is not None else list(rgba) * (width * height))
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.filepath_raw = path
    image.file_format = FORMATS[os.path.splitext(name)[1]]
    image.save()
    bpy.data.images.remove(image)
    return path


def glb_parts(path):
    with open(path, "rb") as handle:
        data = handle.read()
    magic, version, length = struct.unpack("<4sII", data[:12])
    assert magic == b"glTF" and version == 2 and length == len(data), path
    json_length, kind = struct.unpack("<I4s", data[12:20])
    assert kind == b"JSON"
    document = json.loads(data[20 : 20 + json_length])
    position = 20 + json_length
    binary = b""
    if position < len(data):
        binary_length, kind = struct.unpack("<I4s", data[position : position + 8])
        assert kind == b"BIN\x00"
        binary = data[position + 8 : position + 8 + binary_length]
    return document, binary


def glb_image_bytes(document, binary, texture_info):
    texture = document["textures"][texture_info["index"]]
    image = document["images"][texture["source"]]
    view = document["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    return binary[start : start + view["byteLength"]], image["mimeType"]


def graph_signature(material):
    tree = material.node_tree
    nodes = sorted(
        (
            node.bl_idname,
            node.name,
            getattr(getattr(node, "image", None), "name", None),
            tuple(round(value, 5) if isinstance(value, float) else value for value in socket_values(node)),
        )
        for node in tree.nodes
    )
    links = sorted((link.from_node.name, link.from_socket.identifier, link.to_node.name, link.to_socket.identifier) for link in tree.links)
    return nodes, links, material.displacement_method, material.surface_render_method


def socket_values(node):
    values = []
    for socket in node.inputs:
        value = getattr(socket, "default_value", None)
        if isinstance(value, (int, float)):
            values.append(value)
        elif value is not None and hasattr(value, "__len__"):
            values.extend(float(item) for item in value)
    return values


def world_state():
    return (
        snapshot(),
        sorted((image.name, image.colorspace_settings.name) for image in bpy.data.images),
        sorted(group.name for group in bpy.data.node_groups),
        {material.name: graph_signature(material) for material in bpy.data.materials if material.node_tree is not None},
    )


def linked_from(socket):
    assert socket.is_linked, f"{socket.node.name}.{socket.name} is not linked"
    return socket.links[0].from_node, socket.links[0].from_socket


def upstream_image(socket):
    node, _ = linked_from(socket)
    seen = 0
    while node.type != "TEX_IMAGE":
        seen += 1
        assert seen < 10, socket.name
        linked = [item for item in node.inputs if item.is_linked]
        assert linked, f"no image upstream of {socket.name}"
        node = linked[0].links[0].from_node
    return node.image


def principled(material):
    return next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")


def pixel(image, x, y):
    width = image.size[0]
    start = (y * width + x) * 4
    return list(image.pixels[start : start + 4])
