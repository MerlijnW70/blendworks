"""Ground cover shading: preset materials, instance tint and ground darkening."""

import bpy

from . import leaf_optics
from .errors import bad_args
from .limits import MAX_CONTACT_DARKENING
from .nodes import Graph, find_socket
from .presets import PRESETS
from .procedural import surface_principled, wire_channels
from .schema import validate

TINT_ATTRIBUTE = "gc_tint"
TINT_HUE = 0.05
TINT_SATURATION = 0.25
TINT_VALUE = 0.35
STRAW_ATTRIBUTE = "gc_straw"
STRAW_SHADE = 0.8
CONTACT_MIX = "gc_contact_mix"
CONTACT_ATTRIBUTE = "gc_contact_attribute"
CONTACT_STRENGTH = "gc_contact_strength"
CONTACT_MULTIPLIER = "gc_contact_multiplier"
CONTACT_FLOOR = 1.0 - MAX_CONTACT_DARKENING
CONTACT_DEFAULT = 0.2
LEAF_PRESETS = {"grass_blade": "grass", "litter": "litter"}


def preset_material(name, preset_name, overrides):
    preset = PRESETS[preset_name]
    params = validate(preset.schema(), overrides)
    if name in bpy.data.materials:
        raise bad_args(f"a material named {name} already exists; ground cover does not overwrite materials")
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    graph = Graph(tree)
    output = graph.node("ShaderNodeOutputMaterial", is_active_output=True)
    shader = graph.node("ShaderNodeBsdfPrincipled")
    graph.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    channels = preset.build(graph, params)
    wire_channels(graph, material, output, shader, channels, params["bump"])
    instance_tint(graph, shader, params.get("dry_color") if preset_name == "grass_blade" else None)
    leaf = LEAF_PRESETS.get(preset_name)
    if leaf is not None and not (preset_name == "litter" and params["shape"] in ("twig", "pebble")):
        leaf_optics.two_sided(graph, leaf, params["translucency"])
    material.diffuse_color = list(params.get("color", (0.2, 0.3, 0.1))[:3]) + [1.0]
    graph.layout()
    return material


def instance_tint(graph, shader, straw_color=None):
    """Vary the colour per instance through gc_tint, and turn it towards straw_color (darkened, as a whole dry blade is
    darker than its sunlit tip) by the instance's gc_straw share."""
    socket = shader.inputs["Base Color"]
    source = socket.links[0].from_socket if socket.is_linked else list(socket.default_value)
    tint = graph.node("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name=TINT_ATTRIBUTE).outputs["Fac"]
    adjusted = graph.node("ShaderNodeHueSaturation", {
        "Hue": graph.math("MULTIPLY_ADD", tint, TINT_HUE, 0.5),
        "Saturation": graph.math("MULTIPLY_ADD", tint, TINT_SATURATION, 1.0),
        "Value": graph.math("MULTIPLY_ADD", tint, TINT_VALUE, 1.0),
        "Color": source,
    })
    tinted = adjusted.outputs["Color"]
    if straw_color is not None:
        straw = graph.node("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name=STRAW_ATTRIBUTE).outputs["Fac"]
        tinted = graph.mix(straw, tinted, [value * STRAW_SHADE for value in list(straw_color)[:3]])
    graph.links.new(tinted, socket)


def darken_ground(material, attribute, strength):
    _, shader = surface_principled(material)
    tree = material.node_tree
    graph = Graph(tree)
    strength = min(strength, 1.0 - CONTACT_FLOOR)
    existing = tree.nodes.get(CONTACT_MIX)
    if existing is not None:
        tree.nodes[CONTACT_ATTRIBUTE].attribute_name = attribute
        tree.nodes[CONTACT_STRENGTH].inputs[1].default_value = strength
        return False
    socket = shader.inputs["Base Color"]
    source = socket.links[0].from_socket if socket.is_linked else list(socket.default_value)
    reader = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=attribute)
    reader.name = CONTACT_ATTRIBUTE
    cover = graph.node("ShaderNodeMath", operation="MULTIPLY", use_clamp=True)
    graph.set(cover.inputs[0], reader.outputs["Fac"])
    cover.inputs[1].default_value = 1.0
    scale = graph.node("ShaderNodeMath", operation="MULTIPLY", use_clamp=True)
    scale.name = CONTACT_STRENGTH
    graph.set(scale.inputs[0], cover.outputs[0])
    scale.inputs[1].default_value = strength
    multiplier = graph.node("ShaderNodeMath", operation="SUBTRACT", use_clamp=True)
    multiplier.name = CONTACT_MULTIPLIER
    multiplier.inputs[0].default_value = 1.0
    graph.set(multiplier.inputs[1], scale.outputs[0])
    mix = graph.node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY", clamp_result=True)
    mix.name = CONTACT_MIX
    find_socket(mix.inputs, "Factor_Float").default_value = 1.0
    graph.set(find_socket(mix.inputs, "A_Color"), source)
    graph.set(find_socket(mix.inputs, "B_Color"), multiplier.outputs[0])
    graph.links.new(find_socket(mix.outputs, "Result_Color"), socket)
    return True
