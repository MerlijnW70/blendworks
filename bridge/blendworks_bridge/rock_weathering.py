"""Weathering of a rock surface: a rind, lichen, moss, worn edges and the marks of water; docs/research/rock-realism.md.

- Rind: exposed rock weathers to a skin of its own colour (oxidised iron in granite and basalt, a paler crust on limestone);
  fresh fracture faces have none, and worn edges lose it first.
- Lichen: colonies are founded, grow outward at a steady rate and merge (lichenometry, Armstrong and Bradwell 2010): lobed
  rosettes of every size up to the oldest, grey, grey-green (raised, foliose), yellow-green map lichen with a dark margin,
  orange and black species mixed, clustered, on exposed, lit faces: the cover falls from the stated share on a fully exposed top to none on
  an underside, on fresh faces and under water.
- Moss: in cracks and hollows, where water stays, and on shaded or damp tops.
- Water: under the water line a film of algae (periphyton) that thickens with depth; just above it a dark stained band, the
  water mark; liquid_depth and liquid_wet are the point attributes liquid_body and shore wetting write.
"""
from .procedural import seed_offset

LICHEN_LAYERS = (0.12, 0.05, 0.02)
LICHEN_REACH = 0.5
LICHEN_LOBES = 0.35
LICHEN_CLUSTER = 0.6
SPECIES = (
    {"color": (0.27, 0.28, 0.25), "share": 0.38, "relief": 0.2, "rim": 1.15},
    {"color": (0.19, 0.22, 0.17), "share": 0.26, "relief": 1.2, "rim": 1.25},
    {"color": (0.2, 0.23, 0.05), "share": 0.2, "relief": 0.2, "rim": 0.25},
    {"color": (0.26, 0.12, 0.025), "share": 0.05, "relief": 0.4, "rim": 1.2},
    {"color": (0.05, 0.05, 0.045), "share": 0.11, "relief": 0.15, "rim": 1.0},
)
MOSS = (0.03, 0.075, 0.012)
MOSS_TIPS = (0.11, 0.19, 0.03)
ALGAE = (0.045, 0.055, 0.018)
WATER_MARK = 0.05
ALGAE_DEPTH = 0.06
SHADE_REACH = 0.4
EDGE_POINTINESS = (0.5, 0.56)
RIND_PATCH = 0.12
GRIME_REACH = 0.05
EXPOSED_NORMAL = (-0.15, 0.75)


def attribute(graph, name):
    return graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name).outputs["Fac"]


def facing_up(graph):
    normal = graph.node("ShaderNodeNewGeometry").outputs["Normal"]
    up = graph.node("ShaderNodeSeparateXYZ", {"Vector": normal}).outputs["Z"]
    return graph.map_range(up, EXPOSED_NORMAL[0], EXPOSED_NORMAL[1], 0.0, 1.0, "SMOOTHSTEP")


def edges(graph):
    pointiness = graph.node("ShaderNodeNewGeometry").outputs["Pointiness"]
    return graph.map_range(pointiness, EDGE_POINTINESS[0], EDGE_POINTINESS[1])


def shade(graph, reach=SHADE_REACH, own=False):
    node = graph.node("ShaderNodeAmbientOcclusion", {"Distance": reach}, inside=False, only_local=own, samples=4)
    return graph.math("SUBTRACT", 1.0, node.outputs["AO"])


def offset(graph, vector, salt):
    return graph.vector_math("ADD", vector, seed_offset(salt))


def species_of(graph, draw):
    color, relief, rim = graph.rgb(SPECIES[0]["color"]), graph.value(SPECIES[0]["relief"]), graph.value(SPECIES[0]["rim"])
    bound = 0.0
    for species, previous in zip(SPECIES[1:], SPECIES[:-1]):
        bound += previous["share"]
        later = graph.math("GREATER_THAN", draw, bound)
        color = graph.mix(later, color, species["color"])
        relief = graph.mix(later, relief, species["relief"], "FLOAT")
        rim = graph.mix(later, rim, species["rim"], "FLOAT")
    return color, relief, rim


