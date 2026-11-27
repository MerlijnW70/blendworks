import json
import os
import struct
import zlib

from harness import Bridge

FOLDER = ".blendworks"


def saving(bridge, seconds=0.0, allow_python=False):
    return Bridge(bridge.workspace, allow_python=allow_python, autosave_seconds=seconds)


def folder(session):
    return os.path.join(session.workspace, FOLDER)


def files(session):
    path = folder(session)
    return sorted(os.listdir(path)) if os.path.isdir(path) else []


def meta(session):
    with open(os.path.join(folder(session), "autosave.json"), encoding="utf-8") as handle:
        return json.load(handle)


def journal_lines(session):
    record = meta(session)
    with open(os.path.join(folder(session), f"journal-{record['generation']}.jsonl"), "rb") as handle:
        return handle.read().decode("utf-8").splitlines()


def entries(session):
    return [json.loads(line) for line in journal_lines(session)[1:]]


def commands(session):
    return [entry["cmd"] for entry in entries(session)]


def snapshots(session):
    return [name for name in files(session) if name.startswith("autosave-") and name.endswith(".blend")]


def write_png(path, rgb, size=4):
    row = b"\x00" + bytes(rgb) * size
    raw = row * size

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def write_gltf(workspace, name="tri", height=1.0):
    positions = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, height, 0.0)
    with open(os.path.join(workspace, f"{name}.bin"), "wb") as handle:
        handle.write(positions)
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, height, 0]}],
        "bufferViews": [{"buffer": 0, "byteLength": len(positions)}],
        "buffers": [{"uri": f"{name}.bin", "byteLength": len(positions)}],
    }
    with open(os.path.join(workspace, f"{name}.gltf"), "w", encoding="utf-8") as handle:
        json.dump(document, handle)


def touch_later(path):
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
