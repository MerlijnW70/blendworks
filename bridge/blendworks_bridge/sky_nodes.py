"""Node graph helper for the sky shader."""

class Graph:
    """Small helpers that build shader node graphs from sockets and constants."""

    def __init__(self, tree, x=-2000, y=0):
        self.tree = tree
        self.x = x
        self.y = y
        self.count = 0

    def node(self, kind, name=None):
        node = self.tree.nodes.new(kind)
        if name is not None:
            node.name = name
            node.label = name
        self.count += 1
        node.location = (self.x + 180 * (self.count % 12), self.y - 160 * (self.count // 12))
        return node

    def feed(self, socket, value):
        if value is None:
            return
        if hasattr(value, "is_output"):
            self.tree.links.new(value, socket)
        elif isinstance(value, (tuple, list)):
            current = socket.default_value
            values = list(value) + [1.0] * (len(current) - len(value))
            socket.default_value = values[: len(current)]
        else:
            socket.default_value = value

    def math(self, operation, a, b=None, c=None, clamp=False):
        node = self.node("ShaderNodeMath")
        node.operation = operation
        node.use_clamp = clamp
        for index, value in enumerate((a, b, c)):
            self.feed(node.inputs[index], value)
        return node.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def div(self, a, b):
        return self.math("DIVIDE", a, b)

    def madd(self, a, b, c):
        return self.math("MULTIPLY_ADD", a, b, c)

    def clamp01(self, a):
        return self.math("MULTIPLY", a, 1.0, clamp=True)

    def maximum(self, a, b):
        return self.math("MAXIMUM", a, b)

    def minimum(self, a, b):
        return self.math("MINIMUM", a, b)

    def power(self, a, b):
        return self.math("POWER", a, b)

    def exp(self, a):
        return self.math("EXPONENT", a)

    def smooth(self, low, high, value):
        node = self.node("ShaderNodeMapRange")
        node.interpolation_type = "SMOOTHSTEP"
        node.clamp = True
        self.feed(node.inputs["Value"], value)
        self.feed(node.inputs["From Min"], low)
        self.feed(node.inputs["From Max"], high)
        node.inputs["To Min"].default_value = 0.0
        node.inputs["To Max"].default_value = 1.0
        return node.outputs["Result"]

    def remap(self, value, low, high, to_low=0.0, to_high=1.0, clamp=True):
        node = self.node("ShaderNodeMapRange")
        node.clamp = clamp
        self.feed(node.inputs["Value"], value)
        self.feed(node.inputs["From Min"], low)
        self.feed(node.inputs["From Max"], high)
        self.feed(node.inputs["To Min"], to_low)
        self.feed(node.inputs["To Max"], to_high)
        return node.outputs["Result"]

    def separate(self, vector):
        node = self.node("ShaderNodeSeparateXYZ")
        self.feed(node.inputs[0], vector)
        return node.outputs["X"], node.outputs["Y"], node.outputs["Z"]

    def combine(self, x, y, z):
        node = self.node("ShaderNodeCombineXYZ")
        for index, value in enumerate((x, y, z)):
            self.feed(node.inputs[index], value)
        return node.outputs[0]

    def vector(self, operation, a, b=None, scale=None):
        node = self.node("ShaderNodeVectorMath")
        node.operation = operation
        self.feed(node.inputs[0], a)
        if b is not None:
            self.feed(node.inputs[1], b)
        if scale is not None:
            self.feed(node.inputs["Scale"], scale)
        return node.outputs["Value"] if operation in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else node.outputs["Vector"]

    def noise(self, vector, scale, detail, roughness=0.5, lacunarity=2.0, distortion=0.0, name=None):
        node = self.node("ShaderNodeTexNoise", name)
        node.noise_dimensions = "3D"
        node.normalize = True
        self.feed(node.inputs["Vector"], vector)
        self.feed(node.inputs["Scale"], scale)
        node.inputs["Detail"].default_value = detail
        node.inputs["Roughness"].default_value = roughness
        node.inputs["Lacunarity"].default_value = lacunarity
        node.inputs["Distortion"].default_value = distortion
        return node.outputs["Factor"]

    def voronoi(self, vector, scale, randomness=1.0):
        node = self.node("ShaderNodeTexVoronoi")
        node.voronoi_dimensions = "3D"
        node.feature = "F1"
        node.distance = "EUCLIDEAN"
        self.feed(node.inputs["Vector"], vector)
        self.feed(node.inputs["Scale"], scale)
        node.inputs["Randomness"].default_value = randomness
        return node.outputs["Distance"]

    def mix(self, factor, a, b, blend="MIX"):
        node = self.node("ShaderNodeMix")
        node.data_type = "RGBA"
        node.blend_type = blend
        node.clamp_factor = False
        self.feed(node.inputs["Factor"], factor)
        self.feed(node.inputs[6], a)
        self.feed(node.inputs[7], b)
        return node.outputs[2]

    def mix_value(self, factor, a, b):
        node = self.node("ShaderNodeMix")
        node.data_type = "FLOAT"
        node.clamp_factor = False
        self.feed(node.inputs["Factor"], factor)
        self.feed(node.inputs[2], a)
        self.feed(node.inputs[3], b)
        return node.outputs[0]

    def scale_colour(self, colour, factor):
        return self.mix(1.0, colour, self.gray(factor), "MULTIPLY")

    def gray(self, value):
        node = self.node("ShaderNodeCombineColor")
        for index in range(3):
            self.feed(node.inputs[index], value)
        return node.outputs[0]

    def rgb(self, colour):
        node = self.node("ShaderNodeRGB")
        node.outputs[0].default_value = list(colour) + [1.0]
        return node.outputs[0]

    def value(self, number, name=None):
        node = self.node("ShaderNodeValue", name)
        node.outputs[0].default_value = number
        return node.outputs[0]
