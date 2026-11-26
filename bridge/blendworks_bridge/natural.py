from .procedural import AXES, Preset, preset_vector, stretched
from . import tree_leaf_shader as leaf_shader
from .schema import boolean, color, integer, number, string

AXIS_CHOICE = list(AXES)
WAVE_FREQUENCY = 3.1831


def amount(description, default):
    return number(description, 0.0, 1.0, default)


def scaled(values, factor):
    return [min(1.0, value * factor) for value in values[:3]]


def share(graph, value, fraction, width=0.1):
    middle = 0.72 - 0.44 * fraction
    return graph.map_range(value, middle - width, middle + width)


def vector_offset(graph, vector, field, reach):
    centred = graph.vector_math("SUBTRACT", field, (0.5, 0.5, 0.5))
    return graph.vector_math("ADD", vector, graph.vector_math("MULTIPLY", centred, (reach, reach, reach)))


def tone(graph, vector, size, low, high, detail=6.0, roughness=0.55):
    field = graph.noise(vector, 1.0 / size, detail=detail, roughness=roughness).outputs["Factor"]
    return graph.map_range(field, low, high)


def bark(graph, p):
    vector = preset_vector(graph, p)
    spacing = p["fissure_spacing"]
    along = stretched(graph, vector, p["grain"], 0.12, 1.0)
    swirl = graph.noise(along, 0.25 / spacing, detail=3.0, roughness=0.5, distortion=0.6).outputs["Color"]
    warped = vector_offset(graph, along, swirl, 1.6 * spacing)
    ridges = graph.noise(warped, 1.0 / spacing, detail=5.0, roughness=0.6, distortion=0.3).outputs["Factor"]
    fine = graph.noise(vector_offset(graph, along, swirl, 0.6 * spacing), 3.4 / spacing, detail=3.0, roughness=0.55).outputs["Factor"]
    distance = graph.math("ABSOLUTE", graph.math("SUBTRACT", ridges, 0.5))
    fine_distance = graph.math("ABSOLUTE", graph.math("SUBTRACT", fine, 0.5))
    width = 0.006 + 0.04 * p["fissure_depth"]
    fissures = graph.map_range(distance, width * 0.35, width, 1.0, 0.0)
    cracks = graph.math("MULTIPLY", graph.map_range(fine_distance, 0.012, 0.03, 1.0, 0.0), 0.5 * p["fissure_depth"])
    shut = graph.math("MAXIMUM", fissures, cracks)
    plates = tone(graph, along, spacing * 2.5, 0.3, 0.7)
    lichen = tone(graph, vector, spacing * 9.0, 0.4, 0.66, detail=4.0)
    plate_color = graph.mix(plates, scaled(p["color"], 0.7), scaled(p["color"], 1.45))
    fissure_color = p["fissure_color"]
    lichen_share = graph.math("MULTIPLY", lichen, 0.35)
    depth = 0.35 + 0.65 * p["fissure_depth"]
    if p["upper_end"] > 0.0:
        upper = upper_share(graph, p, vector)
        flakes = tone(graph, along, spacing * 0.6, 0.25, 0.75, detail=4.0)
        plate_color = graph.mix(upper, plate_color, graph.mix(flakes, scaled(p["upper_color"], 0.55), scaled(p["upper_color"], 1.35)))
        fissure_color = graph.mix(upper, fissure_color, scaled(p["upper_color"], 0.35))
        shut = graph.math("MULTIPLY", shut, graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", upper, 1.0 - p["upper_fissures"])))
        lichen_share = graph.math("MULTIPLY", lichen_share, graph.math("SUBTRACT", 1.0, upper))
    surface = graph.mix(lichen_share, plate_color, p["lichen_color"])
    if p["lenticels"] > 0.0:
        rows = stretched(graph, vector, p["grain"], 4.0 / spacing, 0.6 / spacing)
        dashes = graph.noise(rows, 1.0, detail=1.0, roughness=0.5, distortion=0.15).outputs["Factor"]
        marks = graph.math("MULTIPLY", graph.map_range(dashes, 0.6, 0.62), p["lenticels"])
        shut = graph.math("MAXIMUM", graph.math("MULTIPLY", shut, 1.0 - 0.85 * p["lenticels"]), marks)
    return {
        "base_color": graph.mix(graph.math("MULTIPLY", shut, 0.92), surface, fissure_color),
        "roughness": graph.map_range(plates, 0.0, 1.0, max(0.0, p["roughness"] - 0.1), min(1.0, p["roughness"] + 0.06)),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", plates, 0.2, graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", shut, depth))),
    }


