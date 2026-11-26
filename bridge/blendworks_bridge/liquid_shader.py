import math

import bpy

from . import liquid_light
from .sky_nodes import Graph

FOAM_ROUGHNESS = 0.9
CELL_EDGE = 0.29
MELT_COLOR = (0.02, 0.018, 0.017)
DEPOSIT_DEPTH = 3.0


class LiquidGraph(Graph):
    def attribute(self, name):
        node = self.node("ShaderNodeAttribute")
        node.attribute_type = "GEOMETRY"
        node.attribute_name = name
        return node.outputs["Fac"]

    def shader(self, kind):
        return self.node(kind)

    def mix_shader(self, factor, a, b):
        node = self.node("ShaderNodeMixShader")
        self.feed(node.inputs[0], factor)
        self.tree.links.new(a, node.inputs[1])
        self.tree.links.new(b, node.inputs[2])
        return node.outputs[0]

    def add_shader(self, a, b):
        node = self.node("ShaderNodeAddShader")
        self.tree.links.new(a, node.inputs[0])
        self.tree.links.new(b, node.inputs[1])
        return node.outputs[0]


def fresh_material(name):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    return material


def scaled(values, factor):
    return [value * factor for value in values]


def channel_split(values):
    largest = max(values)
    if largest <= 0.0:
        return None
    return [1.0 - value / largest for value in values], largest


def coefficients(entry):
    factor = entry.get("concentration", 1.0)
    return scaled(entry.get("absorption", [0.0] * 3), factor), scaled(entry.get("scattering", [0.0] * 3), factor)


def volume_output(graph, entry):
    absorption, scattering = coefficients(entry)
    result = None
    split = channel_split(absorption)
    if split is not None:
        node = graph.node("ShaderNodeVolumeAbsorption", "lq_absorption")
        node.inputs["Color"].default_value = list(split[0]) + [1.0]
        node.inputs["Density"].default_value = split[1]
        result = node.outputs[0]
    if max(scattering) > 0.0:
        largest = max(scattering)
        node = graph.node("ShaderNodeVolumeScatter", "lq_scatter")
        node.inputs["Color"].default_value = [value / largest for value in scattering] + [1.0]
        node.inputs["Density"].default_value = largest
        node.inputs["Anisotropy"].default_value = entry.get("anisotropy", 0.0)
        result = node.outputs[0] if result is None else graph.add_shader(result, node.outputs[0])
    return result


def principled(graph, name):
    node = graph.node("ShaderNodeBsdfPrincipled", name)
    return node


def shadow_clear(graph, surface):
    """Shadow rays pass the surface as if it were clear, so light reaches what lies under the liquid; the volume still absorbs it."""
    path = graph.node("ShaderNodeLightPath")
    transparent = graph.node("ShaderNodeBsdfTransparent")
    return graph.mix_shader(path.outputs["Is Shadow Ray"], surface, transparent.outputs[0])


def ripple_normal(graph, ripples):
    if ripples is None:
        return None
    image = graph.node("ShaderNodeTexImage", "lq_ripples")
    image.image = ripples["image"]
    image.interpolation = "Cubic"
    image.extension = "REPEAT"
    if ripples.get("coordinates") == "uv":
        uv = graph.node("ShaderNodeUVMap")
        u, v, _ = graph.separate(uv.outputs["UV"])
        sx, sy = ripples["uv_scale"]
        coords = graph.combine(graph.mul(u, sx / ripples["size"]), graph.mul(v, sy / ripples["size"]), 0.0)
    else:
        geometry = graph.node("ShaderNodeNewGeometry")
        coords = graph.vector("SCALE", geometry.outputs["Position"], None, 1.0 / ripples["size"])
    graph.feed(image.inputs["Vector"], coords)
    bump = graph.node("ShaderNodeBump", "lq_bump")
    bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = ripples.get("amplitude", 1.0)
    graph.feed(bump.inputs["Height"], image.outputs["Color"])
    return bump.outputs["Normal"]


