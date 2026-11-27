import bpy

from .rig import TEMPORARY_PREFIX

CLAY = (0.6, 0.6, 0.6, 1.0)
CLAY_ROUGHNESS = 0.65
LINE = (0.02, 0.02, 0.025, 1.0)
DEFAULT_WIRE_WIDTH = 1.5
OUTSIDE_EDGE = 1e9
FADE_START = 0.5
FADE_SPAN = 1.5
CORNER_ATTRIBUTE = "bw_wire_corner"
EDGE_ATTRIBUTES = ("bw_wire_edge_a", "bw_wire_edge_b")
TINY = 1e-12


def temporary_material(name):
    material = bpy.data.materials.new(TEMPORARY_PREFIX + name)
    if not material.node_tree:
        material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    return material, nodes, material.node_tree.links, output


class Shader:
    """Builds the nodes of one shader graph."""

    def __init__(self, tree):
        self.nodes = tree.nodes
        self.links = tree.links

    def feed(self, socket, value):
        if isinstance(value, (int, float)):
            socket.default_value = value
        else:
            self.links.new(value, socket)

    def math(self, operation, a, b=None, clamp=False):
        node = self.nodes.new("ShaderNodeMath")
        node.operation = operation
        node.use_clamp = clamp
        self.feed(node.inputs[0], a)
        if b is not None:
            self.feed(node.inputs[1], b)
        return node.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b, clamp=False):
        return self.math("SUBTRACT", a, b, clamp)

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def div(self, a, b, clamp=False):
        return self.math("DIVIDE", a, self.math("MAXIMUM", b, TINY), clamp)

    def hypot(self, x, y):
        return self.math("SQRT", self.add(self.mul(x, x), self.mul(y, y)))

    def separate(self, vector):
        node = self.nodes.new("ShaderNodeSeparateXYZ")
        self.links.new(vector, node.inputs[0])
        return node.outputs[0], node.outputs[1], node.outputs[2]

    def attribute(self, name):
        node = self.nodes.new("ShaderNodeAttribute")
        node.attribute_type = "GEOMETRY"
        node.attribute_name = name
        return node.outputs["Vector"]

    def to_camera(self, vector):
        node = self.nodes.new("ShaderNodeVectorTransform")
        node.vector_type = "VECTOR"
        node.convert_from = "OBJECT"
        node.convert_to = "CAMERA"
        self.links.new(vector, node.inputs[0])
        return node.outputs[0]


def shader_group(name):
    """A temporary shader node group with one Shader output: what a view puts in place of every surface closure."""
    tree = bpy.data.node_groups.new(TEMPORARY_PREFIX + name, "ShaderNodeTree")
    tree.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    output = tree.nodes.new("NodeGroupOutput")
    return tree, Shader(tree), output


def clay_shader(nodes):
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = CLAY_ROUGHNESS
    shader.inputs["Base Color"].default_value = CLAY
    return shader


def clay_group():
    """The one clay definition of render_preview and render_final: matte neutral grey."""
    tree, build, output = shader_group("clay")
    shader = clay_shader(build.nodes)
    build.links.new(shader.outputs["BSDF"], output.inputs[0])
    return tree


def normals_group():
    tree, build, output = shader_group("normals")
    geometry = build.nodes.new("ShaderNodeNewGeometry")
    scale = build.nodes.new("ShaderNodeVectorMath")
    scale.operation = "MULTIPLY_ADD"
    scale.inputs[1].default_value = (0.5, 0.5, 0.5)
    scale.inputs[2].default_value = (0.5, 0.5, 0.5)
    emission = build.nodes.new("ShaderNodeEmission")
    build.links.new(geometry.outputs["Normal"], scale.inputs[0])
    build.links.new(scale.outputs["Vector"], emission.inputs["Color"])
    build.links.new(emission.outputs["Emission"], output.inputs[0])
    return tree


def pixel_footprint(camera, scene):
    """Size of one pixel as (per metre of depth, constant): perspective cameras scale with depth, orthographic ones do not."""
    data = camera.data
    width, height = scene.render.resolution_x, scene.render.resolution_y
    fit = data.sensor_fit
    pixels = {"AUTO": max(width, height), "HORIZONTAL": width, "VERTICAL": height}[fit]
    if data.type == "ORTHO":
        return 0.0, data.ortho_scale / pixels
    sensor = data.sensor_height if fit == "VERTICAL" else data.sensor_width
    return sensor / data.lens / pixels, 0.0


