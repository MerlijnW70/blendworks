"""Reads and writes glTF files to add skeleton extras."""

import json
import os
import struct

from .errors import failed
from .tree_skeleton import PROPERTY, plain

GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
HEADER = struct.Struct("<III")
CHUNK = struct.Struct("<II")


def skeleton_extras(objects):
    return {obj.name: plain(obj[PROPERTY]) for obj in objects if PROPERTY in obj.keys()}


def read_glb(path):
    with open(path, "rb") as handle:
        data = handle.read()
    magic, version, total = HEADER.unpack_from(data, 0)
    if magic != GLB_MAGIC or version != 2 or total != len(data):
        raise failed("the exported .glb has an unexpected header")
    length, kind = CHUNK.unpack_from(data, HEADER.size)
    if kind != JSON_CHUNK:
        raise failed("the exported .glb does not start with a JSON chunk")
    start = HEADER.size + CHUNK.size
    return json.loads(data[start : start + length].decode("utf-8")), data[start + length :]


def write_glb(path, document, rest):
    text = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = HEADER.size + CHUNK.size + len(text) + len(rest)
    partial = f"{path}.extras-partial"
    with open(partial, "wb") as handle:
        handle.write(HEADER.pack(GLB_MAGIC, 2, total))
        handle.write(CHUNK.pack(len(text), JSON_CHUNK))
        handle.write(text)
        handle.write(rest)
    os.replace(partial, path)


def add_skeleton_extras(path, objects):
    extras = skeleton_extras(objects)
    if not extras:
        return []
    document, rest = read_glb(path)
    written = []
    for node in document.get("nodes", []):
        name = node.get("name")
        if name in extras:
            node.setdefault("extras", {})[PROPERTY] = extras[name]
            written.append(name)
    missing = sorted(set(extras) - set(written))
    if missing:
        raise failed(f"the exporter wrote no glTF node for {', '.join(missing)}, so its skeleton has nowhere to go")
    write_glb(path, document, rest)
    return sorted(written)
