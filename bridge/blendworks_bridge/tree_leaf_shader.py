"""Leaf shader values: variants, envelope and toothed edges."""

import math

LEAF_SHAPES = ("pointed", "ovate", "deltoid", "lanceolate", "lobed", "palmate", "needle", "tuft", "brush")
TUFT_NEEDLES = 9
TUFT_SPREAD = 0.9
TUFT_HALF_WIDTH = 0.012
TUFT_COUNTS = (0.75, 1.0, 1.4)
BRUSH_SLOPES = (0.7, 1.15)
BRUSH_HALF_WIDTH = 0.013
BRUSH_COUNTS = (0.8, 1.0, 1.25)
BRUSH_TIP = 0.85
VARIANTS = 3
ATTRIBUTE_NAMES = ("leaf_hue", "leaf_saturation", "leaf_value", "leaf_age", "leaf_damage", "leaf_shape", "leaf_seed")
STALK_HALF_WIDTH = 0.025
EDGE_SOFTNESS = 0.012
TEETH = {"ovate": (0.012, 22.0), "deltoid": (0.022, 16.0), "lanceolate": (0.008, 30.0), "lobed": (0.0, 1.0), "palmate": (0.02, 14.0)}
PALM_CENTRE = 0.36
OUTLINES = {
    "pointed": {"width": (0.85, 1.0, 1.2), "power": (0.75, 0.95, 0.6), "exponent": (1.0, 0.8, 1.25)},
    "ovate": {"width": (0.8, 1.0, 1.25), "power": (0.85, 1.05, 0.7), "exponent": (0.8, 0.6, 1.05)},
    "deltoid": {"width": (0.75, 1.0, 1.25), "power": (0.5, 0.7, 0.4), "exponent": (1.1, 0.85, 1.3)},
    "lanceolate": {"width": (0.65, 1.0, 1.4), "power": (0.85, 1.1, 0.7), "exponent": (0.7, 0.95, 0.55)},
    "lobed": {"width": (0.85, 1.0, 1.15), "lobes": (3.2, 4.4, 5.8), "depth": (0.5, 0.36, 0.55)},
    "palmate": {"width": (0.88, 1.0, 1.1), "lobes": (2.0, 2.5, 3.2), "reach": (0.9, 1.0, 1.12)},
}
YOUNG_COLOR = (0.2, 0.32, 0.05)
OLD_COLOR = (0.05, 0.055, 0.018)
DAMAGE_COLOR = (0.13, 0.075, 0.03)
SEED_STRETCH = (31.7, 17.3, 11.9)


def attribute(graph, name):
    geometry = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name).outputs["Fac"]
    instance = graph.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=name).outputs["Fac"]
    return graph.math("ADD", geometry, instance)


def leaf_values(graph):
    return {name: attribute(graph, name) for name in ATTRIBUTE_NAMES}


def seeded_vector(graph, vector, seed):
    shift = graph.vector_math("MULTIPLY", graph.node("ShaderNodeCombineXYZ", {"X": seed, "Y": seed, "Z": seed}).outputs["Vector"], SEED_STRETCH)
    return graph.vector_math("ADD", vector, shift)


def blade_coordinates(graph, uv, petiole):
    split = graph.node("ShaderNodeSeparateXYZ", {"Vector": uv})
    across = graph.math("ABSOLUTE", graph.math("SUBTRACT", split.outputs["X"], 0.5))
    along = split.outputs["Y"]
    blade = graph.math("DIVIDE", graph.math("SUBTRACT", along, petiole), max(1.0 - petiole, 1e-3)) if petiole > 0.0 else along
    return across, along, graph.math("MAXIMUM", blade, 0.0)


def variant(graph, shape_value, values):
    """The value of the variant the leaf_shape attribute picks: its first, middle or last third."""
    first, middle, last = values
    second = graph.math("MULTIPLY", graph.math("GREATER_THAN", shape_value, 1.0 / VARIANTS), middle - first)
    third = graph.math("MULTIPLY", graph.math("GREATER_THAN", shape_value, 2.0 / VARIANTS), last - middle)
    return graph.math("ADD", graph.math("ADD", second, third), first)


def envelope(graph, blade, power, exponent, reach):
    lifted = graph.math("POWER", graph.math("MAXIMUM", blade, 1e-4), power)
    swell = graph.math("SINE", graph.math("MULTIPLY", lifted, math.pi))
    return graph.math("MULTIPLY", graph.math("POWER", graph.math("MAXIMUM", swell, 0.0), exponent), reach)


def toothed(graph, half_width, blade, shape):
    depth, count = TEETH.get(shape, (0.0, 1.0))
    if depth <= 0.0:
        return half_width
    saw = graph.math("FRACT", graph.math("MULTIPLY", blade, count))
    return graph.math("SUBTRACT", half_width, graph.math("MULTIPLY", saw, depth))


