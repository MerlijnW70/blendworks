"""The ground material of distant land: a copy of the region's own material, so the ground continues at the border with
the same texture, whose fine detail the renderer averages over each pixel's footprint as the land recedes. Away from the
border it gains what only shows at landscape scale: broad variation of tone, rock on steep slopes and still water."""
import math

import bpy

from .nodes import Graph

FAR_ATTRIBUTE = "dl_far"
WATER_ATTRIBUTE = "dl_water"
FOREST_ATTRIBUTE = "dl_forest"
DEFAULT_GROUND = (0.07, 0.1, 0.035)
DEFAULT_ROCK = (0.16, 0.15, 0.14)
WATER_COLOR = (0.015, 0.025, 0.03)
WATER_ROUGHNESS = 0.03
WATER_IOR = 1.333
BROAD_WAVELENGTH = 1500.0
FIELD_WAVELENGTH = 260.0
ROCK_FROM = math.radians(28.0)
ROCK_FULL = math.radians(42.0)
SURFACE_NODE = "dl_surface"
WATER_MIX = "dl_water_mix"


def principled_of(material):
    tree = material.node_tree
    if tree is None:
        return None, None
    output = next((node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output), None)
    if output is None or not output.inputs["Surface"].is_linked:
        return output, None
    node = output.inputs["Surface"].links[0].from_node
    return output, node if node.type == "BSDF_PRINCIPLED" else None


def attribute(graph, name):
    return graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name).outputs["Fac"]


def ground_material(name, source, rock_color, variation):
    """A new material: the source's copy with landscape-scale variation, or a plain ground when it has no Principled BSDF."""
    material = None
    principled = None
    copied = False
    if source is not None:
        material = source.copy()
        material.name = name
        output, principled = principled_of(material)
        if principled is None:
            bpy.data.materials.remove(material)
            material = None
        else:
            copied = True
    if material is None:
        material = bpy.data.materials.new(name)
        tree = material.node_tree
        tree.nodes.clear()
        output = tree.nodes.new("ShaderNodeOutputMaterial")
        principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
        principled.inputs["Base Color"].default_value = list(DEFAULT_GROUND) + [1.0]
        principled.inputs["Roughness"].default_value = 0.9
        tree.links.new(principled.outputs[0], output.inputs["Surface"])
    principled.name = SURFACE_NODE
    graph = Graph(material.node_tree)
    base = graph.source_of(principled.inputs["Base Color"])
    far = attribute(graph, FAR_ATTRIBUTE)
    geometry = graph.node("ShaderNodeNewGeometry")
    broad = graph.noise(geometry.outputs["Position"], 1.0 / BROAD_WAVELENGTH, detail=3.0).outputs["Fac"]
    fields = graph.noise(geometry.outputs["Position"], 1.0 / FIELD_WAVELENGTH, detail=2.0).outputs["Fac"]
    swing = graph.math("ADD", graph.math("MULTIPLY", graph.math("SUBTRACT", broad, 0.5), 2.0 * variation),
                       graph.math("MULTIPLY", graph.math("SUBTRACT", fields, 0.5), variation))
    tone = graph.math("ADD", graph.math("MULTIPLY", swing, far), 1.0)
    toned = graph.mix(1.0, base, graph.node("ShaderNodeCombineXYZ", {"X": tone, "Y": tone, "Z": tone}).outputs[0], blend="MULTIPLY")
    up = graph.node("ShaderNodeSeparateXYZ", {"Vector": geometry.outputs["Normal"]}).outputs["Z"]
    steep = graph.map_range(up, math.cos(ROCK_FROM), math.cos(ROCK_FULL))
    rock = graph.math("MULTIPLY", steep, far)
    graph.set(principled.inputs["Base Color"], graph.mix(rock, toned, list(rock_color)))
    water = graph.node("ShaderNodeBsdfPrincipled", {"Base Color": list(WATER_COLOR), "Roughness": WATER_ROUGHNESS, "IOR": WATER_IOR})
    mix = graph.node("ShaderNodeMixShader")
    mix.name = WATER_MIX
    graph.set(mix.inputs[0], attribute(graph, WATER_ATTRIBUTE))
    graph.set(mix.inputs[1], principled.outputs[0])
    graph.set(mix.inputs[2], water.outputs[0])
    graph.set(output.inputs["Surface"], mix.outputs[0])
    return material, copied
