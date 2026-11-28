"""Atomic saving of .blend files and the data blocks that are unused or unsaved."""

import hashlib
import json
import os
import re

import bpy
import numpy

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


SKIPPED_PROPERTIES = {
    "rna_type", "name", "name_full", "users", "session_uid", "is_evaluated", "original", "use_fake_user", "use_extra_user",
    "tag", "is_runtime_data", "is_missing", "is_library_indirect", "library", "library_weak_reference", "asset_data",
    "override_library", "preview", "is_embedded_data", "is_editmode", "bindcode", "is_dirty", "has_data", "pixels",
    "packed_file", "packed_files", "select", "frame_duration", "id_type", "display_name",
}
SUFFIX = re.compile(r"^(.*)\.\d{3,}$")
MERGED_KINDS = ("materials", "node_groups", "images")


def base_name(name):
    match = SUFFIX.match(name)
    return match.group(1) if match else name


def value_digest(value, seen):
    if isinstance(value, bpy.types.ID):
        return content_digest(value, seen)
    if isinstance(value, (bool, int, float, str)) or value is None:
        return repr(value)
    if isinstance(value, (set, frozenset)):
        return repr(sorted(value))
    try:
        return "[" + ",".join(value_digest(item, seen) for item in value) + "]"
    except TypeError:
        return type(value).__name__


def properties_digest(struct, seen):
    parts = []
    for prop in struct.bl_rna.properties:
        name = prop.identifier
        if name in SKIPPED_PROPERTIES or prop.type == "COLLECTION":
            continue
        try:
            value = getattr(struct, name)
        except (AttributeError, RuntimeError):
            continue
        if prop.type == "POINTER" and not isinstance(value, bpy.types.ID):
            continue
        parts.append(f"{name}={value_digest(value, seen)}")
    return ";".join(parts)


def interface_digest(tree):
    interface = getattr(tree, "interface", None)
    if interface is None:
        return ""
    return "|".join(f"{item.item_type}:{getattr(item, 'in_out', '')}:{getattr(item, 'socket_type', '')}:{item.name}" for item in interface.items_tree)


def tree_digest(tree, seen):
    if tree is None:
        return "-"
    nodes = []
    for node in sorted(tree.nodes, key=lambda item: item.name):
        sockets = ",".join(f"{socket.identifier}={value_digest(getattr(socket, 'default_value', None), seen)}" for socket in node.inputs)
        nodes.append(f"{node.name}:{node.bl_idname}:{properties_digest(node, seen)}:{sockets}")
    links = sorted(f"{link.from_node.name}.{link.from_socket.identifier}>{link.to_node.name}.{link.to_socket.identifier}:{link.is_muted}" for link in tree.links)
    return "|".join(nodes) + "#" + "|".join(links) + "#" + interface_digest(tree)


def image_digest(image):
    digest = hashlib.sha256(properties_digest(image, set()).encode("utf-8"))
    digest.update(repr(tuple(image.size)).encode("ascii"))
    for packed in image.packed_files:
        digest.update(bytes(packed.data))
    if image.has_data and (image.is_dirty or image.source == "GENERATED"):
        pixels = numpy.empty(len(image.pixels), dtype=numpy.float32)
        image.pixels.foreach_get(pixels)
        digest.update(pixels.tobytes())
    return digest.hexdigest()


def content_digest(block, seen=None):
    """The content of a material, node group or image by value and without its name, so two copies of one data-block
    appended from different files compare equal."""
    seen = set() if seen is None else seen
    key = (type(block).__name__, block.as_pointer())
    if key in seen:
        return f"cycle:{type(block).__name__}"
    seen.add(key)
    if isinstance(block, bpy.types.Image):
        text = image_digest(block)
    elif isinstance(block, bpy.types.NodeTree):
        text = block.bl_idname + "@" + tree_digest(block, seen)
    elif hasattr(block, "node_tree"):
        text = properties_digest(block, seen) + "@" + tree_digest(block.node_tree, seen)
    else:
        text = type(block).__name__ + "@" + properties_digest(block, seen)
    seen.discard(key)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_objects(path, objects):
    partial = partial_path(path)
    remove_quietly(partial)
    bpy.data.libraries.write(partial, set(objects), fake_user=False, compress=False)
    os.replace(partial, path)