def colonies(graph, vector, cell, chance, salt):
    """One generation of colonies on a Voronoi lattice of the given cell: a colony founded in a cell with the given chance,
    grown for an age drawn uniformly (crustose thalli widen at a steady rate once established, Armstrong and Bradwell 2010,
    so radius is proportional to age and sizes spread evenly up to the oldest), out to LICHEN_REACH of the cell, its margin
    lobed by noise in the direction of growth. Returns the cover (1 inside), its relative radius and the cell's draws."""
    lobed = graph.noise(offset(graph, vector, salt), 1.0 / (0.25 * cell), detail=4.0, roughness=0.6).outputs["Color"]
    warp = graph.vector_math("MULTIPLY", graph.vector_math("SUBTRACT", lobed, (0.5, 0.5, 0.5)), (0.5 * cell,) * 3)
    cells = graph.voronoi(graph.vector_math("ADD", offset(graph, vector, salt + 1), warp), 1.0 / cell)
    draws = graph.node("ShaderNodeSeparateColor", {"Color": cells.outputs["Color"]}).outputs
    founded = graph.math("LESS_THAN", draws[0], chance)
    radius = graph.math("MULTIPLY", graph.math("MAXIMUM", draws[1], 0.08), LICHEN_REACH)
    margin = graph.noise(offset(graph, vector, salt + 2), 1.0 / (0.08 * cell), detail=3.0, roughness=0.6).outputs["Factor"]
    reach = graph.math("DIVIDE", cells.outputs["Distance"], graph.math("MULTIPLY", radius, graph.map_range(margin, 0.3, 0.7, 1.0 - LICHEN_LOBES, 1.0 + LICHEN_LOBES)))
    cover = graph.math("MULTIPLY", founded, graph.map_range(reach, 0.92, 1.0, 1.0, 0.0))
    return cover, reach, draws


def lichen_cover(graph, vector, exposure, coverage):
    """Lichen by growth: three generations of colonies of different cell sizes, founded more often where the surface is
    exposed and in clusters (spores settle where others grew), merging where they meet. A colony covers on average
    pi * LICHEN_REACH^2 / 3 of its cell (uniform ages), so the chance per cell that gives the stated coverage of a fully
    exposed top over the union of the generations follows: each covers 1 - (1 - coverage)^(1/3). The colour is the species of
    the colony on top, paler or darker towards its growing margin, mottled by its areoles."""
    per_layer = 1.0 - (1.0 - min(coverage, 0.95)) ** (1.0 / len(LICHEN_LAYERS))
    mean_area = 3.14159 * LICHEN_REACH * LICHEN_REACH / 3.0
    cluster = graph.map_range(graph.noise(offset(graph, vector, 37), 1.0 / 0.4, detail=2.0).outputs["Factor"], 0.3, 0.7, 1.0 - LICHEN_CLUSTER, 1.0 + LICHEN_CLUSTER)
    chance = graph.math("MULTIPLY", graph.math("MULTIPLY", exposure, cluster), min(1.0, per_layer / mean_area))
    cover, color, relief = graph.value(0.0), graph.rgb((0.0, 0.0, 0.0)), graph.value(0.0)
    for index, cell in enumerate(LICHEN_LAYERS):
        layer, reach, draws = colonies(graph, vector, cell, chance, 101 + 7 * index)
        tone, height, rim = species_of(graph, draws[2])
        edge = graph.map_range(reach, 0.6, 0.95)
        tone = graph.mix(edge, tone, graph.mix(1.0, tone, graph.node("ShaderNodeCombineXYZ", {"X": rim, "Y": rim, "Z": rim}).outputs[0], blend="MULTIPLY"))
        areoles = graph.voronoi(offset(graph, vector, 151 + index), 1.0 / 0.002, feature="DISTANCE_TO_EDGE").outputs["Distance"]
        tone = graph.mix(graph.map_range(areoles, 0.0, 0.06, 0.35, 0.0), tone, graph.mix(1.0, tone, (0.55, 0.55, 0.55), blend="MULTIPLY"))
        color = graph.mix(layer, color, tone)
        relief = graph.mix(layer, relief, height, "FLOAT")
        cover = graph.math("MAXIMUM", cover, layer)
    return cover, color, relief


def moss_cover(graph, vector, crack, cavity, damp, top, amount):
    widened = graph.map_range(crack, 0.0, 0.3)
    wet_place = graph.math("MAXIMUM", graph.math("MULTIPLY", widened, 0.9), cavity)
    shaded_top = graph.math("MULTIPLY", top, graph.math("MAXIMUM", damp, graph.map_range(cavity, 0.1, 0.5)))
    patches = graph.map_range(graph.noise(offset(graph, vector, 53), 4.0, detail=4.0, roughness=0.6).outputs["Factor"], 0.55 - 0.3 * amount, 0.65 - 0.3 * amount)
    mask = graph.math("MULTIPLY", graph.math("MAXIMUM", wet_place, shaded_top), patches)
    tufts = graph.noise(offset(graph, vector, 59), 1.0 / 0.004, detail=4.0, roughness=0.7).outputs["Factor"]
    color = graph.mix(graph.map_range(tufts, 0.4, 0.65), MOSS, MOSS_TIPS)
    return graph.math("MULTIPLY", mask, min(1.0, 2.0 * amount)), color, tufts


