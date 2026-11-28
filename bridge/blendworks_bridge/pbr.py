"""PBR material builder: colour spaces, maps, warnings and glTF group."""

import math

import bpy

from .errors import bad_args
from .images import set_colorspace
from .nodes import Graph, find_socket

MAP_KEYS = ("base_color", "metallic", "roughness", "orm", "normal", "height", "emission", "alpha", "ao")
COLOR_MAPS = ("base_color", "emission")
CHANNEL_SOCKETS = ("Red", "Green", "Blue")
ORM_ORDERS = ("orm", "omr", "rom", "rmo", "mor", "mro")
GLTF_GROUP = "glTF Material Output"
OCCLUSION = "Occlusion"
DEFAULT_OPTIONS = {
    "orm_order": "orm",
    "normal_strength": 1.0,
    "height_strength": 1.0,
    "height_distance": 0.01,
    "emission_strength": 1.0,
    "scale": [1.0, 1.0],
    "offset": [0.0, 0.0],
    "rotation": 0.0,
}


def required_colorspace(key, image, maps):
    if key in COLOR_MAPS:
        if image.is_float and image.colorspace_settings.name not in ("sRGB", "Non-Color"):
            return image.colorspace_settings.name
        return "sRGB"
    if key == "alpha" and maps.get("base_color") == image:
        return None
    return "Non-Color"


def assign_colorspaces(txn, maps):
    wanted = {}
    for key, image in maps.items():
        colorspace = required_colorspace(key, image, maps)
        if colorspace is None:
            continue
        earlier = wanted.get(image.name)
        if earlier is not None and earlier[1] != colorspace:
            raise bad_args(f"image {image.name} is used as {earlier[0]} ({earlier[1]}) and as {key} ({colorspace}); one image has one colour space")
        wanted[image.name] = (key, colorspace)
    for key, image in maps.items():
        if image.name in wanted:
            set_colorspace(txn, image, wanted[image.name][1])
    return {name: value[1] for name, value in wanted.items()}


def warnings_for(maps):
    notes = []
    for key in COLOR_MAPS:
        image = maps.get(key)
        if image is not None and image.is_float:
            notes.append(f"{key} image {image.name} is a float image; the glTF exporter writes its linear values as they are, so save it as an 8-bit PNG with image_save first")
    if "height" in maps:
        notes.append("height is a bump in Blender only; glTF has no height map, so bake a normal map to carry it into an export")
    return notes