def screen_projection(build, footprint):
    """The camera's projection at the shaded point, linearised: a camera-space vector to an offset on screen in pixels.

    A perspective camera maps (x, y, z) to (x / z, y / z) / footprint; its derivative at the point seen along (vx, vy, vz)
    is (x - z vx / vz, y - z vy / vz) / (depth * footprint). An orthographic camera maps (x, y) / footprint."""
    per_depth, constant = footprint
    if per_depth <= 0.0:
        def flat(vector):
            x, y, _ = build.separate(vector)
            return build.mul(x, 1.0 / constant), build.mul(y, 1.0 / constant)

        return flat
    camera = build.nodes.new("ShaderNodeCameraData")
    view_x, view_y, view_z = build.separate(camera.outputs["View Vector"])
    slope_x = build.math("DIVIDE", view_x, view_z)
    slope_y = build.math("DIVIDE", view_y, view_z)
    scale = build.div(1.0, build.mul(build.math("ABSOLUTE", camera.outputs["View Z Depth"]), per_depth))

    def perspective(vector):
        x, y, z = build.separate(vector)
        return build.mul(build.sub(x, build.mul(slope_x, z)), scale), build.mul(build.sub(y, build.mul(slope_y, z)), scale)

    return perspective


def polygon_edge_coverage(build, width, footprint):
    """Share of the pixel a line `width` pixels wide covers, measured to the nearest real edge on screen.

    Each triangle corner carries its barycentric weight (a cut edge's weight is pushed far outside) and each triangle its
    two edge vectors in object space. Projected to the screen they give the triangle in pixels, so the distance to each
    edge is exact for that edge's direction on screen, however obliquely the surface is seen. Where a triangle is too small
    to hold its own outline (its inscribed circle on screen under about two line widths across) the lines fade out instead
    of turning the surface solid."""
    weights = build.separate(build.attribute(CORNER_ATTRIBUTE))
    project = screen_projection(build, footprint)
    first_x, first_y = project(build.to_camera(build.attribute(EDGE_ATTRIBUTES[0])))
    second_x, second_y = project(build.to_camera(build.attribute(EDGE_ATTRIBUTES[1])))
    twice_area = build.math("ABSOLUTE", build.sub(build.mul(first_x, second_y), build.mul(first_y, second_x)))
    opposite = (
        build.hypot(build.sub(second_x, first_x), build.sub(second_y, first_y)),
        build.hypot(second_x, second_y),
        build.hypot(first_x, first_y),
    )
    distances = [build.mul(weight, build.div(twice_area, length)) for weight, length in zip(weights, opposite)]
    nearest = build.math("MINIMUM", build.math("MINIMUM", distances[0], distances[1]), distances[2])
    line = build.sub(width / 2.0 + 0.5, nearest, clamp=True)
    room = build.div(twice_area, build.add(build.add(opposite[0], opposite[1]), opposite[2]))
    fade = build.math("DIVIDE", build.sub(room, width * FADE_START), width * FADE_SPAN, clamp=True)
    known = build.math("GREATER_THAN", build.add(build.add(weights[0], weights[1]), weights[2]), 0.5)
    return build.mul(line, fade), known


def triangle_edge_coverage(build, width):
    wireframe = build.nodes.new("ShaderNodeWireframe")
    wireframe.use_pixel_size = True
    wireframe.inputs["Size"].default_value = width
    return wireframe.outputs["Fac"]


def wire_group(width, footprint):
    """Clay with lines. With a footprint, meshes that carry the edge attributes get their real edges; every other surface
    (and every surface without a footprint) gets Cycles' Wireframe node, which draws each render triangle's edges."""
    tree, build, output = shader_group("wire")
    coverage = triangle_edge_coverage(build, width)
    if footprint is not None:
        exact, known = polygon_edge_coverage(build, width, footprint)
        coverage = build.add(build.mul(exact, known), build.mul(coverage, build.sub(1.0, known)))
    path = build.nodes.new("ShaderNodeLightPath")
    coverage = build.mul(coverage, path.outputs["Is Camera Ray"])
    mix = build.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = CLAY
    mix.inputs["B"].default_value = LINE
    build.links.new(coverage, mix.inputs["Factor"])
    shader = clay_shader(build.nodes)
    build.links.new(mix.outputs["Result"], shader.inputs["Base Color"])
    build.links.new(shader.outputs["BSDF"], output.inputs[0])
    return tree


def group_material(name, group):
    """A temporary material that is the view's shader group alone, for surfaces that have no material of their own."""
    material, nodes, links, output = temporary_material(name)
    node = nodes.new("ShaderNodeGroup")
    node.node_tree = group
    links.new(node.outputs[0], output.inputs["Surface"])
    return material
