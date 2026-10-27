import json
import os

import bpy

from .errors import failed

BLEND_MAGIC = b"BLENDER"
COMPRESSED_MAGICS = (b"\x28\xb5\x2f\xfd", b"\x1f\x8b")


def looks_like_blend(path):
    try:
        with open(path, "rb") as handle:
            head = handle.read(7)
    except OSError:
        return False
    return head == BLEND_MAGIC or head[:4] in COMPRESSED_MAGICS or head[:2] in COMPRESSED_MAGICS


def partial_path(path):
    folder, name = os.path.split(path)
    return os.path.join(folder, f".{name}.partial.blend")


def write_copy(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    partial = partial_path(path)
    remove_quietly(partial)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=partial, copy=True, check_existing=False, compress=False)
    except RuntimeError as error:
        remove_quietly(partial)
        raise failed(f"Blender could not save {os.path.basename(path)}: {error}") from error
    if not looks_like_blend(partial):
        remove_quietly(partial)
        raise failed(f"saving {os.path.basename(path)} wrote no .blend file")
    return partial


def save_atomically(path, previous=None):
    partial = write_copy(path)
    if previous is not None and os.path.isfile(path):
        os.replace(path, previous)
    os.replace(partial, path)
    return os.path.getsize(path)


def write_json_atomically(path, value):
    partial = f"{path}.partial"
    with open(partial, "w", encoding="utf-8") as handle:
        json.dump(value, handle)
    os.replace(partial, path)


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def open_blend(path):
    if not looks_like_blend(path):
        raise failed(f"{os.path.basename(path)} is not a .blend file")
    try:
        result = bpy.ops.wm.open_mainfile(filepath=path, load_ui=False, use_scripts=False, display_file_selector=False)
    except RuntimeError as error:
        raise failed(f"Blender could not open {os.path.basename(path)}: {error}") from error
    if "FINISHED" not in result:
        raise failed(f"Blender could not open {os.path.basename(path)}")


def remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