def foam_mix(graph, surface, entry, foam):
    if foam is None:
        return surface
    colour = (entry.get("foam") or {}).get("color", [0.6, 0.6, 0.6])
    node = principled(graph, "lq_foam")
    node.inputs["Base Color"].default_value = list(colour) + [1.0]
    node.inputs["Roughness"].default_value = FOAM_ROUGHNESS
    geometry = graph.node("ShaderNodeNewGeometry")
    breakup = graph.noise(geometry.outputs["Position"], foam.get("scale", 1.2), 6.0, 0.6)
    amount = graph.mul(graph.attribute(foam["attribute"]), graph.smooth(0.35, 0.65, breakup))
    return graph.mix_shader(graph.clamp01(graph.mul(amount, 1.6)), surface, node.outputs[0])


def deposit_tint(graph, entry, deposit):
    """The coffee ring: solids carried to the contact line as the film dries at its edge (Deegan et al. 1997) stain the ring
    as darkly as DEPOSIT_DEPTH films; each crossing of the surface passes exp(-a e DEPOSIT_DEPTH) there."""
    absorption, _ = coefficients(entry)
    ring = [math.exp(-value * deposit["thickness"] * DEPOSIT_DEPTH) for value in absorption]
    weight = graph.clamp01(graph.attribute(deposit["attribute"]))
    return graph.mix(weight, (1.0, 1.0, 1.0, 1.0), tuple(ring) + (1.0,))


def clear_surface(graph, entry, normal, deposit=None):
    node = principled(graph, "lq_surface")
    node.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    if deposit is not None:
        graph.feed(node.inputs["Base Color"], deposit_tint(graph, entry, deposit))
    node.inputs["Roughness"].default_value = entry["roughness"]
    node.inputs["IOR"].default_value = entry["ior"]
    node.inputs["Transmission Weight"].default_value = 1.0
    graph.feed(node.inputs["Normal"], normal)
    return shadow_clear(graph, node.outputs[0])


def opaque_parameters(entry):
    if "base_color" in entry:
        return list(entry["base_color"]), list(entry["mean_free_path"])
    absorption, scattering = coefficients(entry)
    reduced = [value * (1.0 - entry.get("anisotropy", 0.0)) for value in scattering]
    colour = liquid_light.diffuse_reflectance(reduced, absorption, entry["ior"])
    free_path = [1.0 / (s + a) for s, a in zip(reduced, absorption)]
    return colour, free_path


def opaque_surface(graph, entry, normal):
    colour, free_path = opaque_parameters(entry)
    node = principled(graph, "lq_surface")
    node.subsurface_method = "RANDOM_WALK"
    node.inputs["Base Color"].default_value = list(colour) + [1.0]
    node.inputs["Roughness"].default_value = entry["roughness"]
    node.inputs["IOR"].default_value = entry["ior"]
    node.inputs["Subsurface Weight"].default_value = 1.0
    node.inputs["Subsurface Radius"].default_value = free_path
    node.inputs["Subsurface Scale"].default_value = 1.0
    graph.feed(node.inputs["Normal"], normal)
    return node.outputs[0]


