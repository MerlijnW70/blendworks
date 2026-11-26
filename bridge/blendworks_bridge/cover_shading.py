import bpy

from .errors import bad_args
from .nodes import Graph, find_socket
from .presets import PRESETS
from .procedural import surface_principled, wire_channels
from .schema import validate

TINT_ATTRIBUTE = "gc_tint"
TINT_HUE = 0.05
TINT_SATURATION = 0.25
TINT_VALUE = 0.35
CONTACT_MIX = "gc_contact_mix"
CONTACT_ATTRIBUTE = "gc_contact_attribute"
CONTACT_STRENGTH = "gc_contact_strength"
CONTACT_MULTIPLIER = "gc_contact_multiplier"
CONTACT_FLOOR = 0.64
CONTACT_DEFAULT = 0.2


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
    instance_tint(graph, shader)
    material.diffuse_color = list(params.get("color", (0.2, 0.3, 0.1))[:3]) + [1.0]
    graph.layout()
    return material


def instance_tint(graph, shader):
    socket = shader.inputs["Base Color"]
    source = socket.links[0].from_socket if socket.is_linked else list(socket.default_value)
    tint = graph.node("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name=TINT_ATTRIBUTE).outputs["Fac"]
    adjusted = graph.node("ShaderNodeHueSaturation", {
        "Hue": graph.math("MULTIPLY_ADD", tint, TINT_HUE, 0.5),
        "Saturation": graph.math("MULTIPLY_ADD", tint, TINT_SATURATION, 1.0),
        "Value": graph.math("MULTIPLY_ADD", tint, TINT_VALUE, 1.0),
        "Color": source,
    })
    graph.links.new(adjusted.outputs["Color"], socket)


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
