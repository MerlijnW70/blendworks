"""World-space shader coordinates during a camera-relative render.

While floating_origin moves the world by minus an offset, a shader that reads the world position of a shading point
(the Position output of a Geometry node, or a Vector Transform of a point into or out of world space) would see the
moved coordinates: cloud fields, cloud shadows, rain and every procedural texture placed in world space would slide by
the offset. ShaderShift puts the offset back at those sockets, in every shader node tree of the file (materials,
worlds, lights and shader node groups), so each shader computes from the same world coordinates as without the move,
at the same float32 precision. restore removes every node it added and links each socket to what it was linked to."""
import bpy

from .rig import TEMPORARY_PREFIX

NODE_NAME = TEMPORARY_PREFIX + "world_offset"
GEOMETRY_NODE = "ShaderNodeNewGeometry"
TRANSFORM_NODE = "ShaderNodeVectorTransform"


def shader_trees():
    trees = []
    for owners in (bpy.data.materials, bpy.data.worlds, bpy.data.lights):
        trees.extend(owner.node_tree for owner in owners if owner.node_tree is not None)
    trees.extend(group for group in bpy.data.node_groups if group.bl_idname == "ShaderNodeTree")
    return trees


def world_outputs(node):
    """Output sockets that carry a world-space point."""
    if node.bl_idname == GEOMETRY_NODE:
        return [node.outputs["Position"]]
    if node.bl_idname == TRANSFORM_NODE and node.vector_type == "POINT" and node.convert_to == "WORLD" and node.convert_from != "WORLD":
        return [node.outputs[0]]
    return []


def world_inputs(node):
    """Input sockets that expect a world-space point."""
    if node.bl_idname == TRANSFORM_NODE and node.vector_type == "POINT" and node.convert_from == "WORLD" and node.convert_to != "WORLD":
        return [node.inputs[0]]
    return []


class ShaderShift:
    def __init__(self, offset):
        self.offset = (float(offset[0]), float(offset[1]), float(offset[2]))
        self.added = []

    def apply(self):
        for tree in shader_trees():
            for node in list(tree.nodes):
                for socket in world_outputs(node):
                    self.after(tree, socket)
                for socket in world_inputs(node):
                    self.before(tree, socket)

    def math_node(self, tree, operation):
        node = tree.nodes.new("ShaderNodeVectorMath")
        node.name = NODE_NAME
        node.label = NODE_NAME
        node.operation = operation
        node.inputs[1].default_value = self.offset
        return node

    def after(self, tree, socket):
        """socket gives moved world points: every link from it goes through socket + offset instead."""
        links = [(link.to_socket, link.is_muted) for link in tree.links if link.from_socket == socket]
        if not links:
            return
        add = self.math_node(tree, "ADD")
        tree.links.new(socket, add.inputs[0])
        for target, _ in links:
            tree.links.new(add.outputs[0], target)
        self.added.append((tree, add, [(socket, target, muted) for target, muted in links]))

    def before(self, tree, socket):
        """socket takes true world points but its node converts with moved matrices: feed it point - offset."""
        sources = [(link.from_socket, link.is_muted) for link in tree.links if link.to_socket == socket]
        subtract = self.math_node(tree, "SUBTRACT")
        if sources:
            tree.links.new(sources[0][0], subtract.inputs[0])
        else:
            subtract.inputs[0].default_value = socket.default_value
        tree.links.new(subtract.outputs[0], socket)
        self.added.append((tree, subtract, [(source, socket, muted) for source, muted in sources]))

    def restore(self):
        for tree, node, links in reversed(self.added):
            tree.nodes.remove(node)
            for source, target, muted in links:
                link = tree.links.new(source, target)
                link.is_muted = muted
        self.added = []