def upper_share(graph, p, vector):
    """0 below upper_start and 1 above upper_end, by height in the object's own space, with a ragged seeded edge between."""
    height = graph.node("ShaderNodeSeparateXYZ", {"Vector": graph.node("ShaderNodeTexCoord").outputs["Object"]}).outputs["Z"]
    start, end = p["upper_start"], max(p["upper_end"], p["upper_start"] + 1e-3)
    ragged = graph.math("MULTIPLY", graph.math("SUBTRACT", graph.noise(vector, 1.5 / max(p["fissure_spacing"], 1e-3) / 8.0, detail=3.0).outputs["Factor"], 0.5), 0.6 * (end - start))
    return graph.map_range(graph.math("ADD", height, ragged), start, end)


def moss(graph, p):
    vector = preset_vector(graph, p)
    size = p["clump_size"]
    patches = graph.noise(vector, 1.0 / (size * 14.0), detail=5.0, roughness=0.6, distortion=0.5).outputs["Factor"]
    cover = graph.map_range(patches, 0.2 + 0.25 * p["patchiness"], 0.4 + 0.25 * p["patchiness"])
    tufts = graph.noise(vector, 1.0 / size, detail=9.0, roughness=0.68).outputs["Factor"]
    shoots = graph.noise(vector, 1.0 / (size * 0.25), detail=4.0, roughness=0.7).outputs["Factor"]
    brightness = graph.math("MULTIPLY_ADD", graph.map_range(tufts, 0.42, 0.58), 0.7, graph.math("MULTIPLY", graph.map_range(shoots, 0.42, 0.58), 0.3))
    green = graph.mix(brightness, scaled(p["color"], 0.45), p["tip_color"])
    bare = graph.mix(graph.map_range(shoots, 0.42, 0.58), scaled(p["ground_color"], 0.5), scaled(p["ground_color"], 1.3))
    relief = graph.math("MULTIPLY_ADD", graph.map_range(tufts, 0.25, 0.75), 0.75, graph.math("MULTIPLY", shoots, 0.25))
    return {
        "base_color": graph.mix(cover, bare, green),
        "roughness": graph.map_range(cover, 0.0, 1.0, 0.92, 0.82),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY", graph.math("MULTIPLY_ADD", cover, relief, 0.0), p["height"]),
    }


def leaf_shape(graph, across, along):
    swell = graph.math("SINE", graph.math("MULTIPLY", graph.math("POWER", along, 0.75), 3.14159))
    reach = graph.math("MULTIPLY", swell, 0.4)
    inside = graph.math("SUBTRACT", reach, across)
    ends = graph.math("MULTIPLY", graph.map_range(along, 0.0, 0.03), graph.map_range(along, 1.0, 0.97))
    return graph.math("MULTIPLY", graph.map_range(inside, 0.0, 0.012), ends)


def leaf_layout(graph, p):
    source = graph.node("ShaderNodeTexCoord").outputs["UV" if p["coordinates"] == "uv" else "Object"]
    return graph.vector_math("MULTIPLY", source, (p["scale"],) * 3)


def blade_veins(graph, vector, p, across, blade):
    wobble = graph.math("MULTIPLY", graph.noise(vector, 7.0, detail=3.0).outputs["Factor"], 0.25)
    count = p["vein_pairs"]
    slant = graph.math("SUBTRACT", graph.math("MULTIPLY", blade, count), graph.math("MULTIPLY", across, count * 1.7))
    lateral_position = graph.math("ABSOLUTE", graph.math("SUBTRACT", graph.math("FRACT", graph.math("ADD", slant, wobble)), 0.5))
    fade = graph.map_range(across, 0.0, 0.42, 1.0, 0.25)
    laterals = graph.math("MULTIPLY", graph.map_range(lateral_position, 0.5 - 0.06, 0.5), fade)
    midrib = graph.map_range(across, 0.011, 0.02, 1.0, 0.0)
    net = graph.voronoi(vector, 38.0, feature="DISTANCE_TO_EDGE").outputs["Distance"]
    fine = graph.math("MULTIPLY", graph.map_range(net, 0.0, 0.05, 1.0, 0.0), 0.35)
    return graph.math("MAXIMUM", graph.math("MAXIMUM", midrib, graph.math("MULTIPLY", laterals, 0.8)), fine)


