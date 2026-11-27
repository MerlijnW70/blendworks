import random

from .errors import bad_args
from .limits import BUMP_DEPTH, MAX_SCALE_FACTOR, MAX_SEED, SMALLEST_FEATURE_MULTIPLIER
from .schema import integer, number, obj, string

SEED_RANGE = 100.0
AXES = {"x": "X", "y": "Y", "z": "Z"}
EXTRA_CHANNELS = (("Alpha", "alpha"), ("Transmission Weight", "translucency"))
AXIS_VECTORS = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


class Preset:
    def __init__(self, name, description, bump, properties, build):
        self.name = name
        self.description = description
        self.bump = bump
        self.properties = properties
        self.build = build

    def schema(self):
        properties = common_properties(self.bump)
        properties.update(self.properties)
        schema = obj(properties)
        schema["description"] = self.description
        return schema


def common_properties(bump):
    return {
        "scale": number("Feature size multiplier; 2 makes every feature half as big.", SMALLEST_FEATURE_MULTIPLIER, MAX_SCALE_FACTOR, 1.0),
        "seed": integer("Random seed; another seed gives another variation.", 0, MAX_SEED, 0),
        "coordinates": string("object: texture follows the object's local space in metres; uv: the UV map, one unit per UV square.", ["object", "uv"], "object"),
        "bump": number("Bump depth in millimetres.", 0.0, BUMP_DEPTH, bump),
    }


def seed_offset(seed):
    generator = random.Random(seed)
    return tuple(generator.uniform(-SEED_RANGE, SEED_RANGE) for _ in range(3))


def preset_vector(graph, params, salt=0):
    source = graph.node("ShaderNodeTexCoord").outputs["UV" if params["coordinates"] == "uv" else "Object"]
    mapping = graph.node("ShaderNodeMapping", vector_type="POINT")
    graph.set(mapping.inputs["Vector"], source)
    mapping.inputs["Location"].default_value = seed_offset(params["seed"] * 7919 + salt)
    factor = params["scale"]
    mapping.inputs["Scale"].default_value = (factor, factor, factor)
    return mapping.outputs["Vector"]


def stretched(graph, vector, axis, along, across):
    factors = tuple(along if value else across for value in AXIS_VECTORS[axis])
    return graph.vector_math("MULTIPLY", vector, factors)


def chosen_preset(presets, args):
    given = [name for name in presets if name in args]
    if len(given) != 1:
        raise bad_args(f"give exactly one preset: {', '.join(presets)}")
    return presets[given[0]], args[given[0]]


def surface_principled(material):
    tree = material.node_tree
    if tree is None:
        raise bad_args(f"{material.name} has no node tree")
    output = next((node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output), None)
    if output is None:
        output = next((node for node in tree.nodes if node.type == "OUTPUT_MATERIAL"), None)
    surface = output.inputs["Surface"] if output is not None else None
    if surface is None or not surface.is_linked or surface.links[0].from_node.type != "BSDF_PRINCIPLED":
        raise bad_args(f"{material.name} has no Principled BSDF feeding its material output")
    return output, surface.links[0].from_node


def displacement_of(graph, height, bump):
    node = graph.node("ShaderNodeDisplacement", {"Height": height, "Midlevel": 0.0, "Scale": bump / 1000.0}, space="OBJECT")
    return node.outputs["Displacement"]


def wire_channels(graph, material, output, shader, channels, bump):
    graph.set(shader.inputs["Base Color"], channels["base_color"])
    graph.set(shader.inputs["Roughness"], channels["roughness"])
    graph.set(shader.inputs["Metallic"], channels["metallic"])
    for socket_name, key in EXTRA_CHANNELS:
        if channels.get(key) is not None:
            graph.set(shader.inputs[socket_name], channels[key])
    if channels.get("alpha") is not None:
        material.surface_render_method = "DITHERED"
    if bump > 0.0 and channels.get("height") is not None:
        graph.set(output.inputs["Displacement"], displacement_of(graph, channels["height"], bump))
        material.displacement_method = "BUMP"
