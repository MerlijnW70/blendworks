"""Outline graphs for silhouettes."""

from math import e

import bpy

LINE_COLOUR = (0.05, 0.05, 0.05, 1.0)
LINE_STRENGTH = 0.85
NORMAL_EDGE = (0.5, 1.2)
DEPTH_EDGE = (0.03, 0.12)


class OutlineGraph:
    def __init__(self, scene):
        self.group = bpy.data.node_groups.new("judge-outlines", "CompositorNodeTree")
        self.group.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        self.nodes = self.group.nodes
        self.links = self.group.links
        self.layers = self.nodes.new("CompositorNodeRLayers")
        self.layers.scene = scene

    def link(self, source, target):
        if isinstance(source, float):
            target.default_value = source
        else:
            self.links.new(source, target)

    def math(self, operation, first, second):
        node = self.nodes.new("ShaderNodeMath")
        node.operation = operation
        self.link(first, node.inputs[0])
        self.link(second, node.inputs[1])
        return node.outputs[0]

    def gradient(self, source):
        sobel = self.nodes.new("CompositorNodeFilter")
        sobel.inputs["Type"].default_value = "Sobel"
        self.links.new(source, sobel.inputs["Image"])
        grey = self.nodes.new("CompositorNodeRGBToBW")
        self.links.new(sobel.outputs["Image"], grey.inputs["Image"])
        return grey.outputs["Val"]

    def ramp(self, source, bounds):
        node = self.nodes.new("ShaderNodeMapRange")
        node.clamp = True
        self.links.new(source, node.inputs["Value"])
        node.inputs["From Min"].default_value = bounds[0]
        node.inputs["From Max"].default_value = bounds[1]
        return node.outputs["Result"]

    def build(self):
        creases = self.ramp(self.gradient(self.layers.outputs["Normal"]), NORMAL_EDGE)
        log_depth = self.math("LOGARITHM", self.layers.outputs["Depth"], e)
        steps = self.ramp(self.gradient(log_depth), DEPTH_EDGE)
        strength = self.math("MULTIPLY", self.math("MAXIMUM", creases, steps), LINE_STRENGTH)
        mix = self.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        self.links.new(strength, mix.inputs["Factor"])
        colour_inputs = [socket for socket in mix.inputs if socket.type == "RGBA"]
        self.links.new(self.layers.outputs["Image"], colour_inputs[0])
        colour_inputs[1].default_value = LINE_COLOUR
        output = self.nodes.new("NodeGroupOutput")
        result = next(socket for socket in mix.outputs if socket.type == "RGBA")
        self.links.new(result, output.inputs[0])
        return self.group


def add_outlines(scene):
    layer = scene.view_layers[0]
    layer.use_pass_normal = True
    layer.use_pass_z = True
    scene.compositing_node_group = OutlineGraph(scene).build()
    scene.render.use_compositing = True