def load_seed(path, scene):
    with bpy.data.libraries.load(path, link=False) as (source, target):
        for kind in ("objects", "materials", "node_groups", "images"):
            setattr(target, kind, list(getattr(source, kind)))
    for obj in target.objects:
        if obj is not None and obj.name not in scene.collection.objects:
            scene.collection.objects.link(obj)


def object_state(objects, view_layer):
    master = view_layer.layer_collection.collection
    state = {}
    for obj in objects:
        shown = obj.name in view_layer.objects
        state[obj.name] = {
            "collections": sorted("" if collection == master else collection.name for collection in obj.users_collection),
            "hidden": bool(shown and obj.hide_get(view_layer=view_layer)),
            "selected": bool(shown and obj.select_get(view_layer=view_layer)),
        }
    active = view_layer.objects.active
    return {"objects": state, "active": active.name if active is not None and active.name in state else None}


def remove_objects(objects):
    for obj in objects:
        bpy.data.objects.remove(obj)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)


def merge_objects(path, record, scene, view_layer):
    """Append the objects of a worker's task as the serial build would have made them, in the same collections and
    view-layer state. A material that takes the name of one the scene already holds is the one the commands would have
    reused by name, so it is merged onto it (and reported when its content differs). Images and node groups equal in
    content to ones the scene holds are merged onto them; appended ones left without users are removed."""
    before = {kind: {block.as_pointer() for block in getattr(bpy.data, kind)} for kind in MERGED_KINDS}
    with bpy.data.libraries.load(path, link=False) as (source, target):
        target.objects = list(source.objects)
    appended = [obj for obj in target.objects if obj is not None]
    link_like(appended, record, scene, view_layer)
    report = {"materials_reused": 0, "materials_differing": [], "images_merged": 0, "node_groups_merged": 0}
    for material in [block for block in bpy.data.materials if block.as_pointer() not in before["materials"]]:
        existing = bpy.data.materials.get(base_name(material.name))
        if existing is None or existing.as_pointer() not in before["materials"]:
            continue
        if content_digest(material) != content_digest(existing):
            report["materials_differing"].append(existing.name)
        material.user_remap(existing)
        bpy.data.materials.remove(material)
        report["materials_reused"] += 1
    for kind, counter in (("node_groups", "node_groups_merged"), ("images", "images_merged")):
        report[counter] = merge_by_content(getattr(bpy.data, kind), before[kind])
    return appended, report


def merge_by_content(collection, before):
    known = {}
    for block in collection:
        if block.as_pointer() in before:
            known.setdefault(content_digest(block), block)
    merged = 0
    for block in [item for item in collection if item.as_pointer() not in before]:
        if block.users - int(block.use_fake_user) <= 0:
            collection.remove(block)
            continue
        twin = known.get(content_digest(block))
        if twin is None:
            continue
        block.user_remap(twin)
        collection.remove(block)
        merged += 1
    return merged


def link_like(objects, record, scene, view_layer):
    state = record["objects"]
    for obj in objects:
        for name in state.get(obj.name, {}).get("collections", [""]):
            collection = scene.collection if name == "" else bpy.data.collections.get(name)
            if collection is None:
                collection = bpy.data.collections.new(name)
                scene.collection.children.link(collection)
            if obj.name not in collection.objects:
                collection.objects.link(obj)
    view_layer.update()
    for other in view_layer.objects:
        other.select_set(False, view_layer=view_layer)
    for obj in objects:
        entry = state.get(obj.name)
        if entry is not None and obj.name in view_layer.objects:
            obj.hide_set(entry["hidden"], view_layer=view_layer)
            obj.select_set(entry["selected"], view_layer=view_layer)
    if record.get("active") in view_layer.objects:
        view_layer.objects.active = view_layer.objects[record["active"]]
