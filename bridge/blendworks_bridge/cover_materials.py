from .natural import leaf_shape, leaf_veins, tone
from .procedural import Preset, preset_vector
from .schema import boolean, color, integer, number, string

LITTER_SHAPES = ("none", "leaf", "twig", "pebble")
BLADE_VEINS = 5
RIB_LIGHT = 0.35


def amount(description, default):
    return number(description, 0.0, 1.0, default)


def instance_random(graph):
    return graph.node("ShaderNodeObjectInfo").outputs["Random"]


def uv_parts(graph):
    split = graph.node("ShaderNodeSeparateXYZ", {"Vector": graph.node("ShaderNodeTexCoord").outputs["UV"]})
    return split.outputs["X"], split.outputs["Y"]


def geometry_attribute(graph, name):
    return graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name).outputs["Fac"]


def column_random(graph, u, columns, salt):
    column = graph.math("FLOOR", graph.math("MULTIPLY", u, columns))
    noise = graph.node("ShaderNodeTexWhiteNoise", noise_dimensions="2D")
    graph.set(noise.inputs["Vector"], graph.node("ShaderNodeCombineXYZ", {"X": column, "Y": salt}).outputs["Vector"])
    return noise.outputs["Value"]


def card_blades(graph, p, u, v):
    columns = p["card_blades"]
    first = column_random(graph, u, columns, 1.0)
    second = column_random(graph, u, columns, 2.0)
    third = column_random(graph, u, columns, 3.0)
    tallest = graph.math("MULTIPLY_ADD", first, 1.0 - p["card_height_min"], p["card_height_min"])
    along = graph.math("DIVIDE", v, tallest)
    lean = graph.math("MULTIPLY", graph.math("MULTIPLY", along, along), graph.math("MULTIPLY", graph.math("SUBTRACT", second, 0.5), 0.9))
    offset = graph.math("SUBTRACT", graph.math("SUBTRACT", graph.math("FRACT", graph.math("MULTIPLY", u, columns)), 0.5), lean)
    half = graph.math("MULTIPLY", graph.math("SUBTRACT", 1.0, along), 0.5 * p["card_blade_width"])
    inside = graph.map_range(graph.math("SUBTRACT", half, graph.math("ABSOLUTE", offset)), 0.0, 0.02)
    below_tip = graph.math("LESS_THAN", along, 1.0)
    alpha = graph.math("MULTIPLY", inside, below_tip)
    dry_start = graph.math("SUBTRACT", 2.0, graph.math("MULTIPLY", graph.math("LESS_THAN", third, p["dry_tips"]), graph.math("MULTIPLY_ADD", second, 0.3, 1.15)))
    return along, first, dry_start, alpha


def grass_blade(graph, p):
    u, v = uv_parts(graph)
    if p["card"]:
        along, blade, dry_start, alpha = card_blades(graph, p, u, v)
    else:
        along, blade, dry_start, alpha = v, geometry_attribute(graph, "gc_blade"), geometry_attribute(graph, "gc_dry"), None
    lower = graph.mix(graph.map_range(along, 0.0, 0.3), p["root_color"], p["color"])
    green = graph.mix(graph.map_range(along, 0.3, 1.0), lower, p["tip_color"])
    shift = graph.math("SUBTRACT", graph.math("FRACT", graph.math("ADD", blade, graph.math("MULTIPLY", instance_random(graph), 0.37))), 0.5)
    varied = graph.node("ShaderNodeHueSaturation", {
        "Hue": graph.math("MULTIPLY_ADD", shift, 0.06 * p["variation"], 0.5),
        "Saturation": graph.math("MULTIPLY_ADD", shift, 0.3 * p["variation"], 1.0),
        "Value": graph.math("MULTIPLY_ADD", shift, 0.6 * p["variation"], 1.0),
        "Color": green,
    }).outputs["Color"]
    ridge = graph.math("SUBTRACT", 1.0, graph.math("ABSOLUTE", graph.math("MULTIPLY_ADD", u, 2.0, -1.0)))
    if not p["card"]:
        varied = graph.node("ShaderNodeHueSaturation", {"Value": graph.math("MULTIPLY_ADD", ridge, RIB_LIGHT, 1.0 - 0.5 * RIB_LIGHT), "Color": varied}).outputs["Color"]
    dry = graph.map_range(graph.math("SUBTRACT", along, dry_start), 0.0, 0.08)
    veins = graph.math("ABSOLUTE", graph.math("SINE", graph.math("MULTIPLY", u, BLADE_VEINS * 6.2832 * (p["card_blades"] if p["card"] else 1.0))))
    if not p["card"]:
        veins = graph.math("MULTIPLY_ADD", ridge, 0.7, graph.math("MULTIPLY", veins, 0.3))
    straw = graph.mix(graph.map_range(along, 0.5, 1.0), p["dry_color"], [min(1.0, value * 1.35) for value in p["dry_color"][:3]])
    return {
        "base_color": graph.mix(dry, varied, straw),
        "roughness": graph.mix(dry, p["roughness"], min(1.0, p["roughness"] + 0.1), data_type="FLOAT"),
        "metallic": 0.0,
        "translucency": p["translucency"],
        "alpha": alpha,
        "height": veins,
    }