def outline_width(graph, shape, blade, shape_value):
    if shape == "needle":
        taper = graph.math("SUBTRACT", 1.0, graph.math("POWER", blade, 6.0))
        return graph.math("MULTIPLY", graph.math("MULTIPLY", taper, 0.48), graph.map_range(blade, 0.0, 0.04))
    rows = OUTLINES[shape]
    width = variant(graph, shape_value, rows["width"])
    if shape == "lobed":
        lobes = variant(graph, shape_value, rows["lobes"])
        depth = variant(graph, shape_value, rows["depth"])
        bulge = graph.math("POWER", graph.math("ABSOLUTE", graph.math("SINE", graph.math("MULTIPLY", graph.math("MULTIPLY", blade, lobes), math.pi))), 0.6)
        lobed = graph.math("MULTIPLY_ADD", bulge, depth, graph.math("SUBTRACT", 1.0, depth))
        base = graph.math("MULTIPLY", envelope(graph, blade, 1.3, 0.65, 0.48), lobed)
    else:
        reach = {"pointed": 0.4, "ovate": 0.47, "deltoid": 0.48, "lanceolate": 0.48}[shape]
        base = envelope(graph, blade, variant(graph, shape_value, rows["power"]), variant(graph, shape_value, rows["exponent"]), reach)
    return graph.math("MULTIPLY", toothed(graph, base, blade, shape), width)


def palmate_inside(graph, across, blade, shape_value):
    rows = OUTLINES["palmate"]
    side = graph.math("MULTIPLY", across, 2.0)
    height = graph.math("SUBTRACT", blade, PALM_CENTRE)
    angle = graph.math("ARCTAN2", side, height)
    radius = graph.math("SQRT", graph.math("ADD", graph.math("MULTIPLY", side, side), graph.math("MULTIPLY", height, height)))
    lobes = graph.math("POWER", graph.math("ABSOLUTE", graph.math("COSINE", graph.math("MULTIPLY", angle, variant(graph, shape_value, rows["lobes"])))), 0.45)
    reach = graph.math("MULTIPLY", graph.math("MULTIPLY_ADD", lobes, 0.5, 0.42), variant(graph, shape_value, rows["reach"]))
    reach = graph.math("MULTIPLY", reach, variant(graph, shape_value, rows["width"]))
    reach = graph.math("MULTIPLY", reach, graph.map_range(angle, 2.45, 2.75, 1.0, 0.25))
    reach = graph.math("MULTIPLY", reach, 1.0 - PALM_CENTRE)
    teeth = graph.math("MULTIPLY", graph.math("FRACT", graph.math("MULTIPLY", angle, 9.0)), 0.025)
    return graph.math("SUBTRACT", graph.math("SUBTRACT", reach, teeth), radius)


def tuft_inside(graph, across, along, shape_value, needles):
    angle = graph.math("ARCTAN2", across, graph.math("MAXIMUM", along, 1e-4))
    radius = graph.math("SQRT", graph.math("ADD", graph.math("MULTIPLY", across, across), graph.math("MULTIPLY", along, along)))
    step = graph.math("DIVIDE", TUFT_SPREAD, variant(graph, shape_value, tuple(max(2.0, needles * share - 1.0) for share in TUFT_COUNTS)))
    slot = graph.math("DIVIDE", angle, step)
    nearest = graph.math("ABSOLUTE", graph.math("SUBTRACT", graph.math("FRACT", graph.math("ADD", slot, 0.5)), 0.5))
    lateral = graph.math("MULTIPLY", graph.math("MULTIPLY", nearest, step), radius)
    length = graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", graph.node("ShaderNodeTexWhiteNoise", {"W": graph.math("FLOOR", slot)}, noise_dimensions="1D").outputs["Value"], 0.35))
    inside = graph.math("SUBTRACT", TUFT_HALF_WIDTH, lateral)
    within = graph.map_range(graph.math("SUBTRACT", length, radius), 0.0, 0.02)
    return graph.math("MULTIPLY", graph.map_range(inside, 0.0, EDGE_SOFTNESS * 0.5), within), inside


