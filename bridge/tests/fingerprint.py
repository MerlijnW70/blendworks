import hashlib

import bpy
import numpy

ID_COLLECTIONS = (
    "objects",
    "meshes",
    "curves",
    "materials",
    "node_groups",
    "images",
    "worlds",
    "lights",
    "cameras",
    "collections",
    "textures",
    "fonts",
)
SKIPPED = {"rna_type", "users", "session_uid", "is_evaluated", "original", "is_runtime_data", "tag", "is_missing",
           "is_dirty", "bindcode", "has_data", "pixels", "is_embedded_data", "is_editmode", "mode", "use_extra_user"}


def value_of(value):
    if isinstance(value, bpy.types.ID):
        return ("id", value.name)
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    try:
        return [value_of(item) for item in value]
    except TypeError:
        return repr(type(value))


def properties(struct):
    found = {}
    for prop in struct.bl_rna.properties:
        name = prop.identifier
        if name in SKIPPED or prop.type == "COLLECTION":
            continue
        if prop.type == "POINTER" and not isinstance(getattr(struct, name, None), bpy.types.ID):
            continue
        try:
            found[name] = value_of(getattr(struct, name))
        except (AttributeError, RuntimeError):
            continue
    return found


def digest(values):
    return hashlib.sha256(numpy.ascontiguousarray(values).tobytes()).hexdigest()


def float_digest(collection, attribute, width):
    values = numpy.empty(len(collection) * width, dtype=numpy.float32)
    collection.foreach_get(attribute, values)
    return digest(numpy.round(values, 5))


def pixel_digest(image):
    values = numpy.empty(len(image.pixels), dtype=numpy.float32)
    image.pixels.foreach_get(values)
    return digest(numpy.round(values, 5))


def tree_print(tree):
    if tree is None:
        return None
    nodes = []
    for node in sorted(tree.nodes, key=lambda n: n.name):
        inputs = [(socket.identifier, value_of(getattr(socket, "default_value", None))) for socket in node.inputs]
        nodes.append((node.name, node.bl_idname, properties(node), inputs))
    links = sorted((link.from_node.name, link.from_socket.identifier, link.to_node.name, link.to_socket.identifier) for link in tree.links)
    return {"nodes": nodes, "links": links}


def custom_properties(block):
    return {key: value_of(block[key]) for key in sorted(block.keys())}


def block_print(kind, block):
    entry = {"properties": properties(block), "custom": custom_properties(block)}
    if kind == "objects":
        entry["matrix"] = value_of(block.matrix_world)
        entry["modifiers"] = [(modifier.name, modifier.type, properties(modifier)) for modifier in block.modifiers]
        entry["constraints"] = [(constraint.name, constraint.type) for constraint in block.constraints]
        entry["slots"] = [(slot.link, slot.material.name if slot.material else None) for slot in block.material_slots]
        entry["collections"] = sorted(collection.name for collection in block.users_collection)
        entry["selected"] = block.select_get() if block.name in bpy.context.view_layer.objects else None
        entry["hidden"] = block.hide_get() if block.name in bpy.context.view_layer.objects else None
    elif kind == "meshes":
        entry["vertices"] = float_digest(block.vertices, "co", 3)
        entry["faces"] = [tuple(polygon.vertices) for polygon in block.polygons]
        entry["materials"] = [material.name if material else None for material in block.materials]
        entry["uv"] = [(layer.name, float_digest(layer.uv, "vector", 2)) for layer in block.uv_layers]
    elif kind in ("materials", "worlds", "lights", "textures") or kind == "node_groups":
        tree = block if kind == "node_groups" else getattr(block, "node_tree", None)
        entry["tree"] = tree_print(tree)
    elif kind == "images":
        entry["size"] = tuple(block.size)
        entry["pixels"] = pixel_digest(block) if block.type not in ("RENDER_RESULT", "COMPOSITING") else None
    elif kind == "curves":
        entry["splines"] = [[value_of(point.co) for point in spline.points] + [value_of(point.co) for point in spline.bezier_points] for spline in block.splines]
    elif kind == "collections":
        entry["objects"] = sorted(obj.name for obj in block.objects)
        entry["children"] = sorted(child.name for child in block.children)
    return entry


def fingerprint():
    scene = bpy.context.scene
    data = {kind: {block.name: block_print(kind, block) for block in getattr(bpy.data, kind)} for kind in ID_COLLECTIONS}
    data["scene"] = {
        "camera": scene.camera.name if scene.camera else None,
        "world": scene.world.name if scene.world else None,
        "cursor": value_of(scene.cursor.location),
        "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
        "root": sorted(obj.name for obj in scene.collection.objects),
        "children": sorted(child.name for child in scene.collection.children),
        "custom": custom_properties(scene),
    }
    return data


def differences(before, after, path="", found=None, limit=12):
    found = [] if found is None else found
    if len(found) >= limit:
        return found
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after), key=str):
            if key not in before or key not in after:
                found.append(f"{path}/{key}: only {'after' if key in after else 'before'}")
            else:
                differences(before[key], after[key], f"{path}/{key}", found, limit)
    elif before != after:
        found.append(f"{path}: {str(before)[:120]} != {str(after)[:120]}")
    return found