def litter_alpha(graph, p, u, v, field):
    across = graph.math("ABSOLUTE", graph.math("SUBTRACT", u, 0.5))
    if p["shape"] == "leaf":
        return leaf_shape(graph, across, v)
    if p["shape"] == "twig":
        ends = graph.math("MULTIPLY", graph.map_range(v, 0.0, 0.03), graph.map_range(v, 1.0, 0.97))
        return graph.math("MULTIPLY", graph.map_range(across, 0.25, 0.2), ends)
    if p["shape"] == "pebble":
        centred = graph.vector_math("SUBTRACT", graph.node("ShaderNodeCombineXYZ", {"X": u, "Y": v}).outputs["Vector"], (0.5, 0.5, 0.0))
        reach = graph.math("MULTIPLY_ADD", field, 0.25, graph.math("MULTIPLY", graph.vector_math("LENGTH", centred), 2.0))
        return graph.map_range(reach, 1.05, 0.95)
    return None


def litter(graph, p):
    u, v = uv_parts(graph)
    vector = graph.vector_math("ADD", preset_vector(graph, p), graph.math("MULTIPLY", instance_random(graph), 61.0))
    field = graph.noise(vector, 3.0, detail=3.0).outputs["Factor"]
    blotches = tone(graph, vector, 0.18, 0.3, 0.7, detail=5.0)
    speckle = tone(graph, vector, 0.03, 0.35, 0.65, detail=3.0)
    patches = graph.math("MULTIPLY_ADD", blotches, 1.0 - 0.35 * p["mottling"], graph.math("MULTIPLY", speckle, 0.35 * p["mottling"]))
    hue = graph.math("FRACT", graph.math("MULTIPLY", instance_random(graph), 7.13))
    body = graph.mix(graph.map_range(hue, 0.0, 1.0, 0.0, p["spread"]), p["color"], p["second_color"])
    shaded = graph.mix(patches, p["dark_color"], body)
    height = patches
    if p["shape"] in ("leaf", "none"):
        veins, _, _ = leaf_veins(graph, vector, {"coordinates": "uv", "scale": 1.0, "vein_pairs": p["vein_pairs"]})
        shaded = graph.mix(graph.math("MULTIPLY", veins, p["vein_contrast"]), shaded, p["vein_color"])
        height = graph.math("MULTIPLY_ADD", veins, 0.6, graph.math("MULTIPLY", patches, 0.4))
    return {
        "base_color": shaded,
        "roughness": graph.map_range(patches, 0.0, 1.0, max(0.0, p["roughness"] - 0.08), min(1.0, p["roughness"] + 0.05)),
        "metallic": 0.0,
        "height": height,
        "translucency": p["translucency"],
        "alpha": litter_alpha(graph, p, u, v, field),
    }


def cover_presets():
    return (
        Preset("grass_blade", "Grass blades on cards or blade geometry: darker root, green body and paler tip along the UV v, parallel veins, per-blade colour variation and dry straw tips.", 0.05, {
            "root_color": color("Colour at the root of the blade, linear RGB.", [0.05, 0.06, 0.02], False),
            "color": color("Colour of the blade body, linear RGB.", [0.07, 0.16, 0.03], False),
            "tip_color": color("Colour at the tip of a green blade, linear RGB.", [0.16, 0.24, 0.07], False),
            "dry_color": color("Colour of a dry tip, linear RGB.", [0.36, 0.29, 0.13], False),
            "variation": amount("Colour change from blade to blade.", 0.5),
            "dry_tips": amount("cards: share of the drawn blades with a dry tip (blade geometry carries its own share in gc_dry).", 0.25),
            "card": boolean("Draw blades into the alpha of a card, u across and v up, instead of colouring blade geometry.", False),
            "card_blades": integer("cards: blades across one card.", 2, 64, 12),
            "card_blade_width": amount("cards: width of a blade at its root as a share of its column.", 0.7),
            "card_height_min": amount("cards: the shortest blade as a share of the card height.", 0.45),
            "translucency": amount("Light passing through the blade: transmission weight.", 0.3),
            "roughness": amount("Average roughness.", 0.55),
            "coordinates": string("Grass blades read the UV map: u across, v from root to tip.", ["uv"], "uv"),
        }, grass_blade),
        Preset("litter", "Forest-floor litter: dry leaves with veins, twigs and pebbles, mottled per instance, with optional leaf, twig or pebble outlines in alpha for cards.", 0.4, {
            "shape": string("Outline cut with alpha from the UV square: leaf, twig (a strip along v), pebble (a rough disc) or none.", list(LITTER_SHAPES), "none"),
            "color": color("Main colour, linear RGB.", [0.2, 0.1, 0.035], False),
            "second_color": color("Second colour; each instance picks a colour between the two, linear RGB.", [0.28, 0.17, 0.05], False),
            "dark_color": color("Colour of the dark blotches, linear RGB.", [0.07, 0.04, 0.02], False),
            "vein_color": color("Vein colour for leaves, linear RGB.", [0.3, 0.2, 0.09], False),
            "vein_contrast": amount("How much the veins of a leaf stand out.", 0.5),
            "vein_pairs": integer("Lateral veins on each side of the midrib.", 2, 40, 6),
            "spread": amount("How far instances spread from color towards second_color.", 1.0),
            "mottling": amount("Strength of the fine speckle.", 0.5),
            "translucency": amount("Transmission weight.", 0.1),
            "roughness": amount("Average roughness.", 0.75),
            "coordinates": string("uv: the UV square holds one leaf, twig or pebble.", ["object", "uv"], "uv"),
        }, litter),
    )
