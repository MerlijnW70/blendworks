import bpy

from . import sky_nodes, weather_objects

PREFIX = "wx_wet_"
DARKEN = 0.45
WET_ROUGHNESS = 0.12
PUDDLE_SCALE = 3.5


def principled(material):
    if material is None or material.node_tree is None:
        return None
    return next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)


def clear(material):
    tree = material.node_tree
    bsdf = principled(material)
    for node in [node for node in tree.nodes if node.name.startswith(PREFIX + "out_")]:
        target = node.get("wet_input")
        original = node.inputs[6].links[0].from_socket if node.inputs[6].is_linked else None
        if bsdf is None or target not in bsdf.inputs:
            continue
        socket = bsdf.inputs[target]
        for link in list(socket.links):
            tree.links.remove(link)
        if original is not None and not original.node.name.startswith(PREFIX):
            tree.links.new(original, socket)
    for node in [node for node in tree.nodes if node.name.startswith(PREFIX)]:
        tree.nodes.remove(node)


def source_of(graph, socket, roughness):
    if socket.is_linked:
        return socket.links[0].from_socket
    if roughness:
        return graph.value(float(socket.default_value))
    return graph.rgb(list(socket.default_value)[:3])


def apply(material, wetness, seed):
    """Darken the base colour and lower the roughness where the surface faces up; puddles go glossy."""
    clear(material)
    bsdf = principled(material)
    if bsdf is None or wetness <= 0.0:
        return False
    tree = material.node_tree
    graph = WetGraph(tree)
    geometry = graph.node("ShaderNodeNewGeometry")
    _, _, up = graph.separate(geometry.outputs["Normal"])
    facing = graph.smooth(0.3, 0.9, up)
    puddles = graph.smooth(0.55, 0.68, graph.noise(graph.vector("ADD", graph.vector("SCALE", geometry.outputs["Position"], None, 1.0 / PUDDLE_SCALE), (seed * 1.7, seed * 0.9, 0.0)), 1.0, 3.0, 0.5))
    wet = graph.mul(graph.madd(facing, 0.7, 0.3), wetness)
    flat = graph.smooth(0.92, 0.99, up)
    puddle = graph.mul(graph.mul(puddles, flat), wetness)
    colour = source_of(graph, bsdf.inputs["Base Color"], False)
    darker = graph.mix(wet, colour, graph.mix(1.0, colour, graph.gray(DARKEN), "MULTIPLY"))
    darker = graph.mix(graph.mul(puddle, 0.5), darker, graph.mix(1.0, colour, graph.gray(0.35), "MULTIPLY"))
    out_colour = graph.node("ShaderNodeMix", PREFIX + "out_color")
    out_colour.data_type = "RGBA"
    out_colour.inputs["Factor"].default_value = 1.0
    out_colour["wet_input"] = "Base Color"
    graph.feed(out_colour.inputs[6], colour)
    graph.feed(out_colour.inputs[7], darker)
    tree.links.new(out_colour.outputs[2], bsdf.inputs["Base Color"])
    rough = source_of(graph, bsdf.inputs["Roughness"], True)
    glossy = graph.mix_value(wet, rough, graph.mul(rough, 0.45))
    glossy = graph.mix_value(puddle, glossy, WET_ROUGHNESS)
    out_rough = graph.node("ShaderNodeMix", PREFIX + "out_roughness")
    out_rough.data_type = "RGBA"
    out_rough.inputs["Factor"].default_value = 1.0
    out_rough["wet_input"] = "Roughness"
    graph.feed(out_rough.inputs[6], graph.gray(rough))
    graph.feed(out_rough.inputs[7], graph.gray(glossy))
    tree.links.new(out_rough.outputs[2], bsdf.inputs["Roughness"])
    return True


class WetGraph(sky_nodes.Graph):
    def node(self, kind, name=None):
        node = super().node(kind, name)
        if not node.name.startswith(PREFIX):
            node.name = PREFIX + node.name
        return node


def scene_materials(scene, names=None):
    found = {}
    for obj in scene.objects:
        if weather_objects.kind_of(obj) is not None or obj.type not in ("MESH", "CURVE"):
            continue
        for slot in obj.material_slots:
            if slot.material is not None:
                found[slot.material.name] = slot.material
    if names is not None:
        return {name: material for name, material in found.items() if name in names}
    return found


def wet_scene(scene, wetness, seed, names=None):
    wetted, skipped = [], []
    for name, material in sorted(scene_materials(scene, names).items()):
        if principled(material) is None:
            skipped.append(name)
            continue
        if apply(material, wetness, seed):
            wetted.append(name)
    return wetted, skipped


def dry_scene(scene):
    dried = []
    for material in bpy.data.materials:
        if material.node_tree is not None and any(node.name.startswith(PREFIX) for node in material.node_tree.nodes):
            clear(material)
            dried.append(material.name)
    return sorted(dried)