def leaf_veins(graph, vector, p):
    split = graph.node("ShaderNodeSeparateXYZ", {"Vector": leaf_layout(graph, p)})
    centre = 0.5 if p["coordinates"] == "uv" else 0.0
    across = graph.math("ABSOLUTE", graph.math("SUBTRACT", split.outputs["X"], centre))
    along = split.outputs["Y"]
    wobble = graph.math("MULTIPLY", graph.noise(vector, 7.0, detail=3.0).outputs["Factor"], 0.25)
    count = p["vein_pairs"]
    slant = graph.math("SUBTRACT", graph.math("MULTIPLY", along, count), graph.math("MULTIPLY", across, count * 1.7))
    lateral_position = graph.math("ABSOLUTE", graph.math("SUBTRACT", graph.math("FRACT", graph.math("ADD", slant, wobble)), 0.5))
    fade = graph.map_range(across, 0.0, 0.42, 1.0, 0.25)
    laterals = graph.math("MULTIPLY", graph.map_range(lateral_position, 0.5 - 0.06, 0.5), fade)
    midrib = graph.map_range(across, 0.011, 0.02, 1.0, 0.0)
    net = graph.voronoi(vector, 38.0, feature="DISTANCE_TO_EDGE").outputs["Distance"]
    fine = graph.math("MULTIPLY", graph.map_range(net, 0.0, 0.05, 1.0, 0.0), 0.35)
    return graph.math("MAXIMUM", graph.math("MAXIMUM", midrib, graph.math("MULTIPLY", laterals, 0.8)), fine), across, along


def leaf(graph, p):
    values = leaf_shader.leaf_values(graph)
    vector = leaf_shader.seeded_vector(graph, preset_vector(graph, p), values["leaf_seed"])
    layout = leaf_layout(graph, p)
    if p["coordinates"] == "uv":
        across, along, blade = leaf_shader.blade_coordinates(graph, layout, p["petiole"])
    else:
        split = graph.node("ShaderNodeSeparateXYZ", {"Vector": layout})
        across, along = graph.math("ABSOLUTE", split.outputs["X"]), split.outputs["Y"]
        blade = along
    veins = blade_veins(graph, vector, p, across, blade)
    blotches = tone(graph, vector, 0.15, 0.32, 0.68, detail=5.0)
    speckle = tone(graph, vector, 0.012, 0.4, 0.6, detail=3.0)
    blade_colour = graph.mix(graph.math("MULTIPLY_ADD", blotches, 0.8, graph.math("MULTIPLY", speckle, 0.2)), p["dark_color"], p["color"])
    colour = graph.mix(graph.math("MULTIPLY", veins, p["vein_contrast"]), blade_colour, p["vein_color"])
    side = graph.math("GREATER_THAN", graph.node("ShaderNodeSeparateXYZ", {"Vector": layout}).outputs["X"], 0.5 if p["coordinates"] == "uv" else 0.0)
    opacity, edge = leaf_shader.leaf_opacity(graph, p["shape"], p["petiole"], across, along, blade, values["leaf_shape"], p["needles"], side)
    holes, browned = leaf_shader.damage_masks(graph, vector, values, edge)
    colour = leaf_shader.aged(graph, colour, values, p)
    colour = graph.mix(browned, colour, leaf_shader.DAMAGE_COLOR)
    colour = leaf_shader.two_sided(graph, leaf_shader.toned(graph, colour, values), p)
    leaf_shader.thin_translucency(graph, p)
    channels = {
        "base_color": colour,
        "roughness": graph.map_range(veins, 0.0, 1.0, p["roughness"], max(0.0, p["roughness"] - 0.12)),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", veins, 0.7, graph.math("MULTIPLY", speckle, 0.3)),
    }
    cutout = graph.math("MULTIPLY", opacity, graph.math("SUBTRACT", 1.0, holes)) if p["cutout"] else None
    if p["alpha"] < 1.0:
        cutout = graph.math("MULTIPLY", cutout, p["alpha"]) if cutout is not None else p["alpha"]
    channels["alpha"] = cutout
    return channels


