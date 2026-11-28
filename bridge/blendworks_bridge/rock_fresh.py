"""The fresh fracture variant of a rock material, which fracture and chip give their cut faces."""
import json

import bpy

from .nodes import Graph
from .presets import PRESETS
from .procedural import wire_channels
from .rock_relief import ROCK_FLAG, is_rock_material

FRESH_SUFFIX = "_fresh"
FRESH_FLAG = "blendworks_fresh"


def rock_params(material):
    return json.loads(material[ROCK_FLAG])


def fresh_variant(material):
    """The fresh fracture face of a rock material: the same stone preset with fresh on, named <material>_fresh and flagged
    as a fresh slot, so fracture and chip give cut faces the unweathered rock with its rough break relief."""
    if material.get(FRESH_FLAG):
        return material
    name = material.name + FRESH_SUFFIX
    found = bpy.data.materials.get(name)
    if found is not None and is_rock_material(found) and found.get(FRESH_FLAG):
        return found
    params = dict(rock_params(material), fresh=True)
    variant = found or bpy.data.materials.new(name)
    variant.use_fake_user = True
    variant.use_nodes = True
    tree = variant.node_tree
    tree.nodes.clear()
    graph = Graph(tree)
    output = graph.node("ShaderNodeOutputMaterial", is_active_output=True)
    shader = graph.node("ShaderNodeBsdfPrincipled")
    graph.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    wire_channels(graph, variant, output, shader, PRESETS["stone"].build(graph, params), params["bump"])
    variant.diffuse_color = list(material.diffuse_color)
    variant[FRESH_FLAG] = True
    graph.layout()
    return variant


def first_rock(mesh):
    return next((material for material in mesh.materials if is_rock_material(material) and not material.get(FRESH_FLAG)), None)
