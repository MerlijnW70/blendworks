"""The stone preset's natural rock: lithology grains, pits, cracks and colour, with weathering and relief on top."""
from . import rock_lithology, rock_relief, rock_weathering
from .limits import FRACTION
from .procedural import preset_vector
from .schema import boolean, number, string

GRAIN_WARP = 0.35
MOTTLE_SIZE = 0.35
MOTTLE_SPREAD = 0.22
CRACK_WIDTH = 0.0004
CRACK_KEEP = 0.45
FRACTURE_SIZE = 0.025
FRACTURE_STEPS = 5.0
SURFACE_SIZE = 0.04
CONCHOIDAL_RINGS = 0.012


def shifted_vector(graph, p):
    """Object space in metres, offset per object by its random number so linked copies of one rock differ."""
    vector = preset_vector(graph, p)
    random = graph.node("ShaderNodeObjectInfo").outputs["Random"]
    return graph.vector_math("ADD", vector, graph.vector_math("MULTIPLY", graph.node("ShaderNodeCombineXYZ", {"X": random, "Y": random, "Z": random}).outputs[0], (173.0, 311.0, 97.0)))


def warped(graph, vector, size, reach):
    field = graph.noise(vector, 1.0 / size, detail=2.0, roughness=0.5).outputs["Color"]
    centred = graph.vector_math("SUBTRACT", field, (0.5, 0.5, 0.5))
    return graph.vector_math("ADD", vector, graph.vector_math("MULTIPLY", centred, (reach, reach, reach)))


def mottle(graph, vector):
    field = graph.noise(vector, 1.0 / MOTTLE_SIZE, detail=4.0, roughness=0.55).outputs["Factor"]
    return graph.map_range(field, 0.3, 0.7, 1.0 - MOTTLE_SPREAD, 1.0 + MOTTLE_SPREAD)


def minerals_of(graph, draw, minerals):
    """Colour and relief of the mineral a uniform draw picks by the minerals' shares."""
    color = graph.rgb(minerals[0]["color"])
    relief = graph.value(minerals[0]["relief"])
    for index, mineral in enumerate(minerals[1:], start=1):
        inside = graph.math("LESS_THAN", draw, sum(item["share"] for item in minerals[index:]))
        color = graph.mix(inside, color, mineral["color"])
        relief = graph.mix(inside, relief, mineral["relief"], "FLOAT")
    return color, relief


def grains(graph, vector, grain):
    cells = graph.voronoi(warped(graph, vector, 3.0 * grain, GRAIN_WARP * grain), 1.0 / grain)
    return cells, graph.node("ShaderNodeSeparateColor", {"Color": cells.outputs["Color"]}).outputs


def granite(graph, vector, table):
    """Interlocking mineral grains at two sizes: feldspar crystals (the coarse Voronoi cells that draw below the crystal
    share) set in a groundmass of finer quartz, biotite and feldspar grains, each grain one mineral by a random draw with the
    modal shares, its tone varied within the grain; quartz stands proud and biotite lies low (differential weathering)."""
    crystals, crystals_draw = grains(graph, vector, table["crystals"]["grain"])
    groundmass, groundmass_draw = grains(graph, vector, table["groundmass"]["grain"])
    crystal_color, crystal_relief = minerals_of(graph, crystals_draw[1], table["crystals"]["minerals"])
    ground_color, ground_relief = minerals_of(graph, groundmass_draw[0], table["groundmass"]["minerals"])
    is_crystal = graph.math("LESS_THAN", crystals_draw[0], table["crystals"]["share"])
    color = graph.mix(is_crystal, ground_color, crystal_color)
    relief = graph.mix(is_crystal, ground_relief, crystal_relief, "FLOAT")
    within = graph.noise(vector, 1.0 / (0.25 * table["groundmass"]["grain"]), detail=2.0).outputs["Factor"]
    tone = graph.math("MULTIPLY", graph.map_range(graph.mix(is_crystal, groundmass_draw[2], crystals_draw[2], "FLOAT"), 0.0, 1.0, 0.82, 1.18), graph.map_range(within, 0.3, 0.7, 0.9, 1.1))
    color = graph.mix(1.0, color, graph.node("ShaderNodeCombineXYZ", {"X": tone, "Y": tone, "Z": tone}).outputs[0], blend="MULTIPLY")
    edge = graph.mix(is_crystal, graph.voronoi(warped(graph, vector, 3.0 * table["groundmass"]["grain"], GRAIN_WARP * table["groundmass"]["grain"]), 1.0 / table["groundmass"]["grain"], feature="DISTANCE_TO_EDGE").outputs["Distance"], 1.0, "FLOAT")
    seams = graph.map_range(edge, 0.0, 0.08, -0.5, 0.0)
    return color, graph.math("ADD", graph.math("MULTIPLY", relief, 0.5), seams)