def soil(graph, p):
    vector = preset_vector(graph, p)
    size = p["clod_size"]
    wet = 1.0 - 0.55 * p["moisture"]
    clods = tone(graph, vector, size * 4.0, 0.41, 0.59, detail=7.0, roughness=0.6)
    crumbs = tone(graph, vector, size * 0.7, 0.42, 0.58, detail=6.0, roughness=0.65)
    grit = tone(graph, vector, size * 0.07, 0.4, 0.6, detail=3.0)
    lumps = graph.math("MULTIPLY_ADD", clods, 0.5, graph.math("MULTIPLY_ADD", crumbs, 0.35, graph.math("MULTIPLY", grit, 0.15)))
    ground = graph.mix(lumps, scaled(p["color"], 0.1 * wet), scaled(p["color"], 2.1 * wet))
    stones = graph.voronoi(vector, 1.0 / (size * 2.2), randomness=1.0)
    sizes = graph.map_range(graph.noise(vector, 1.0 / (size * 5.0), detail=1.0).outputs["Factor"], 0.35, 0.65, 0.1, 0.34)
    sparse = graph.map_range(graph.noise(vector, 1.0 / (size * 9.0), detail=2.0).outputs["Factor"], 0.62 - 0.3 * p["pebbles"], 0.78 - 0.3 * p["pebbles"])
    pebble = graph.math("MULTIPLY", graph.map_range(graph.math("SUBTRACT", sizes, stones.outputs["Distance"]), 0.0, 0.05), sparse)
    pebble_tone = graph.mix(tone(graph, vector, size * 0.6, 0.4, 0.6), scaled(p["pebble_color"], 0.5), scaled(p["pebble_color"], 1.2))
    return {
        "base_color": graph.mix(pebble, ground, pebble_tone),
        "roughness": graph.map_range(crumbs, 0.0, 1.0, max(0.0, p["roughness"] - 0.35 * p["moisture"] - 0.06), min(1.0, p["roughness"] - 0.35 * p["moisture"] + 0.06)),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", clods, 0.35, graph.math("MULTIPLY_ADD", crumbs, 0.4, graph.math("MULTIPLY_ADD", pebble, 0.9, graph.math("MULTIPLY", grit, 0.1)))),
    }


def sand(graph, p):
    vector = preset_vector(graph, p)
    spacing = p["ripple_spacing"]
    along = p["ripple_direction"]
    swirl = graph.noise(vector, 1.0 / (spacing * 5.0), detail=2.0, distortion=0.5).outputs["Color"]
    waves = graph.wave(vector_offset(graph, vector, swirl, spacing * 4.0), 1.0 / (spacing * WAVE_FREQUENCY), 6.0, 2.0, AXES[along])
    ripples = waves.outputs["Factor"]
    drifts = tone(graph, vector, spacing * 9.0, 0.45, 0.55, detail=4.0)
    strength = tone(graph, vector, spacing * 16.0, 0.3, 0.7, detail=2.0)
    crests = graph.math("MULTIPLY", graph.map_range(ripples, 0.35, 0.65), graph.math("MULTIPLY_ADD", strength, 0.8, 0.2))
    dune = graph.math("MULTIPLY_ADD", crests, p["ripples"] * 0.5, graph.math("MULTIPLY", drifts, 1.0 - 0.5 * p["ripples"]))
    grain = tone(graph, vector, 0.0016, 0.35, 0.65, detail=2.0, roughness=0.5)
    flecks = graph.voronoi(vector, 1.0 / 0.004, randomness=1.0).outputs["Distance"]
    fleck = graph.math("MULTIPLY", graph.map_range(flecks, 0.12, 0.22, 1.0, 0.0), graph.map_range(graph.noise(vector, 40.0, detail=1.0).outputs["Factor"], 0.42, 0.58))
    damp = 1.0 - 0.45 * p["moisture"]
    body = graph.mix(graph.math("MULTIPLY_ADD", dune, 0.7, graph.math("MULTIPLY", grain, 0.3)), scaled(p["color"], 0.2 * damp), scaled(p["color"], 1.6 * damp))
    return {
        "base_color": graph.mix(graph.math("MULTIPLY", fleck, 0.8), body, p["fleck_color"]),
        "roughness": graph.map_range(grain, 0.0, 1.0, max(0.0, p["roughness"] - 0.1 - 0.2 * p["moisture"]), min(1.0, p["roughness"] + 0.05)),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", ripples, p["ripples"] * 0.8, graph.math("MULTIPLY", grain, 0.2)),
    }


