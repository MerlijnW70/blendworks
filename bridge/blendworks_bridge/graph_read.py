import bpy

from .graph_build import settings_owner
from .graph_catalog import BY_IDNAME, INPUT_KEYS, KINDS
from .util import rounded

CHECK_TREE = "blendworks_defaults"


def plain(value):
    if isinstance(value, float):
        return rounded(value)
    if isinstance(value, (int, str, bool)):
        return value
    return [rounded(item) for item in value]


def socket_value(socket):
    return plain(socket.default_value)


def fresh_nodes(tree, types):
    return {name: tree.nodes.new(KINDS[name].idname) for name in types}


def changed_settings(node, kind, fresh):
    entries = []
    for name in kind.settings:
        owner, base = settings_owner(node, kind), settings_owner(fresh, kind)
        value = plain(getattr(owner, name))
        if value == plain(getattr(base, name)):
            continue
        key = "text" if isinstance(value, str) else "boolean" if isinstance(value, bool) else "number"
        entries.append({"name": name, key: value})
    return entries


def input_entry(socket, base):
    key = INPUT_KEYS.get(socket.type)
    if key is None or socket.is_linked or not socket.enabled:
        return None
    value = socket_value(socket)
    if value == socket_value(base):
        return None
    return {"socket": socket.identifier, key: value}


def changed_inputs(node, kind, fresh):
    if kind.output_value:
        pairs = zip(node.outputs, fresh.outputs)
    else:
        pairs = zip(node.inputs, fresh.inputs)
    return [entry for entry in (input_entry(socket, base) for socket, base in pairs) if entry is not None]


def node_entry(node, fresh):
    name = BY_IDNAME[node.bl_idname]
    kind = KINDS[name]
    entry = {"name": node.name, "type": name}
    inputs = changed_inputs(node, kind, fresh)
    if inputs:
        entry["inputs"] = inputs
    settings = changed_settings(node, kind, fresh)
    if settings:
        entry["settings"] = settings
    if kind.stops:
        entry["stops"] = [{"position": plain(element.position), "color": plain(element.color)} for element in node.color_ramp.elements]
    return entry


def link_entry(link):
    return {
        "from_node": link.from_node.name,
        "from_socket": link.from_socket.identifier,
        "to_node": link.to_node.name,
        "to_socket": link.to_socket.identifier,
    }


def read_graph(material):
    tree = material.node_tree
    if tree is None:
        return {"editable": False, "reason": "the material has no node tree"}
    unsupported = [{"name": node.name, "type": node.bl_idname} for node in tree.nodes if node.bl_idname not in BY_IDNAME]
    if unsupported:
        return {"editable": False, "reason": "the material uses nodes that material_nodes does not offer", "unsupported": unsupported}
    scratch = bpy.data.node_groups.new(CHECK_TREE, "ShaderNodeTree")
    try:
        fresh = fresh_nodes(scratch, {BY_IDNAME[node.bl_idname] for node in tree.nodes})
        nodes = [node_entry(node, fresh[BY_IDNAME[node.bl_idname]]) for node in tree.nodes]
    finally:
        bpy.data.node_groups.remove(scratch)
    return {"editable": True, "nodes": nodes, "links": [link_entry(link) for link in tree.links]}
