"""Reads and writes .glb files and adds GPU instancing for ground cover export."""

import json
import struct

import numpy

INSTANCING = "EXT_mesh_gpu_instancing"
TINT_ATTRIBUTE = "_GC_TINT"
GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
FLOAT = 5126
Y_UP = numpy.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])


def read_glb(path):
    with open(path, "rb") as handle:
        data = handle.read()
    magic, _, _ = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError(f"{path} is not a binary glTF file")
    length, kind = struct.unpack_from("<II", data, 12)
    document = json.loads(data[20:20 + length].decode("utf-8"))
    offset = 20 + length
    binary = b""
    if offset < len(data):
        size, kind = struct.unpack_from("<II", data, offset)
        if kind == BIN_CHUNK:
            binary = data[offset + 8:offset + 8 + size]
    return document, bytearray(binary)


def padded(data, filler):
    return data + filler * ((4 - len(data) % 4) % 4)


def write_glb(path, document, binary):
    text = padded(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    chunks = struct.pack("<II", len(text), JSON_CHUNK) + text
    if binary:
        body = padded(bytes(binary), b"\x00")
        chunks += struct.pack("<II", len(body), BIN_CHUNK) + body
    with open(path, "wb") as handle:
        handle.write(struct.pack("<III", GLB_MAGIC, 2, 12 + len(chunks)) + chunks)


def append_accessor(document, binary, values, kind):
    values = numpy.ascontiguousarray(values, dtype="<f4")
    while len(binary) % 4:
        binary.append(0)
    if not document.get("buffers"):
        document["buffers"] = [{"byteLength": 0}]
    view = {"buffer": 0, "byteOffset": len(binary), "byteLength": int(values.nbytes)}
    binary.extend(values.tobytes())
    document["buffers"][0]["byteLength"] = len(binary)
    document.setdefault("bufferViews", []).append(view)
    accessor = {"bufferView": len(document["bufferViews"]) - 1, "componentType": FLOAT, "count": int(len(values)), "type": kind}
    document.setdefault("accessors", []).append(accessor)
    return len(document["accessors"]) - 1


def quaternions(r):
    trace = r[:, 0, 0] + r[:, 1, 1] + r[:, 2, 2]
    by_trace = trace > 0.0
    by_x = ~by_trace & (r[:, 0, 0] >= r[:, 1, 1]) & (r[:, 0, 0] >= r[:, 2, 2])
    by_y = ~by_trace & ~by_x & (r[:, 1, 1] >= r[:, 2, 2])
    by_z = ~(by_trace | by_x | by_y)
    result = numpy.zeros((len(r), 4))
    m = r[by_trace]
    s = 2.0 * numpy.sqrt(1.0 + m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2])
    result[by_trace] = numpy.column_stack([(m[:, 2, 1] - m[:, 1, 2]) / s, (m[:, 0, 2] - m[:, 2, 0]) / s, (m[:, 1, 0] - m[:, 0, 1]) / s, 0.25 * s])
    m = r[by_x]
    s = 2.0 * numpy.sqrt(1.0 + m[:, 0, 0] - m[:, 1, 1] - m[:, 2, 2])
    result[by_x] = numpy.column_stack([0.25 * s, (m[:, 0, 1] + m[:, 1, 0]) / s, (m[:, 0, 2] + m[:, 2, 0]) / s, (m[:, 2, 1] - m[:, 1, 2]) / s])
    m = r[by_y]
    s = 2.0 * numpy.sqrt(1.0 + m[:, 1, 1] - m[:, 0, 0] - m[:, 2, 2])
    result[by_y] = numpy.column_stack([(m[:, 0, 1] + m[:, 1, 0]) / s, 0.25 * s, (m[:, 1, 2] + m[:, 2, 1]) / s, (m[:, 0, 2] - m[:, 2, 0]) / s])
    m = r[by_z]
    s = 2.0 * numpy.sqrt(1.0 + m[:, 2, 2] - m[:, 0, 0] - m[:, 1, 1])
    result[by_z] = numpy.column_stack([(m[:, 0, 2] + m[:, 2, 0]) / s, (m[:, 1, 2] + m[:, 2, 1]) / s, 0.25 * s, (m[:, 1, 0] - m[:, 0, 1]) / s])
    return result / numpy.linalg.norm(result, axis=1)[:, None]


def instance_parts(matrices, yup):
    linear = matrices[:, :3, :3]
    scales = numpy.linalg.norm(linear, axis=1)
    rotations = linear / numpy.maximum(scales[:, None, :], 1e-12)
    translations = matrices[:, :3, 3]
    if yup:
        rotations = Y_UP @ rotations @ Y_UP.T
        translations = translations @ Y_UP.T
        scales = scales[:, [0, 2, 1]]
    return translations, quaternions(rotations), scales


def add_instancing(path, groups, yup, tints=None):
    document, binary = read_glb(path)
    nodes = {node.get("name"): index for index, node in enumerate(document.get("nodes", []))}
    written = {}
    for name, matrices in groups.items():
        if name not in nodes or not len(matrices):
            continue
        node = document["nodes"][nodes[name]]
        translations, rotations, scales = instance_parts(matrices, yup)
        attributes = {
            "TRANSLATION": append_accessor(document, binary, translations, "VEC3"),
            "ROTATION": append_accessor(document, binary, rotations, "VEC4"),
            "SCALE": append_accessor(document, binary, scales, "VEC3"),
        }
        if tints is not None:
            attributes[TINT_ATTRIBUTE] = append_accessor(document, binary, tints[name], "SCALAR")
        node.setdefault("extensions", {})[INSTANCING] = {"attributes": attributes}
        written[name] = int(len(matrices))
    if written:
        used = document.setdefault("extensionsUsed", [])
        if INSTANCING not in used:
            used.append(INSTANCING)
    write_glb(path, document, binary)
    return written