def grass_ground(graph, p):
    vector = preset_vector(graph, p)
    size = p["tuft_size"]
    tufts = graph.noise(vector, 1.0 / size, detail=6.0, roughness=0.6, distortion=0.4).outputs["Factor"]
    cover = graph.map_range(tufts, 0.6 - 0.4 * p["density"], 0.68 - 0.4 * p["density"])
    blades = graph.noise(vector, 1.0 / (size * 0.12), detail=6.0, roughness=0.72).outputs["Factor"]
    blade_tone = graph.map_range(blades, 0.41, 0.59)
    dry = graph.map_range(graph.noise(vector, 1.0 / (size * 8.0), detail=4.0, distortion=0.4).outputs["Factor"], 0.5 - 0.35 * p["dryness"] + 0.1, 0.6 - 0.35 * p["dryness"] + 0.2)
    leaves = graph.mix(dry, graph.mix(blade_tone, scaled(p["color"], 0.25), scaled(p["color"], 2.0)), graph.mix(blade_tone, scaled(p["dry_color"], 0.35), scaled(p["dry_color"], 1.4)))
    earth = graph.mix(graph.map_range(blades, 0.4, 0.6), scaled(p["soil_color"], 0.4), scaled(p["soil_color"], 1.2))
    return {
        "base_color": graph.mix(cover, earth, leaves),
        "roughness": graph.map_range(blade_tone, 0.0, 1.0, max(0.0, p["roughness"] - 0.08), min(1.0, p["roughness"] + 0.05)),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", cover, graph.math("MULTIPLY_ADD", blade_tone, 0.4, 0.45), graph.math("MULTIPLY", graph.math("SUBTRACT", 1.0, cover), 0.1)),
    }