def sandstone(graph, vector, table):
    """Sand grains as fine speckle over beds and laminae: bands along the object's own z (the stone's short axis, which lies on
    the bedding of a slab), warped, at the stated bed and lamina thicknesses; iron bands darken some beds; laminae are
    grooves where the softer layers weather back."""
    along = warped(graph, vector, 3.0 * table["bed"], 0.5 * table["bed"])
    height = graph.node("ShaderNodeSeparateXYZ", {"Vector": along}).outputs["Z"]
    beds = graph.math("SINE", graph.math("MULTIPLY", height, 6.2832 / table["bed"]))
    laminae = graph.math("SINE", graph.math("MULTIPLY", height, 6.2832 / table["lamina"]))
    iron = graph.map_range(graph.math("MULTIPLY_ADD", beds, 0.5, graph.math("MULTIPLY", graph.noise(vector, 4.0, detail=2.0).outputs["Factor"], 0.8)), 0.55, 0.85)
    speck = graph.noise(vector, 0.5 / max(table["grain"], 1e-4), detail=1.0).outputs["Factor"]
    color = graph.mix(graph.math("MULTIPLY", iron, 0.45), table["color"], table["band_color"])
    fine = graph.map_range(graph.math("MULTIPLY_ADD", laminae, 0.04, speck), 0.2, 1.1, 0.88, 1.1)
    color = graph.mix(1.0, color, graph.node("ShaderNodeCombineXYZ", {"X": fine, "Y": fine, "Z": fine}).outputs[0], blend="MULTIPLY")
    groove = graph.math("MULTIPLY", graph.map_range(laminae, -1.0, -0.4, -1.0, 0.0), table["relief_share"]["bedding"])
    return color, graph.math("ADD", groove, graph.math("MULTIPLY", graph.math("SUBTRACT", speck, 0.5), 2.0 * table["relief_share"]["grain"]))


def fine_grained(graph, vector, table, speck_color):
    speck = graph.noise(vector, 0.5 / max(table["grain"], 1e-4), detail=2.0, roughness=0.6).outputs["Factor"]
    color = graph.mix(graph.map_range(speck, 0.55, 0.75), table["color"], speck_color)
    return color, graph.math("MULTIPLY", graph.math("SUBTRACT", speck, 0.5), 2.0 * table["relief_share"]["grain"])


def pits(graph, vector, table):
    """Round pits (solution pits on limestone, vesicles in basalt): Voronoi cells of twice the pit size, a pit in the share of
    cells that gives the stated cover, each a bowl of its own radius."""
    size = table["pits"]["size"]
    cells = graph.voronoi(vector, 0.5 / size)
    chosen = graph.math("LESS_THAN", graph.node("ShaderNodeSeparateColor", {"Color": cells.outputs["Color"]}).outputs[0], min(1.0, 4.0 * table["pits"]["cover"]))
    radius = graph.math("MULTIPLY_ADD", graph.node("ShaderNodeSeparateColor", {"Color": cells.outputs["Color"]}).outputs[1], 0.25, 0.15)
    bowl = graph.map_range(graph.math("DIVIDE", cells.outputs["Distance"], radius), 0.0, 1.0, -1.0, 0.0, "SMOOTHSTEP")
    return graph.math("MULTIPLY", graph.math("MULTIPLY", bowl, chosen), table["relief_share"]["pits"])


def cracks(graph, vector, table):
    """Hairline cracks: the edges of warped Voronoi cells at the stated spacing, a fraction of them kept by a noise, each about
    CRACK_WIDTH wide."""
    spacing = table["crack_spacing"]
    network = graph.voronoi(warped(graph, vector, spacing, 0.35 * spacing), 1.0 / spacing, feature="DISTANCE_TO_EDGE").outputs["Distance"]
    line = graph.map_range(graph.math("MULTIPLY", network, spacing), 0.0, CRACK_WIDTH, 1.0, 0.0)
    keep = graph.map_range(graph.noise(vector, 2.5 / spacing, detail=2.0).outputs["Factor"], CRACK_KEEP, CRACK_KEEP + 0.08)
    return graph.math("MULTIPLY", line, keep)