def build_pbr(material, maps, options):
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    graph = Graph(tree)
    output = graph.node("ShaderNodeOutputMaterial", is_active_output=True)
    shader = graph.node("ShaderNodeBsdfPrincipled")
    graph.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    vector = coordinates(graph, options)
    textures = {}

    def texture(image):
        if image.name not in textures:
            node = graph.node("ShaderNodeTexImage", image=image, interpolation="Linear", extension="REPEAT")
            graph.set(node.inputs["Vector"], vector)
            textures[image.name] = node
        return textures[image.name]

    def channel(image, index):
        separate = graph.node("ShaderNodeSeparateColor", {"Color": texture(image).outputs["Color"]})
        return separate.outputs[CHANNEL_SOCKETS[index]]

    if "base_color" in maps:
        graph.set(shader.inputs["Base Color"], texture(maps["base_color"]).outputs["Color"])
    if "orm" in maps:
        order = options["orm_order"]
        separate = graph.node("ShaderNodeSeparateColor", {"Color": texture(maps["orm"]).outputs["Color"]})
        sockets = {letter: separate.outputs[CHANNEL_SOCKETS[index]] for index, letter in enumerate(order)}
        graph.set(shader.inputs["Roughness"], sockets["r"])
        graph.set(shader.inputs["Metallic"], sockets["m"])
        if "ao" not in maps:
            graph.set(occlusion_input(graph), sockets["o"])
    if "metallic" in maps:
        graph.set(shader.inputs["Metallic"], channel(maps["metallic"], 0))
    if "roughness" in maps:
        graph.set(shader.inputs["Roughness"], channel(maps["roughness"], 0))
    if "normal" in maps:
        normal = graph.node("ShaderNodeNormalMap", {"Strength": options["normal_strength"], "Color": texture(maps["normal"]).outputs["Color"]}, space="TANGENT")
        if options.get("uv_map"):
            normal.uv_map = options["uv_map"]
        graph.set(shader.inputs["Normal"], normal.outputs["Normal"])
    if "height" in maps:
        scale = options["height_strength"] * options["height_distance"]
        displacement = graph.node("ShaderNodeDisplacement", {"Height": channel(maps["height"], 0), "Midlevel": 0.5, "Scale": scale}, space="OBJECT")
        graph.set(output.inputs["Displacement"], displacement.outputs["Displacement"])
        material.displacement_method = "BUMP"
    if "emission" in maps:
        graph.set(shader.inputs["Emission Color"], texture(maps["emission"]).outputs["Color"])
        graph.set(shader.inputs["Emission Strength"], options["emission_strength"])
    if "alpha" in maps:
        if maps["alpha"] == maps.get("base_color"):
            graph.set(shader.inputs["Alpha"], texture(maps["alpha"]).outputs["Alpha"])
        else:
            graph.set(shader.inputs["Alpha"], channel(maps["alpha"], 0))
        material.surface_render_method = "DITHERED"
    if "ao" in maps:
        graph.set(occlusion_input(graph), channel(maps["ao"], 0))
    graph.layout()
    return shader


def coordinates(graph, options):
    uv_map = options.get("uv_map")
    moved = options["scale"] != [1.0, 1.0] or options["offset"] != [0.0, 0.0] or options["rotation"] != 0.0
    if uv_map is None and not moved:
        return None
    if uv_map is not None:
        source = graph.node("ShaderNodeUVMap", uv_map=uv_map).outputs["UV"]
    else:
        source = graph.node("ShaderNodeTexCoord").outputs["UV"]
    if not moved:
        return source
    mapping = graph.node("ShaderNodeMapping", vector_type="POINT")
    graph.set(mapping.inputs["Vector"], source)
    mapping.inputs["Location"].default_value = (options["offset"][0], options["offset"][1], 0.0)
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(options["rotation"]))
    mapping.inputs["Scale"].default_value = (options["scale"][0], options["scale"][1], 1.0)
    return mapping.outputs["Vector"]


def occlusion_input(graph):
    for node in graph.nodes:
        if node.type == "GROUP" and node.node_tree is not None and node.node_tree.name.startswith(GLTF_GROUP):
            return find_socket(node.inputs, OCCLUSION)
    node = graph.node("ShaderNodeGroup")
    node.node_tree = gltf_group()
    return find_socket(node.inputs, OCCLUSION)


def gltf_group():
    for group in bpy.data.node_groups:
        if group.name.startswith(GLTF_GROUP) and group.bl_idname == "ShaderNodeTree":
            sockets = [item for item in group.interface.items_tree if item.item_type == "SOCKET" and item.in_out == "INPUT"]
            if any(item.name == OCCLUSION for item in sockets):
                return group
    group = bpy.data.node_groups.new(GLTF_GROUP, "ShaderNodeTree")
    socket = group.interface.new_socket(OCCLUSION, in_out="INPUT", socket_type="NodeSocketFloat")
    socket.default_value = 1.0
    socket.min_value = 0.0
    socket.max_value = 1.0
    group.nodes.new("NodeGroupInput")
    group.nodes.new("NodeGroupOutput")
    return group


def users_of(material):
    return [obj for obj in bpy.context.scene.objects if any(slot.material == material for slot in obj.material_slots)]


def check_uv_map(material, uv_map):
    for obj in users_of(material):
        if obj.type == "MESH" and uv_map not in obj.data.uv_layers:
            raise bad_args(f"{obj.name} uses {material.name} but has no UV map named {uv_map}")