def natural_presets():
    return (
        Preset("bark", "Tree bark: plates split by warped, ridged fissures that run along the grain, with lichen tint; sized in metres.", 8.0, {
            "color": color("Plate colour, linear RGB.", [0.14, 0.1, 0.07], False),
            "fissure_color": color("Colour deep in the fissures, linear RGB.", [0.03, 0.022, 0.016], False),
            "lichen_color": color("Colour of the pale lichen and dry patches, linear RGB.", [0.16, 0.15, 0.1], False),
            "grain": string("Axis the fissures run along (z for an upright trunk).", AXIS_CHOICE, "z"),
            "fissure_depth": amount("How wide and deep the fissures are; 0 gives shallow cracks, 1 deep furrows.", 0.6),
            "fissure_spacing": number("Distance between fissures in metres.", 0.005, 1.0, 0.04),
            "lenticels": amount("Dark dashes across the grain, as on birch and cherry bark; 0 none.", 0.0),
            "upper_color": color("Plate colour of the thin, flaking bark high on the tree, as the orange-red upper trunk and limbs of a Scots pine, linear RGB; used above upper_start.", [0.45, 0.17, 0.07], False),
            "upper_start": number("Height in metres, in the object's own space, where the bark starts to turn into the upper bark.", 0.0, 1000.0, 0.0),
            "upper_end": number("Height in metres above which the bark is all upper bark, with a ragged edge between; 0 gives no upper bark.", 0.0, 1000.0, 0.0),
            "upper_fissures": amount("How deep the upper bark's fissures are compared with the lower bark's: thin papery plates have shallow ones.", 0.25),
            "roughness": amount("Average roughness.", 0.9),
        }, bark),
        Preset("moss", "Moss: clumps of fine green tufts in patches over bare ground.", 4.0, {
            "color": color("Dark moss colour, linear RGB.", [0.03, 0.09, 0.012], False),
            "tip_color": color("Colour of the sunlit tuft tips, linear RGB.", [0.15, 0.27, 0.04], False),
            "ground_color": color("Colour of the bare ground between the patches, linear RGB.", [0.06, 0.045, 0.03], False),
            "patchiness": amount("How patchy the cover is: 0 covers everything, 1 leaves mostly bare ground.", 0.5),
            "clump_size": number("Size of one tuft clump in metres.", 0.002, 0.5, 0.03),
            "height": amount("How tall the tufts stand: scales the relief of the bump.", 0.7),
        }, moss),
        Preset("leaf", "A leaf blade with a midrib, lateral veins and a fine vein net; fits one UV square, optional outline alpha and translucency.", 0.6, {
            "color": color("Blade colour, linear RGB.", [0.045, 0.15, 0.025], False),
            "dark_color": color("Colour of the darker blotches, linear RGB.", [0.01, 0.04, 0.006], False),
            "vein_color": color("Vein colour, linear RGB.", [0.32, 0.42, 0.12], False),
            "vein_contrast": amount("How much the veins stand out from the blade.", 0.7),
            "vein_pairs": integer("Lateral veins on each side of the midrib along the leaf (one UV unit or one metre long).", 2, 40, 7),
            "alpha": amount("Opacity of the leaf; below 1 the material blends.", 1.0),
            "cutout": boolean("Cut the leaf outline (shape) out of the card with alpha; needs a UV map.", False),
            "shape": string("Leaf outline cut out of the unit UV square: pointed, ovate, deltoid (birch), lanceolate (willow, olive), lobed (oak), palmate (maple), needle, tuft (a fan of needles) or brush (a shoot with needles on both sides, for cards along a conifer's twigs); the face attribute leaf_shape varies it per leaf.", list(leaf_shader.LEAF_SHAPES), "pointed"),
            "needles": integer("tuft shape: needles in a fan, the three leaf shapes using 0.75, 1 and 1.4 times as many; brush shape: needles on each side along the card, 0.8, 1 and 1.25 times as many.", 3, 64, leaf_shader.TUFT_NEEDLES),
            "petiole": amount("Share of the card along v taken by the leaf stalk, drawn as a thin stalk; tree_leaves clusters use the same share.", 0.0),
            "translucency": amount("Light passing through the thin blade: the thin-walled subsurface weight, lit from behind.", 0.35),
            "subsurface_tint": color("Tint of the light passing through the blade.", [1.0, 0.9, 0.35], False),
            "underside_color": color("Colour of the paler underside, seen on back faces, linear RGB.", [0.09, 0.15, 0.05], False),
            "young_color": color("Colour of young leaves (attribute leaf_age below 0), linear RGB.", list(leaf_shader.YOUNG_COLOR), False),
            "roughness": amount("Average roughness.", 0.5),
            "coordinates": string("uv: the UV square holds one leaf, midrib at u 0.5, tip at v 1; object: one metre of local space, midrib at x 0; use scale to size it.", ["object", "uv"], "uv"),
        }, leaf),
        Preset("soil", "Soil: dark crumbs and clods with sparse pebbles, darker and glossier when moist.", 6.0, {
            "color": color("Dry soil colour, linear RGB.", [0.15, 0.1, 0.065], False),
            "pebble_color": color("Pebble colour, linear RGB.", [0.28, 0.25, 0.2], False),
            "moisture": amount("How damp the soil is: darker and less rough.", 0.3),
            "pebbles": amount("How many pebbles lie in the soil.", 0.6),
            "clod_size": number("Size of the crumbs in metres; clods are four times as big.", 0.002, 0.5, 0.025),
            "roughness": amount("Average roughness when dry.", 0.95),
        }, soil),
        Preset("sand", "Sand: fine grain, dark mineral flecks and soft wind ripples a few centimetres apart.", 3.0, {
            "color": color("Dry sand colour, linear RGB.", [0.5, 0.38, 0.22], False),
            "fleck_color": color("Colour of the dark mineral flecks, linear RGB.", [0.09, 0.07, 0.05], False),
            "ripples": amount("How strong the wind ripples are.", 0.8),
            "ripple_spacing": number("Distance between ripple crests in metres.", 0.005, 2.0, 0.07),
            "ripple_direction": string("Axis the wind blows along; the crests lie across it.", AXIS_CHOICE, "x"),
            "moisture": amount("How damp the sand is: darker and less rough.", 0.0),
            "roughness": amount("Average roughness when dry.", 0.9),
        }, sand),
        Preset("grass_ground", "Grass ground: tufts of green and dry blades over bare soil, seen from above.", 8.0, {
            "color": color("Green blade colour, linear RGB.", [0.05, 0.13, 0.02], False),
            "dry_color": color("Dry blade colour, linear RGB.", [0.22, 0.17, 0.06], False),
            "soil_color": color("Bare soil between the tufts, linear RGB.", [0.07, 0.05, 0.03], False),
            "density": amount("How much of the ground the grass covers.", 0.75),
            "dryness": amount("Share of dry, yellow grass.", 0.3),
            "tuft_size": number("Size of one tuft in metres.", 0.005, 2.0, 0.12),
            "roughness": amount("Average roughness.", 0.85),
        }, grass_ground),
    )
