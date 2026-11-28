"""Builds a node graph from a description: sockets, settings and input values."""

from .errors import bad_args
from .graph_catalog import INPUT_KEYS, KINDS, SETTING_KEYS
from .limits import MAX_RAMP_STOPS
from .nodes import Graph

VALUE_KEYS = ("number", "vector", "color", "boolean")
SETTING_TYPES = {"ENUM": "text", "STRING": "text", "BOOLEAN": "boolean", "INT": "number", "FLOAT": "number"}


def socket_names(sockets):
    return ", ".join(socket.identifier for socket in sockets if socket.enabled)


def find_socket(sockets, key, where):
    enabled = [socket for socket in sockets if socket.enabled]
    for socket in enabled:
        if socket.identifier == key:
            return socket
    named = [socket for socket in enabled if socket.name == key]
    if len(named) == 1:
        return named[0]
    if len(named) > 1:
        raise bad_args(f"{where}: {key} is ambiguous; use one of {', '.join(socket.identifier for socket in named)}")
    raise bad_args(f"{where} has no socket {key}; its sockets are {socket_names(sockets)}")


def settings_owner(node, kind):
    return getattr(node, kind.owner) if kind.owner else node


def setting_value(prop, entry, where):
    given = [key for key in SETTING_KEYS if key in entry]
    expected = SETTING_TYPES[prop.type]
    if given != [expected]:
        raise bad_args(f"{where} takes {expected}")
    value = entry[expected]
    if prop.type == "ENUM":
        choices = [item.identifier for item in prop.enum_items]
        if value not in choices:
            raise bad_args(f"{where} must be one of: {', '.join(choices)}")
    elif prop.type == "INT":
        if not float(value).is_integer():
            raise bad_args(f"{where} must be a whole number")
        value = int(value)
    if prop.type in ("INT", "FLOAT") and not prop.hard_min <= value <= prop.hard_max:
        raise bad_args(f"{where} must be between {prop.hard_min} and {prop.hard_max}")
    return value


def apply_setting(node, kind, entry, where):
    name = entry["name"]
    if name not in kind.settings:
        listed = ", ".join(kind.settings) or "none"
        raise bad_args(f"{where} has no setting {name}; its settings are: {listed}")
    owner = settings_owner(node, kind)
    value = setting_value(owner.bl_rna.properties[name], entry, f"{where} setting {name}")
    try:
        setattr(owner, name, value)
    except (TypeError, ValueError) as error:
        raise bad_args(f"{where} setting {name} refused {value}: {error}") from error


def input_value(socket, entry, where):
    expected = INPUT_KEYS.get(socket.type)
    if expected is None:
        raise bad_args(f"{where} is a {socket.type.lower()} socket and holds no value; link it instead")
    given = [key for key in VALUE_KEYS if key in entry]
    if given != [expected]:
        raise bad_args(f"{where} is a {socket.type.lower()} socket: give {expected}")
    value = entry[expected]
    if socket.type == "RGBA":
        return list(value) + [1.0] * (4 - len(value))
    if socket.type == "INT":
        if not float(value).is_integer():
            raise bad_args(f"{where} must be a whole number")
        return int(value)
    return value


def apply_input(node, kind, entry, where, seen):
    sockets = node.outputs if kind.output_value else node.inputs
    socket = find_socket(sockets, entry["socket"], where)
    if socket.identifier in seen:
        raise bad_args(f"{where}: {socket.identifier} is given twice")
    seen.add(socket.identifier)
    value = input_value(socket, entry, f"{where}.{socket.identifier}")
    try:
        socket.default_value = value
    except (TypeError, ValueError) as error:
        raise bad_args(f"{where}.{socket.identifier} refused {value}: {error}") from error


def apply_stops(node, stops, where):
    if len(stops) < 2 or len(stops) > MAX_RAMP_STOPS:
        raise bad_args(f"{where} needs 2 to {MAX_RAMP_STOPS} stops")
    positions = [stop["position"] for stop in stops]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise bad_args(f"{where}: stop positions must rise strictly")
    elements = node.color_ramp.elements
    while len(elements) > len(stops):
        elements.remove(elements[-1])
    while len(elements) < len(stops):
        elements.new(1.0)
    for element, stop in zip(elements, stops):
        element.position = stop["position"]
        element.color = list(stop["color"]) + [1.0] * (4 - len(stop["color"]))


def make_node(tree, spec, names, where):
    name = spec["name"]
    if name in names:
        raise bad_args(f"{where}: the node name {name} is used twice")
    kind = KINDS[spec["type"]]
    node = tree.nodes.new(kind.idname)
    node.name = name
    names[name] = node
    if "stops" in spec and not kind.stops:
        raise bad_args(f"{where}: only a color_ramp has stops")
    for entry in spec.get("settings", []):
        apply_setting(node, kind, entry, where)
    seen = set()
    for entry in spec.get("inputs", []):
        apply_input(node, kind, entry, where, seen)
    if "stops" in spec:
        apply_stops(node, spec["stops"], where)
    return node


def compatible(source, target):
    if (source.type == "SHADER") != (target.type == "SHADER"):
        return False
    if "ROTATION" in (source.type, target.type):
        return source.type == target.type
    return True


def add_link(tree, names, link, where):
    ends = []
    for side, sockets_of in (("from", "outputs"), ("to", "inputs")):
        node = names.get(link[f"{side}_node"])
        if node is None:
            raise bad_args(f"{where}: no node named {link[f'{side}_node']}")
        ends.append((node, find_socket(getattr(node, sockets_of), link[f"{side}_socket"], f"{where}: {node.name}")))
    (source_node, source), (target_node, target) = ends
    if not compatible(source, target):
        raise bad_args(f"{where}: cannot link the {source.type.lower()} output {source_node.name}.{source.identifier} to the {target.type.lower()} input {target_node.name}.{target.identifier}")
    if target.is_linked:
        raise bad_args(f"{where}: {target_node.name}.{target.identifier} already has a link")
    tree.links.new(source, target)


def check_acyclic(nodes, links):
    waiting = {node["name"]: 0 for node in nodes}
    following = {name: [] for name in waiting}
    for link in links:
        source, target = link["from_node"], link["to_node"]
        if source in waiting and target in waiting:
            following[source].append(target)
            waiting[target] += 1
    ready = [name for name, count in waiting.items() if count == 0]
    done = 0
    while ready:
        name = ready.pop()
        done += 1
        for after in following[name]:
            waiting[after] -= 1
            if waiting[after] == 0:
                ready.append(after)
    if done != len(waiting):
        stuck = sorted(name for name, count in waiting.items() if count > 0)
        raise bad_args(f"the links form a cycle through {', '.join(stuck)}")


def build_graph(tree, nodes, links):
    names = {}
    for index, spec in enumerate(nodes):
        make_node(tree, spec, names, f"nodes[{index}] {spec['name']}")
    outputs = [node for node in names.values() if node.bl_idname == KINDS["material_output"].idname]
    if len(outputs) != 1:
        raise bad_args(f"give exactly one material_output node, not {len(outputs)}")
    check_acyclic(nodes, links)
    for index, link in enumerate(links):
        add_link(tree, names, link, f"links[{index}]")
    if not outputs[0].inputs["Surface"].is_linked:
        raise bad_args("link a shader into the Surface of the material_output node")
    Graph(tree).layout()