def emissive_surface(graph, entry, normal, crust_scale):
    geometry = graph.node("ShaderNodeNewGeometry")
    voronoi = graph.node("ShaderNodeTexVoronoi", "lq_crust")
    voronoi.voronoi_dimensions = "3D"
    voronoi.feature = "DISTANCE_TO_EDGE"
    warped = graph.vector("ADD", geometry.outputs["Position"], graph.vector("SCALE", graph.combine(
        graph.noise(geometry.outputs["Position"], 0.7 / crust_scale, 3.0), graph.noise(graph.vector("ADD", geometry.outputs["Position"], (7.1, 3.3, 1.9)), 0.7 / crust_scale, 3.0), 0.5), None, crust_scale * 0.6))
    graph.feed(voronoi.inputs["Vector"], warped)
    voronoi.inputs["Scale"].default_value = 1.0 / crust_scale
    width = max(CELL_EDGE * (1.0 - math.sqrt(entry["crust"])), 0.004)
    hot = graph.smooth(width, 0.0, voronoi.outputs["Distance"])
    temperature = graph.madd(hot, entry["temperature"] - entry["edge_temperature"], entry["edge_temperature"])
    a, b = liquid_light.emission_fit(entry["emissivity"])
    strength = graph.exp(graph.sub(a, graph.div(b, temperature)))
    blackbody = graph.node("ShaderNodeBlackbody")
    graph.feed(blackbody.inputs["Temperature"], temperature)
    grey = graph.node("ShaderNodeRGBToBW")
    graph.feed(grey.inputs[0], blackbody.outputs[0])
    unit_colour = graph.mix(1.0, blackbody.outputs[0], graph.gray(graph.div(1.0, graph.maximum(grey.outputs[0], 1e-6))), "MULTIPLY")
    glow = graph.clamp01(graph.mul(hot, 40.0))
    emission = graph.node("ShaderNodeEmission", "lq_emission")
    graph.feed(emission.inputs["Color"], unit_colour)
    graph.feed(emission.inputs["Strength"], graph.mul(strength, glow))
    melt = principled(graph, "lq_melt")
    if entry.get("metallic"):
        melt.inputs["Base Color"].default_value = list(entry["base_color"]) + [1.0]
        melt.inputs["Metallic"].default_value = 1.0
    else:
        melt.inputs["Base Color"].default_value = list(MELT_COLOR) + [1.0]
    melt.inputs["Roughness"].default_value = 0.2 if not entry.get("metallic") else entry["roughness"]
    melt.inputs["IOR"].default_value = entry["ior"]
    crust = principled(graph, "lq_crust_surface")
    crust.inputs["Base Color"].default_value = list(entry["crust_color"]) + [1.0]
    crust.inputs["Roughness"].default_value = 0.85
    graph.feed(crust.inputs["Normal"], normal)
    surface = graph.mix_shader(glow, crust.outputs[0], melt.outputs[0])
    return graph.add_shader(surface, emission.outputs[0])


def build(name, entry, ripples=None, foam=None, crust_scale=0.4, deposit=None):
    material = fresh_material(name)
    graph = LiquidGraph(material.node_tree)
    output = graph.node("ShaderNodeOutputMaterial", "lq_output")
    normal = ripple_normal(graph, ripples)
    mode = entry["mode"]
    if mode == "clear":
        surface = clear_surface(graph, entry, normal, deposit)
        volume = volume_output(graph, entry)
        if volume is not None:
            material.node_tree.links.new(volume, output.inputs["Volume"])
    elif mode == "opaque":
        surface = opaque_surface(graph, entry, normal)
    else:
        surface = emissive_surface(graph, entry, normal, crust_scale)
    surface = foam_mix(graph, surface, entry, foam)
    material.node_tree.links.new(surface, output.inputs["Surface"])
    material["blendworks_liquid"] = entry.get("preset", "custom")
    material.diffuse_color = list(preview_colour(entry)) + [1.0]
    return material


def preview_colour(entry):
    if entry["mode"] == "opaque":
        return opaque_parameters(entry)[0]
    if entry["mode"] == "emissive":
        return entry["crust_color"]
    absorption, _ = coefficients(entry)
    return [math.exp(-value * 0.05) for value in absorption]


def glass(name, ior=None):
    from .liquid_presets import GLASS

    material = fresh_material(name)
    graph = LiquidGraph(material.node_tree)
    output = graph.node("ShaderNodeOutputMaterial", "lq_output")
    entry = {"roughness": GLASS["roughness"], "ior": GLASS["ior"] if ior is None else ior}
    material.node_tree.links.new(clear_surface(graph, entry, None), output.inputs["Surface"])
    volume = volume_output(graph, {"absorption": GLASS["absorption"]})
    material.node_tree.links.new(volume, output.inputs["Volume"])
    material["blendworks_liquid"] = "glass"
    return material