def water_marks(graph, vector):
    """Under the water line, algae; just above it, the water mark. Both need water: a point with no liquid attributes reads
    depth 0 and wetness 0 and gets neither."""
    depth = attribute(graph, "liquid_depth")
    wet = attribute(graph, "liquid_wet")
    present = graph.math("MAXIMUM", graph.math("GREATER_THAN", wet, 0.001), graph.math("GREATER_THAN", depth, 0.0005))
    blotch = graph.map_range(graph.noise(offset(graph, vector, 67), 8.0, detail=3.0).outputs["Factor"], 0.35, 0.65, 0.55, 1.0)
    algae = graph.math("MULTIPLY", graph.math("MULTIPLY", graph.map_range(depth, 0.0, ALGAE_DEPTH, 0.0, 1.0, "SMOOTHSTEP"), blotch), present)
    above = graph.math("MULTIPLY", depth, -1.0)
    mark = graph.math("MULTIPLY", graph.math("MULTIPLY", graph.map_range(above, -0.005, 0.0), graph.map_range(above, 0.6 * WATER_MARK, WATER_MARK, 1.0, 0.0)), present)
    return algae, mark, graph.math("MAXIMUM", graph.math("GREATER_THAN", depth, 0.0), graph.math("MULTIPLY", mark, 1.0)), wet


def weather(graph, p, vector, table, layers):
    color, roughness, height, crack = layers["color"], layers["roughness"], layers["height"], layers["crack"]
    fresh = 1.0 if p["fresh"] else 0.0
    worn = edges(graph)
    top = facing_up(graph)
    if not fresh:
        patina = graph.noise(offset(graph, vector, 71), 1.0 / RIND_PATCH, detail=5.0, roughness=0.6).outputs["Factor"]
        reach = graph.map_range(patina, 0.3, 0.7, 0.45, 1.0)
        rind = graph.math("MULTIPLY", graph.math("MULTIPLY", graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", worn, 0.6)), reach), p["rind"])
        stain = graph.mix(graph.map_range(patina, 0.25, 0.75), [value * 0.7 for value in table["rind"]], [value * 1.15 for value in table["rind"]])
        color = graph.mix(rind, color, graph.mix(0.7, color, stain))
        grime = graph.math("MULTIPLY", shade(graph, GRIME_REACH, True), 0.6)
        color = graph.mix(grime, color, graph.mix(1.0, color, (0.45, 0.42, 0.38), blend="MULTIPLY"))
        height = graph.math("MULTIPLY", height, graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", worn, 0.6)))
    algae, mark, wet_zone, damp = water_marks(graph, vector)
    dry = graph.math("SUBTRACT", 1.0, wet_zone)
    lichen = moss = graph.value(0.0)
    if not fresh and p["lichen"] > 0.0:
        exposure = graph.math("MULTIPLY", graph.math("MULTIPLY", top, dry), graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", worn, 0.7)))
        lichen, lichen_color, lichen_relief = lichen_cover(graph, vector, exposure, p["lichen"])
        color = graph.mix(lichen, color, lichen_color)
        height = graph.math("ADD", height, graph.math("MULTIPLY", lichen, lichen_relief))
        roughness = graph.mix(lichen, roughness, 0.92, "FLOAT")
    if not fresh and p["moss"] > 0.0:
        cavity = shade(graph)
        moss, moss_color, tufts = moss_cover(graph, vector, crack, cavity, damp, top, p["moss"])
        moss = graph.math("MULTIPLY", moss, dry)
        color = graph.mix(moss, color, moss_color)
        height = graph.math("ADD", height, graph.math("MULTIPLY", moss, graph.math("MULTIPLY_ADD", tufts, 1.5, 0.5)))
        roughness = graph.mix(moss, roughness, 0.95, "FLOAT")
    color = graph.mix(algae, color, ALGAE)
    color = graph.mix(graph.math("MULTIPLY", mark, 0.75), color, graph.mix(1.0, color, (0.5, 0.43, 0.36), blend="MULTIPLY"))
    roughness = graph.mix(algae, roughness, 0.55, "FLOAT")
    return {"color": color, "roughness": roughness, "height": height, "lichen": lichen, "moss": moss, "algae": algae, "mark": mark}