def brush_needles(graph, across, along, rows, side, slope, salt):
    base = graph.math("SUBTRACT", along, graph.math("MULTIPLY", across, slope))
    slot = graph.math("ADD", graph.math("MULTIPLY", base, rows), graph.math("MULTIPLY", side, 0.5))
    nearest = graph.math("ABSOLUTE", graph.math("SUBTRACT", graph.math("FRACT", graph.math("ADD", slot, 0.5)), 0.5))
    lateral = graph.math("DIVIDE", nearest, graph.math("MULTIPLY", rows, math.sqrt(1.0 + slope * slope)))
    index = graph.math("ADD", graph.math("FLOOR", graph.math("ADD", slot, 0.5)), graph.math("MULTIPLY_ADD", side, 977.0, salt))
    chance = graph.node("ShaderNodeTexWhiteNoise", {"W": index}, noise_dimensions="1D").outputs["Value"]
    reach = graph.math("MULTIPLY", graph.math("MULTIPLY_ADD", chance, 0.26, 0.22), graph.map_range(base, BRUSH_TIP, 1.0, 1.0, 0.55))
    width = graph.math("MULTIPLY", graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", graph.math("DIVIDE", across, reach), 0.7)), BRUSH_HALF_WIDTH)
    inside = graph.math("SUBTRACT", width, lateral)
    within = graph.math("MULTIPLY", graph.map_range(graph.math("SUBTRACT", reach, across), 0.0, 0.01), graph.math("MULTIPLY", graph.map_range(base, -0.02, 0.0), graph.map_range(base, 1.0, 0.98)))
    return graph.math("MULTIPLY", graph.map_range(inside, 0.0, EDGE_SOFTNESS * 0.25), within), inside


def brush_inside(graph, across, along, shape_value, needles, side):
    """A shoot seen from the side: needles leave the midline of the card on both sides, slanting towards the tip at two angles that cross, as twisted needles do, with seeded lengths, shorter near the tip."""
    rows = variant(graph, shape_value, tuple(0.5 * needles * share for share in BRUSH_COUNTS))
    masks = [brush_needles(graph, across, along, rows, side, slope, 131.0 * number) for number, slope in enumerate(BRUSH_SLOPES)]
    opacity = graph.math("MAXIMUM", masks[0][0], masks[1][0])
    return opacity, graph.math("MAXIMUM", masks[0][1], masks[1][1])


def leaf_opacity(graph, shape, petiole, across, along, blade, shape_value, needles=TUFT_NEEDLES, side=0.0):
    if shape == "tuft":
        return tuft_inside(graph, across, along, shape_value, needles)
    if shape == "brush":
        return brush_inside(graph, across, along, shape_value, needles, side)
    if shape == "palmate":
        inside = palmate_inside(graph, across, blade, shape_value)
        edge = inside
    else:
        edge = graph.math("SUBTRACT", outline_width(graph, shape, blade, shape_value), across)
    blade_mask = graph.map_range(edge, 0.0, EDGE_SOFTNESS)
    ends = graph.map_range(along, 0.995, 0.97) if shape != "palmate" else 1.0
    blade_mask = graph.math("MULTIPLY", blade_mask, ends) if ends != 1.0 else blade_mask
    if petiole <= 0.0:
        return graph.math("MULTIPLY", blade_mask, graph.map_range(along, 0.0, 0.02)), edge
    stalk = graph.math("MULTIPLY", graph.map_range(across, STALK_HALF_WIDTH, STALK_HALF_WIDTH * 0.6), graph.map_range(along, petiole + 0.02, petiole, 1.0, 0.0))
    return graph.math("MAXIMUM", blade_mask, stalk), edge


def damage_masks(graph, vector, values, edge):
    damage = values["leaf_damage"]
    cells = graph.voronoi(vector, 9.0, randomness=1.0).outputs["Distance"]
    holes = graph.math("MULTIPLY", graph.map_range(graph.math("SUBTRACT", graph.math("MULTIPLY", damage, 0.22), cells), 0.0, 0.01), graph.math("GREATER_THAN", damage, 0.35))
    margin = graph.math("MULTIPLY", graph.map_range(edge, graph.math("MULTIPLY", damage, 0.09), 0.0), graph.math("GREATER_THAN", damage, 0.0))
    spots = graph.math("MULTIPLY", graph.map_range(graph.voronoi(vector, 24.0, randomness=1.0).outputs["Distance"], graph.math("MULTIPLY", damage, 0.14), 0.0), graph.math("GREATER_THAN", damage, 0.0))
    return holes, graph.math("MAXIMUM", margin, spots)


def aged(graph, colour, values, p):
    age = values["leaf_age"]
    young = graph.math("MULTIPLY", graph.math("MAXIMUM", graph.math("MULTIPLY", age, -1.0), 0.0), 0.55)
    old = graph.math("MULTIPLY", graph.math("MAXIMUM", age, 0.0), 0.35)
    colour = graph.mix(young, colour, p["young_color"])
    return graph.mix(old, colour, OLD_COLOR)


def toned(graph, colour, values):
    node = graph.node(
        "ShaderNodeHueSaturation",
        {
            "Hue": graph.math("ADD", values["leaf_hue"], 0.5),
            "Saturation": graph.math("ADD", values["leaf_saturation"], 1.0),
            "Value": graph.math("ADD", values["leaf_value"], 1.0),
            "Fac": 1.0,
            "Color": colour,
        },
    )
    return node.outputs["Color"]


def two_sided(graph, colour, p):
    backfacing = graph.node("ShaderNodeNewGeometry").outputs["Backfacing"]
    return graph.mix(graph.math("MULTIPLY", backfacing, 0.75), colour, p["underside_color"])


def thin_translucency(graph, p):
    shader = next((node for node in graph.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if shader is None or p["translucency"] <= 0.0:
        return
    shader.inputs["Thin Wall"].default_value = True
    shader.inputs["Subsurface Weight"].default_value = p["translucency"]
    shader.inputs["Subsurface Radius"].default_value = list(p["subsurface_tint"])
