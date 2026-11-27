import bpy

from ..errors import not_found
from ..graph_build import MAX_RAMP_STOPS, build_graph
from ..graph_catalog import KINDS
from ..graph_read import read_graph
from ..limits import (ELEMENT_NAME_LENGTH, FRACTION, MAX_COORDINATE, MAX_GRAPH_LINKS, MAX_GRAPH_NODES, NODE_INPUTS,
                      NODE_SETTINGS, PAIR)
from ..materials_info import principled_node
from ..registry import command
from ..schema import REPLACES, array, boolean, color, number, obj, ref, string, vector3
from .procedural import ensure_material

NAME_LENGTH = ELEMENT_NAME_LENGTH
DISPLACEMENT = {"bump": "BUMP", "displacement": "DISPLACEMENT", "both": "BOTH"}
CHECK_TREE = "blendworks_check"


def input_schema():
    return obj(
        {
            "socket": string("Input socket, by name or identifier; material_info shows identifiers.", max_length=NAME_LENGTH),
            "number": number("Value of a float or integer socket.", -MAX_COORDINATE, MAX_COORDINATE),
            "vector": vector3("Value of a vector socket."),
            "color": color("Value of a colour socket, linear RGB or RGBA."),
            "boolean": boolean("Value of a boolean socket."),
        },
        ["socket"],
    )


def setting_schema():
    return obj(
        {
            "name": string("Setting name; a wrong one is refused with the list of that node's settings.", max_length=NAME_LENGTH),
            "text": string("Value of a choice or text setting, for example MULTIPLY.", max_length=NAME_LENGTH),
            "number": number("Value of a number setting.", -MAX_COORDINATE, MAX_COORDINATE),
            "boolean": boolean("Value of an on or off setting."),
        },
        ["name"],
    )


def stop_schema():
    return obj({"position": number("Position along the ramp, 0 to 1.", 0.0, FRACTION), "color": color("Colour at the stop, linear RGB or RGBA.")}, ["position", "color"])


def node_schema():
    return obj(
        {
            "name": string("Unique node name that links refer to.", max_length=NAME_LENGTH),
            "type": string("Node type from the allow-list.", list(KINDS)),
            "inputs": array(input_schema(), "Values for unlinked input sockets; the rest keep Blender's defaults. rgb and value nodes set their output here.", 0, NODE_INPUTS),
            "settings": array(setting_schema(), "Node settings such as operation, noise_type or data_type; set before the inputs.", 0, NODE_SETTINGS),
            "stops": array(stop_schema(), f"color_ramp only: 2 to {MAX_RAMP_STOPS} stops with rising positions.", PAIR, MAX_RAMP_STOPS),
        },
        ["name", "type"],
    )


def link_schema():
    return obj(
        {
            "from_node": string("Name of the node the link starts at.", max_length=NAME_LENGTH),
            "from_socket": string("Output socket, by name or identifier.", max_length=NAME_LENGTH),
            "to_node": string("Name of the node the link ends at.", max_length=NAME_LENGTH),
            "to_socket": string("Input socket, by name or identifier.", max_length=NAME_LENGTH),
        },
        ["from_node", "from_socket", "to_node", "to_socket"],
    )


def checked(nodes, links):
    scratch = bpy.data.node_groups.new(CHECK_TREE, "ShaderNodeTree")
    try:
        build_graph(scratch, nodes, links)
    finally:
        bpy.data.node_groups.remove(scratch)


@command(
    "material_nodes",
    "Create or rebuild a material from a node graph of allow-listed shader, texture, colour, vector and converter nodes; invalid graphs are refused.",
    {
        "name": ref(string("Material name; created, or rebuilt when it exists."), "material", REPLACES),
        "nodes": array(node_schema(), "The nodes: exactly one material_output, usually a principled_bsdf feeding its Surface.", 1, MAX_GRAPH_NODES),
        "links": array(link_schema(), "Links from an output socket to an input socket; shader links only join shaders, and cycles are refused.", 0, MAX_GRAPH_LINKS),
        "displacement": string("How a linked Displacement input is applied.", list(DISPLACEMENT), "bump"),
    },
    ["name", "nodes"],
    family="materials",
    intents=("custom shader node graph", "colour ramp, noise or checker material"),
    nearest=(("material_procedural", "for ready presets"),),
)
def material_nodes(ctx, args):
    links = args.get("links", [])
    checked(args["nodes"], links)
    material, created = ensure_material(args["name"])
    material.node_tree.nodes.clear()
    build_graph(material.node_tree, args["nodes"], links)
    material.displacement_method = DISPLACEMENT[args["displacement"]]
    shader = principled_node(material)
    if shader is not None and not shader.inputs["Base Color"].is_linked:
        material.diffuse_color = list(shader.inputs["Base Color"].default_value)
    return {"name": material.name, "created": created, "nodes": len(material.node_tree.nodes), "links": len(material.node_tree.links)}


@command(
    "material_info",
    "Read a material's node graph in the format material_nodes takes, so it can be edited and sent back; says which nodes it cannot express.",
    {"name": ref(string("Material name."), "material")},
    ["name"],
    mutates=False,
    family="materials",
    intents=("read a material's nodes to edit them", "inspect a shader graph"),
    nearest=(("material_nodes", "to change the graph"),),
)
def material_info(ctx, args):
    material = bpy.data.materials.get(args["name"])
    if material is None:
        raise not_found(f"no material named {args['name']}")
    graph = read_graph(material)
    graph["name"] = material.name
    graph["displacement"] = next(key for key, value in DISPLACEMENT.items() if value == material.displacement_method)
    return graph
