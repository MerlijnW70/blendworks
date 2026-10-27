import bpy

COLUMN_WIDTH = 260.0
ROW_HEIGHT = 220.0
MIX_SOCKETS = {
    "FLOAT": ("A_Float", "B_Float", "Result_Float"),
    "RGBA": ("A_Color", "B_Color", "Result_Color"),
    "VECTOR": ("A_Vector", "B_Vector", "Result_Vector"),
}


def find_socket(sockets, key):
    if isinstance(key, int):
        return sockets[key]
    for socket in sockets:
        if socket.identifier == key and socket.enabled:
            return socket
    for socket in sockets:
        if socket.name == key and socket.enabled:
            return socket
    raise KeyError(key)


class Graph:
    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links

    def node(self, kind, inputs=None, **properties):
        node = self.nodes.new(kind)
        for name, value in properties.items():
            setattr(node, name, value)
        for key, value in (inputs or {}).items():
            self.set(find_socket(node.inputs, key), value)
        return node

    def set(self, socket, value):
        if value is None:
            return
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, socket)
            return
        if socket.type == "RGBA" and isinstance(value, (list, tuple)) and len(value) == 3:
            value = list(value) + [1.0]
        if socket.type in ("RGBA", "VECTOR") and isinstance(value, (int, float)):
            value = [float(value)] * len(socket.default_value)
        socket.default_value = value

    def math(self, operation, first, second=None, third=None, clamp=False):
        node = self.node("ShaderNodeMath", operation=operation, use_clamp=clamp)
        self.set(node.inputs[0], first)
        self.set(node.inputs[1], second)
        self.set(node.inputs[2], third)
        return node.outputs[0]

    def vector_math(self, operation, first, second=None, scale=None):
        node = self.node("ShaderNodeVectorMath", operation=operation)
        self.set(node.inputs[0], first)
        self.set(node.inputs[1], second)
        if scale is not None:
            self.set(find_socket(node.inputs, "Scale"), scale)
        return node.outputs["Value" if operation in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else "Vector"]

    def mix(self, factor, first, second, data_type="RGBA", blend="MIX", clamp=True):
        node = self.node("ShaderNodeMix", data_type=data_type, blend_type=blend, clamp_factor=clamp)
        first_key, second_key, result_key = MIX_SOCKETS[data_type]
        self.set(find_socket(node.inputs, "Factor_Float"), factor)
        self.set(find_socket(node.inputs, first_key), first)
        self.set(find_socket(node.inputs, second_key), second)
        return find_socket(node.outputs, result_key)

    def map_range(self, value, from_min, from_max, to_min=0.0, to_max=1.0, interpolation="LINEAR"):
        node = self.node("ShaderNodeMapRange", interpolation_type=interpolation, clamp=True)
        for key, item in (("Value", value), ("From Min", from_min), ("From Max", from_max), ("To Min", to_min), ("To Max", to_max)):
            self.set(find_socket(node.inputs, key), item)
        return find_socket(node.outputs, "Result")

    def noise(self, vector, scale, detail=2.0, roughness=0.5, distortion=0.0, lacunarity=2.0):
        node = self.node(
            "ShaderNodeTexNoise",
            {"Vector": vector, "Scale": scale, "Detail": detail, "Roughness": roughness, "Distortion": distortion, "Lacunarity": lacunarity},
            noise_dimensions="3D",
        )
        return node

    def voronoi(self, vector, scale, randomness=1.0, feature="F1", distance="EUCLIDEAN"):
        return self.node(
            "ShaderNodeTexVoronoi",
            {"Vector": vector, "Scale": scale, "Randomness": randomness},
            voronoi_dimensions="3D",
            feature=feature,
            distance=distance,
        )

    def wave(self, vector, scale, distortion, detail, direction, kind="BANDS", profile="SIN"):
        node = self.node("ShaderNodeTexWave", {"Vector": vector, "Scale": scale, "Distortion": distortion, "Detail": detail}, wave_type=kind, wave_profile=profile)
        if kind == "BANDS":
            node.bands_direction = direction
        else:
            node.rings_direction = direction
        return node

    def ramp(self, factor, stops):
        node = self.node("ShaderNodeValToRGB")
        elements = node.color_ramp.elements
        while len(elements) > len(stops):
            elements.remove(elements[-1])
        while len(elements) < len(stops):
            elements.new(1.0)
        for element, (position, color) in zip(elements, stops):
            element.position = position
            element.color = list(color) + [1.0] * (4 - len(color))
        self.set(node.inputs[0], factor)
        return node.outputs["Color"]

    def value(self, number):
        node = self.node("ShaderNodeValue")
        node.outputs[0].default_value = number
        return node.outputs[0]

    def rgb(self, color):
        node = self.node("ShaderNodeRGB")
        node.outputs[0].default_value = list(color) + [1.0] * (4 - len(color))
        return node.outputs[0]

    def source_of(self, socket):
        if socket.is_linked:
            return socket.links[0].from_socket
        if socket.type == "RGBA":
            return self.rgb(list(socket.default_value))
        if socket.type == "VECTOR":
            return None
        return self.value(socket.default_value)

    def layout(self):
        depth = {}

        def column(node, seen):
            key = node.as_pointer()
            if key in depth:
                return depth[key]
            if key in seen:
                return 0
            seen.add(key)
            consumers = [link.to_node for link in self.links if link.from_node == node]
            depth[key] = 0 if not consumers else 1 + max(column(consumer, seen) for consumer in consumers)
            return depth[key]

        rows = {}
        for node in self.nodes:
            level = column(node, set())
            row = rows.get(level, 0)
            rows[level] = row + 1
            node.location = (-COLUMN_WIDTH * level, -ROW_HEIGHT * row)
