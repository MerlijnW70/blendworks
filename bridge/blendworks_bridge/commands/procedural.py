import bpy

from ..errors import bad_args, not_found
from ..nodes import Graph
from ..pbr import users_of
from ..presets import PRESETS
from ..procedural import chosen_preset, displacement_of, preset_vector, surface_principled, wire_channels
from ..registry import command
from ..schema import boolean, integer, number, string

BLENDED_INPUTS = (("Base Color", "base_color", "RGBA"), ("Roughness", "roughness", "FLOAT"), ("Metallic", "metallic", "FLOAT"))
MASKS = ("noise", "edges", "cavity", "vertex_color")


def preset_properties():
    return {name: preset.schema() for name, preset in PRESETS.items()}


PRESET_NAMES = ", ".join(PRESETS)


@command(
    "material_procedural",
    f"Create or rebuild a bakeable procedural material from one preset: {PRESET_NAMES}.",
    dict({"name": string("Material name; created, or rebuilt when it exists.")}, **preset_properties()),
    ["name"],
)
def material_procedural(ctx, args):
    preset, params = chosen_preset(PRESETS, args)
    material = bpy.data.materials.get(args["name"])
    created = material is None
    if created:
        material = bpy.data.materials.new(args["name"])
        material.use_fake_user = True
    else:
        ctx.txn.touch_material_tree(material)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    graph = Graph(tree)
    output = graph.node("ShaderNodeOutputMaterial", is_active_output=True)
    shader = graph.node("ShaderNodeBsdfPrincipled")
    graph.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    channels = preset.build(graph, params)
    wire_channels(graph, material, output, shader, channels, params["bump"])
    material.diffuse_color = viewport_color(params)
    graph.layout()
    return {"name": material.name, "created": created, "preset": preset.name, "params": params, "nodes": len(tree.nodes)}


def viewport_color(params):
    for key in ("color", "light_color", "metal_color"):
        if key in params:
            return list(params[key][:3]) + [1.0]
    return [0.8, 0.8, 0.8, 1.0]


@command(
    "material_layer",
    "Blend a procedural preset over a material through a mask: noise, edges, cavity or a vertex colour.",
    dict(
        {
            "material": string("Material to layer onto; it needs a Principled BSDF feeding its output."),
            "mask": string("noise: patches; edges: worn convex edges; cavity: crevices; vertex_color: a painted colour attribute.", list(MASKS), "noise"),
            "amount": number("Share of the surface the overlay covers, 0 to 1.", 0.0, 1.0, 0.5),
            "softness": number("Softness of the mask's border, 0 to 1.", 0.0, 1.0, 0.3),
            "mask_scale": number("Patches per metre of the noise mask and of the breakup noise.", 0.01, 1000.0, 8.0),
            "edge_source": string("Edge detection: ao (ambient occlusion from inside, works on low poly) or pointiness (vertex curvature).", ["ao", "pointiness"], "ao"),
            "distance": number("Reach in metres of the edge and cavity occlusion rays.", 0.001, 10.0, 0.03),
            "layer": string("Colour attribute for the vertex_color mask; its brightness is the mask."),
            "invert": boolean("Invert the mask.", False),
            "breakup": number("Break the edges, cavity or vertex colour mask up with noise, 0 to 1.", 0.0, 1.0, 0.5),
            "seed": integer("Seed of the mask noise.", 0, 1_000_000, 0),
        },
        **preset_properties(),
    ),
    ["material"],
)
def material_layer(ctx, args):
    material = bpy.data.materials.get(args["material"])
    if material is None:
        raise not_found(f"no material named {args['material']}")
    preset, params = chosen_preset(PRESETS, args)
    check_mask_args(material, args)
    output, shader = surface_principled(material)
    ctx.txn.touch_material_tree(material)
    graph = Graph(material.node_tree)
    channels = preset.build(graph, params)
    mask = mask_value(graph, args)
    for socket_name, key, data_type in BLENDED_INPUTS:
        socket = shader.inputs[socket_name]
        graph.set(socket, graph.mix(mask, graph.source_of(socket), channels[key], data_type))
    if params["bump"] > 0.0:
        layered = displacement_of(graph, graph.math("MULTIPLY", channels["height"], mask), params["bump"])
        target = output.inputs["Displacement"]
        if target.is_linked:
            layered = graph.vector_math("ADD", target.links[0].from_socket, layered)
        graph.set(target, layered)
        material.displacement_method = "BUMP"
    graph.layout()
    return {"material": material.name, "preset": preset.name, "mask": args["mask"], "amount": args["amount"], "nodes": len(material.node_tree.nodes)}


def check_mask_args(material, args):
    if args["mask"] != "vertex_color":
        if "layer" in args:
            raise bad_args("layer belongs to the vertex_color mask")
        return
    if "layer" not in args:
        raise bad_args("the vertex_color mask needs layer, the colour attribute to read")
    for obj in users_of(material):
        if obj.type == "MESH" and args["layer"] not in obj.data.color_attributes:
            raise bad_args(f"{obj.name} uses {material.name} but has no colour attribute named {args['layer']}")


def mask_value(graph, args):
    noise_params = {"seed": args["seed"], "scale": args["mask_scale"], "coordinates": "object"}
    kind = args["mask"]
    if kind == "noise":
        noise = graph.noise(preset_vector(graph, noise_params, salt=1), 1.0, detail=6.0, roughness=0.6)
        raw = graph.map_range(noise.outputs["Factor"], 0.3, 0.7)
    elif kind == "edges" and args["edge_source"] == "pointiness":
        raw = graph.map_range(graph.node("ShaderNodeNewGeometry").outputs["Pointiness"], 0.5, 0.56)
    elif kind in ("edges", "cavity"):
        occlusion = graph.node("ShaderNodeAmbientOcclusion", {"Distance": args["distance"]}, inside=kind == "edges", samples=16)
        raw = graph.math("SUBTRACT", 1.0, occlusion.outputs["AO"])
    else:
        raw = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=args["layer"]).outputs["Fac"]
    if args["invert"]:
        raw = graph.math("SUBTRACT", 1.0, raw)
    if kind != "noise" and args["breakup"] > 0.0:
        noise = graph.noise(preset_vector(graph, noise_params, salt=2), 1.0, detail=4.0, roughness=0.6)
        variation = graph.map_range(noise.outputs["Factor"], 0.3, 0.7, 1.0 - args["breakup"], 1.0)
        raw = graph.math("MULTIPLY", raw, variation)
    border = 0.02 + 0.3 * args["softness"]
    middle = (1.0 - args["amount"]) * (1.0 + 2.0 * border) - border
    return graph.map_range(raw, middle - border, middle + border)
