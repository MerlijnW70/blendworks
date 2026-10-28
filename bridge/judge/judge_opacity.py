import numpy as np

from judge_textures import group_output, socket_by_identifier

TRANSPARENT = 1.0 / 255.0
MAX_DEPTH = 32
OPAQUE = 1.0


def source(socket, context, depth=0):
    if socket is None or depth > MAX_DEPTH:
        return None
    links = [link for link in socket.links if link.is_valid and not link.is_muted]
    if not links:
        return None
    link = links[0]
    node = link.from_node
    if node.mute:
        inner = next((internal.from_socket for internal in node.internal_links if internal.to_socket == link.from_socket), None)
        return source(inner, context, depth + 1) if inner is not None else ("muted", node, link.from_socket, context)
    if node.type == "REROUTE":
        return source(node.inputs[0], context, depth + 1)
    if node.type == "GROUP":
        output = group_output(node.node_tree) if node.node_tree is not None else None
        inner = socket_by_identifier(output.inputs, link.from_socket.identifier) if output is not None else None
        return source(inner, context + (node,), depth + 1) if inner is not None else None
    if node.type == "GROUP_INPUT":
        if not context:
            return None
        outer = socket_by_identifier(context[-1].inputs, link.from_socket.identifier)
        return value_source(outer, context[:-1], depth + 1)
    return ("node", node, link.from_socket, context)


def value_source(socket, context, depth):
    found = source(socket, context, depth)
    return found if found is not None else ("value", socket, None, context)


def input_named(node, name):
    return node.inputs.get(name)


def unlinked_value(socket):
    value = getattr(socket, "default_value", None)
    if value is None:
        return None
    try:
        return [float(item) for item in value]
    except TypeError:
        return [float(value)]


class OpacityReader:
    def __init__(self):
        self.images = {}
        self.materials = {}

    def material(self, material):
        if material is None:
            return OPAQUE
        key = material.as_pointer()
        if key not in self.materials:
            self.materials[key] = self.read_material(material)
        return self.materials[key]

    def read_material(self, material):
        tree = material.node_tree
        if tree is None:
            return OPAQUE
        output = tree.get_output_node("CYCLES")
        if output is None:
            return OPAQUE
        found = source(output.inputs.get("Surface"), ())
        return OPAQUE if found is None else self.shader(found, 0)

    def shader(self, found, depth):
        kind, node, _, context = found
        if kind != "node" or depth > MAX_DEPTH:
            return OPAQUE
        if node.type == "HOLDOUT":
            return 0.0
        if node.type == "BSDF_TRANSPARENT":
            colour = self.constant(input_named(node, "Color"), context)
            return OPAQUE if colour is None else max(0.0, 1.0 - min(colour[:3]))
        if node.type == "BSDF_PRINCIPLED":
            return min(OPAQUE, max(0.0, self.upper(input_named(node, "Alpha"), context, depth)))
        if node.type in ("MIX_SHADER", "ADD_SHADER"):
            return self.combined(node, context, depth)
        return OPAQUE

    def combined(self, node, context, depth):
        shaders = [socket for socket in node.inputs if socket.type == "SHADER"]
        values = []
        for socket in shaders[:2]:
            found = source(socket, context)
            values.append(0.0 if found is None and node.type == "ADD_SHADER" else (OPAQUE if found is None else self.shader(found, depth + 1)))
        while len(values) < 2:
            values.append(OPAQUE)
        if node.type == "ADD_SHADER":
            return max(values)
        factor_socket = node.inputs[0]
        factor = source(factor_socket, context)
        if factor is None:
            weight = min(1.0, max(0.0, unlinked_value(factor_socket)[0]))
            return (1.0 - weight) * values[0] + weight * values[1]
        if factor[0] == "node" and factor[1].type == "LIGHT_PATH" and factor[2].identifier == "Is Camera Ray":
            return values[1]
        return max(values)

    def constant(self, socket, context):
        if socket is None:
            return None
        found = source(socket, context)
        if found is None:
            return unlinked_value(socket)
        if found[0] == "value":
            return unlinked_value(found[1])
        return None

    def upper(self, socket, context, depth):
        if socket is None or depth > MAX_DEPTH:
            return OPAQUE
        found = source(socket, context)
        if found is None:
            value = unlinked_value(socket)
            return OPAQUE if value is None else value[0]
        kind, node, from_socket, inner = found
        if kind == "value":
            value = unlinked_value(node)
            return OPAQUE if value is None else value[0]
        if kind != "node":
            return OPAQUE
        if node.type == "TEX_IMAGE" and from_socket.identifier == "Alpha":
            return self.image_alpha(node.image)
        if node.type == "MATH" and node.operation == "MULTIPLY" and not node.use_clamp:
            first, second = node.inputs[0], node.inputs[1]
            return max(0.0, min(OPAQUE, self.upper(first, inner, depth + 1))) * max(0.0, min(OPAQUE, self.upper(second, inner, depth + 1)))
        if node.type == "VALUE":
            return float(from_socket.default_value)
        return OPAQUE

    def image_alpha(self, image):
        if image is None:
            return OPAQUE
        key = image.as_pointer()
        if key not in self.images:
            self.images[key] = self.read_alpha(image)
        return self.images[key]

    def read_alpha(self, image):
        if image.alpha_mode == "NONE":
            return OPAQUE
        width, height = (int(value) for value in image.size[:])
        channels = int(image.channels)
        if width == 0 or height == 0 or channels < 4:
            return OPAQUE
        pixels = np.empty(width * height * channels, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        return float(pixels[3::channels].max())


def transparent(opacity):
    return opacity <= TRANSPARENT