def fracture_relief(graph, vector, table):
    """Rough relief of a fresh fracture face: a hackly surface of ridged noise at FRACTURE_SIZE broken into steps (a break
    runs along grain boundaries and cleavage planes and jumps between them), and for fine-grained rock conchoidal ripples,
    rings about the object's origin like the shell-like faces of a brittle break."""
    ridged = graph.math("SUBTRACT", 0.5, graph.math("ABSOLUTE", graph.math("SUBTRACT", graph.noise(vector, 1.0 / FRACTURE_SIZE, detail=5.0, roughness=0.62).outputs["Factor"], 0.5)))
    terrace = graph.noise(warped(graph, vector, FRACTURE_SIZE, 0.3 * FRACTURE_SIZE), 0.5 / FRACTURE_SIZE, detail=2.0).outputs["Factor"]
    steps = graph.math("DIVIDE", graph.math("FLOOR", graph.math("MULTIPLY", terrace, FRACTURE_STEPS)), FRACTURE_STEPS)
    relief = graph.math("MULTIPLY", graph.math("ADD", graph.math("SUBTRACT", ridged, 0.3), graph.math("SUBTRACT", steps, 0.5)), 2.0 * table["relief_share"]["fracture"])
    if table["conchoidal"] > 0.0:
        distance = graph.vector_math("LENGTH", warped(graph, vector, 0.05, 0.01))
        rings = graph.math("SINE", graph.math("MULTIPLY", distance, 6.2832 / CONCHOIDAL_RINGS))
        relief = graph.math("MULTIPLY_ADD", rings, table["conchoidal"] * 10.0, relief)
    return relief


def rock(graph, p):
    name = p["lithology"]
    table = rock_lithology.lithology(name)
    vector = shifted_vector(graph, p)
    if name == "granite":
        color, grain_relief = granite(graph, vector, table)
    elif name == "sandstone":
        color, grain_relief = sandstone(graph, vector, table)
    else:
        color, grain_relief = fine_grained(graph, vector, table, table.get("speck_color", [value * 0.85 for value in table["color"]]))
    tint = mottle(graph, vector)
    color = graph.mix(1.0, color, graph.node("ShaderNodeCombineXYZ", {"X": tint, "Y": tint, "Z": tint}).outputs[0], blend="MULTIPLY")
    crack = cracks(graph, vector, table)
    surface = graph.math("SUBTRACT", graph.noise(vector, 1.0 / SURFACE_SIZE, detail=5.0, roughness=0.62).outputs["Factor"], 0.5)
    height = graph.math("MULTIPLY_ADD", grain_relief, table["relief_share"]["grain"] * 2.0, graph.math("MULTIPLY", surface, 4.0 * table["relief_share"]["surface"]))
    height = graph.math("ADD", height, pits(graph, vector, table))
    height = graph.math("SUBTRACT", height, graph.math("MULTIPLY", crack, table["relief_share"]["cracks"] * 2.0))
    if p["fresh"]:
        height = graph.math("ADD", height, fracture_relief(graph, vector, table))
    color = graph.mix(graph.math("MULTIPLY", crack, 0.7), color, [value * 0.25 for value in rock_lithology.mean_color(name)])
    low, high = table["roughness"]
    roughness = graph.map_range(tint, 1.0 - MOTTLE_SPREAD, 1.0 + MOTTLE_SPREAD, high, low)
    layers = rock_weathering.weather(graph, p, vector, table, {"color": color, "roughness": roughness, "height": height, "crack": crack})
    return rock_relief.finish(graph, p, layers)


def rock_schema():
    """The stone preset's natural rock options; lithology none keeps the plain stone."""
    def amount(description, default):
        return number(description, 0.0, FRACTION, default)

    return {
        "lithology": string("Natural rock instead of plain stone: granite (feldspar, quartz and mica grains of about 4 mm), sandstone (beds, colour bands, fine grain), limestone (pale, solution pits) or basalt (dark, fine, vesicular). Its relief (bump: millimetres per unit) displaces the surface near the camera in render_final; dry rock is matte; color, cells, cracks and veins are not used. none: the plain stone.", ["none", *rock_lithology.LITHOLOGIES], "none"),
        "fresh": boolean("With lithology: a fresh fracture face, with rough break relief and no rind, lichen or moss.", False),
        "rind": amount("With lithology: how far the weathering rind has turned the surface to its weathered colour.", 0.6),
        "lichen": amount("With lithology: share of a fully exposed, lit top that lichen covers; less on steep faces, none underneath, on fresh faces or under water.", 0.25),
        "moss": amount("With lithology: how much moss grows in cracks, hollows and on shaded or damp tops.", 0.15),
    }
