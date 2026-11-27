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
    write_blend(partial, compress=False)
    return partial


def save_atomically(path, previous=None):
    partial = write_copy(path)
    if previous is not None and os.path.isfile(path):
        os.replace(path, previous)
    os.replace(partial, path)
    return os.path.getsize(path)


UI_DATA = ("window_managers", "screens", "workspaces")
NOT_PIXELS = ("RENDER_RESULT", "COMPOSITING")


def id_collections():
    names = []
    for prop in bpy.data.bl_rna.properties:
        if prop.type != "COLLECTION" or prop.identifier in UI_DATA:
            continue
        kind = getattr(bpy.types, prop.fixed_type.identifier, None)
        if isinstance(kind, type) and issubclass(kind, bpy.types.ID):
            names.append(prop.identifier)
    return names


def unused_blocks():
    found = []
    for name in id_collections():
        for block in getattr(bpy.data, name):
            if block.users == 0 and not block.use_fake_user and block.library is None and not block.is_runtime_data:
                found.append((name, block))
    return found


def unsaved_images():
    return sorted(
        image.name for image in bpy.data.images
        if image.type not in NOT_PIXELS and image.is_dirty and image.has_data and image.packed_file is None
    )


def write_snapshot(path):
    unused = unused_blocks()
    for _, block in unused:
        block.use_fake_user = True
    try:
        write_blend(path, compress=True)
    finally:
        for _, block in unused:
            block.use_fake_user = False
    return [[name, block.name] for name, block in unused], unsaved_images()


def write_blend(path, compress):
    try:
        bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, check_existing=False, compress=compress)
    except RuntimeError as error:
        remove_quietly(path)
        raise failed(f"Blender could not save {os.path.basename(path)}: {error}") from error
    if not looks_like_blend(path):
        remove_quietly(path)
        raise failed(f"saving {os.path.basename(path)} wrote no .blend file")


def open_snapshot(path, unused):
    open_blend(path)
    for name, block_name in unused:
        collection = getattr(bpy.data, name, None)
        block = collection.get(block_name) if collection is not None else None
        if block is not None and block.use_fake_user:
            block.use_fake_user = False


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
