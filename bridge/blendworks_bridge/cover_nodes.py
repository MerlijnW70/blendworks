"""Geometry node group that builds ground cover instances."""

import bpy
import numpy

GROUP_NAME = "Blendworks Ground Cover"
MODIFIER_NAME = "GroundCover"
PICK = "gc_pick"
CARD = "gc_card"
TRANSFORM = "gc_transform"
TINT = "gc_tint"
KEY = "gc_key"
STRAW = "gc_straw"
CARDS_PROPERTY = "gc_has_cards"
INPUTS = (
    ("Geometry", "NodeSocketGeometry", None),
    ("Elements", "NodeSocketCollection", None),
    ("Realize", "NodeSocketBool", False),
    ("Cards", "NodeSocketBool", False),
    ("Share", "NodeSocketFloat", 1.0),
)


def named(tree, data_type, name):
    node = tree.nodes.new("GeometryNodeInputNamedAttribute")
    node.data_type = data_type
    node.inputs["Name"].default_value = name
    return node.outputs["Attribute"]


def switch(tree, input_type, condition, false, true):
    node = tree.nodes.new("GeometryNodeSwitch")
    node.input_type = input_type
    tree.links.new(condition, node.inputs["Switch"])
    tree.links.new(false, node.inputs["False"])
    tree.links.new(true, node.inputs["True"])
    return node.outputs["Output"]


def build_group():
    tree = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    for name, socket_type, default in INPUTS:
        socket = tree.interface.new_socket(name, in_out="INPUT", socket_type=socket_type)
        if default is not None:
            socket.default_value = default
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = tree.nodes, tree.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")
    compare = nodes.new("FunctionNodeCompare")
    compare.data_type = "FLOAT"
    compare.operation = "GREATER_EQUAL"
    links.new(named(tree, "FLOAT", KEY), compare.inputs[0])
    links.new(group_in.outputs["Share"], compare.inputs[1])
    delete = nodes.new("GeometryNodeDeleteGeometry")
    delete.domain = "POINT"
    links.new(group_in.outputs["Geometry"], delete.inputs["Geometry"])
    links.new(compare.outputs["Result"], delete.inputs["Selection"])
    collection = nodes.new("GeometryNodeCollectionInfo")
    collection.transform_space = "ORIGINAL"
    collection.inputs["Separate Children"].default_value = True
    collection.inputs["Reset Children"].default_value = True
    links.new(group_in.outputs["Elements"], collection.inputs["Collection"])
    instancer = nodes.new("GeometryNodeInstanceOnPoints")
    instancer.inputs["Pick Instance"].default_value = True
    links.new(delete.outputs["Geometry"], instancer.inputs["Points"])
    links.new(collection.outputs["Instances"], instancer.inputs["Instance"])
    links.new(switch(tree, "INT", group_in.outputs["Cards"], named(tree, "INT", PICK), named(tree, "INT", CARD)), instancer.inputs["Instance Index"])
    placed = nodes.new("GeometryNodeSetInstanceTransform")
    links.new(instancer.outputs["Instances"], placed.inputs["Instances"])
    links.new(named(tree, "FLOAT4X4", TRANSFORM), placed.inputs["Transform"])
    realize = nodes.new("GeometryNodeRealizeInstances")
    links.new(placed.outputs["Instances"], realize.inputs["Geometry"])
    links.new(switch(tree, "GEOMETRY", group_in.outputs["Realize"], placed.outputs["Instances"], realize.outputs["Geometry"]), group_out.inputs["Geometry"])
    return tree


def cover_group():
    tree = bpy.data.node_groups.get(GROUP_NAME)
    return tree if tree is not None else build_group()


def socket_key(modifier, name):
    for item in modifier.node_group.interface.items_tree:
        if getattr(item, "in_out", None) == "INPUT" and item.name == name:
            return item.identifier
    raise KeyError(name)


def set_input(modifier, name, value):
    getattr(modifier.properties.inputs, socket_key(modifier, name)).value = value


def get_input(modifier, name):
    return getattr(modifier.properties.inputs, socket_key(modifier, name)).value


def realized_vertices(vertex_counts, index, key, share):
    """Vertices a realized population holds: every instance kept by the share, with the vertices of the element its index names."""
    return int(numpy.asarray(vertex_counts)[numpy.asarray(index)[numpy.asarray(key) < share]].sum())


def write_attribute(mesh, name, data_type, values, field="value"):
    attribute = mesh.attributes.new(name, data_type, "POINT")
    attribute.data.foreach_set(field, numpy.ascontiguousarray(values).ravel())


def points_object(ctx, name, placed, elements, parent, realize, cards):
    """The instance points of a ground-cover population or of distant_forest's placements; only the cover's carry the
    straw share gc_straw."""
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(placed))
    mesh.vertices.foreach_set("co", placed.positions.astype(numpy.float32).ravel())
    write_attribute(mesh, PICK, "INT", placed.pick)
    write_attribute(mesh, CARD, "INT", placed.card)
    write_attribute(mesh, TINT, "FLOAT", placed.tint.astype(numpy.float32))
    write_attribute(mesh, KEY, "FLOAT", placed.key.astype(numpy.float32))
    straw = getattr(placed, "straw", None)
    if straw is not None:
        write_attribute(mesh, STRAW, "FLOAT", straw.astype(numpy.float32))
    write_attribute(mesh, TRANSFORM, "FLOAT4X4", placed.matrices.transpose(0, 2, 1))
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    ctx.scene.collection.objects.link(obj)
    obj.parent = parent
    obj[CARDS_PROPERTY] = cards
    modifier = obj.modifiers.new(MODIFIER_NAME, "NODES")
    modifier.node_group = cover_group()
    set_input(modifier, "Elements", elements)
    set_input(modifier, "Realize", realize)
    return obj
