"""Marble material: finish and vein layers with capillaries and clouds."""

from .procedural import preset_vector
from .limits import FRACTION
from .schema import color, number, obj, string

VEIN_DIRECTIONS = ((0.82, 0.46, 0.34), (-0.35, 0.9, 0.27), (0.12, -0.5, 0.86))
VEIN_FREQUENCIES = (0.9, 1.9, 3.7)
VEIN_STRENGTHS = (1.0, 0.7, 0.42)
VEIN_WIDTH_SHARES = (1.0, 0.6, 0.35)
WARP_SCALE = 0.55
FADE_SCALE = 0.7
DEFAULT_VEIN_COLOR = [0.07, 0.068, 0.065]
MARBLE_VEIN_COLOR = [0.16, 0.165, 0.175]
HALO_REACH = 5.0
HALO_STRENGTH = 0.2
FLOW_DIRECTION = (0.6, 0.48, 0.64)
FLOW_WARP_SCALE = 1.2
FLOW_WARP_REACH = 0.9
MAIN_SCALE = 6.0
MAIN_WIDTH = 0.008
MAIN_WIDTH_RANGE = 0.04
STRAND_SCALE = 9.0
SMOKE_WIDTH = 0.07
SMOKE_STRENGTH = 0.3
BRANCH_RATIO = 2.2
BRANCH_REACH = 0.16
DRIFT_RATIO = 0.55
SECOND_RATIO = 1.45
SECOND_STRENGTH = 0.6
DRIFT_WIDTH = 0.16
DRIFT_STRENGTH = 0.42
FINISHES = {"polished": 0.0, "honed": 0.2, "rough": 1.0}
FINISH_HELP = "Surface finish: polished is optically flat, so the veins and grain give no relief at all; honed keeps 20% of the bump depth and rough all of it (bump millimetres at rough, 0.3 by default), so a honed or rough slab breaks up the highlights a little or a lot."


def finish_schema():
    return string(FINISH_HELP, list(FINISHES), "polished")


def veins_schema():
    schema = obj(
        {
            "color": color("Vein colour, linear RGB.", DEFAULT_VEIN_COLOR, False),
            "width": number("Vein width: 0 is hair-thin, 1 is broad bands.", 0.0, FRACTION, 0.14),
            "turbulence": number("How far the veins wander: 0 gives straight parallel bands.", 0.0, FRACTION, 0.5),
            "strength": number("How dark the veins get, 0 to 1.", 0.0, FRACTION, 1.0),
        }
    )
    schema["description"] = "Banded, ridged veins with domain warping, laid over the stone."
    return schema


def warped(graph, vector, turbulence, salt):
    field = graph.noise(graph.vector_math("ADD", vector, (salt, salt * 0.7, salt * 1.3)), WARP_SCALE, detail=5.0, roughness=0.55)
    offset = graph.vector_math("SUBTRACT", field.outputs["Color"], 0.5)
    return graph.vector_math("ADD", vector, graph.vector_math("SCALE", offset, scale=3.0 * turbulence))


def vein_layer(graph, vector, params, index):
    direction = VEIN_DIRECTIONS[index]
    across = graph.vector_math("DOT_PRODUCT", warped(graph, vector, params["turbulence"], 11.0 * (index + 1)), direction)
    phase = graph.math("MULTIPLY", across, VEIN_FREQUENCIES[index])
    distance = graph.math("PINGPONG", phase, 0.5)
    fade = graph.map_range(graph.noise(graph.vector_math("ADD", vector, (5.0 * index, 9.0, 2.0 * index)), FADE_SCALE * (index + 1), detail=3.0).outputs["Factor"], 0.28, 0.58)
    half_width = 0.012 + 0.2 * params["width"] * VEIN_WIDTH_SHARES[index]
    line = graph.map_range(distance, 0.0, half_width, 1.0, 0.0, "SMOOTHSTEP")
    halo = graph.map_range(distance, 0.0, half_width * HALO_REACH, HALO_STRENGTH, 0.0, "SMOOTHSTEP")
    return graph.math("MULTIPLY", graph.math("ADD", line, halo), graph.math("MULTIPLY", fade, VEIN_STRENGTHS[index]))


def capillaries(graph, vector, params):
    field = graph.noise(warped(graph, vector, params["turbulence"], 41.0), 5.5, detail=6.0, roughness=0.6).outputs["Factor"]
    distance = graph.math("ABSOLUTE", graph.math("SUBTRACT", field, 0.5))
    line = graph.map_range(distance, 0.0, 0.006 + 0.02 * params["width"], 1.0, 0.0, "SMOOTHSTEP")
    fade = graph.map_range(graph.noise(vector, 1.3, detail=2.0).outputs["Factor"], 0.4, 0.75)
    return graph.math("MULTIPLY", line, graph.math("MULTIPLY", fade, 0.45))


def vein_mask(graph, vector, params):
    total = vein_layer(graph, vector, params, 0)
    for index in (1, 2):
        total = graph.math("ADD", total, vein_layer(graph, vector, params, index))
    total = graph.math("ADD", total, capillaries(graph, vector, params))
    return graph.math("MULTIPLY", graph.math("MINIMUM", total, 1.0), params["strength"])


def clouds(graph, vector, base, tint):
    soft = graph.map_range(graph.noise(vector, 1.1, detail=7.0, roughness=0.6).outputs["Factor"], 0.32, 0.68)
    grain = graph.map_range(graph.noise(vector, 22.0, detail=5.0, roughness=0.65).outputs["Factor"], 0.35, 0.65)
    mottled = graph.math("MULTIPLY_ADD", soft, 0.75, graph.math("MULTIPLY", grain, 0.25))
    return graph.mix(mottled, base, tint), grain


def flowing(graph, vector, turbulence):
    field = graph.noise(vector, FLOW_WARP_SCALE, detail=4.0, roughness=0.55).outputs["Color"]
    warped_vector = graph.vector_math("ADD", vector, graph.vector_math("SCALE", graph.vector_math("SUBTRACT", field, 0.5), scale=FLOW_WARP_REACH * (0.15 + turbulence)))
    along = graph.vector_math("DOT_PRODUCT", warped_vector, FLOW_DIRECTION)
    return graph.vector_math("SUBTRACT", warped_vector, graph.vector_math("SCALE", FLOW_DIRECTION, along))


def distance_to_isoline(graph, vector, scale, detail):
    field = graph.noise(vector, scale, detail=detail, roughness=0.5).outputs["Factor"]
    return graph.math("ABSOLUTE", graph.math("SUBTRACT", field, 0.5))


def soft_line(graph, distance, width, reach, peak, halo):
    core = graph.map_range(distance, 0.0, width, peak, 0.0, "SMOOTHSTEP")
    glow = graph.map_range(distance, 0.0, graph.math("MULTIPLY", width, reach), halo, 0.0, "SMOOTHSTEP")
    return graph.math("ADD", core, glow, clamp=True)


def varying(graph, vector, scale, low, high, salt):
    field = graph.noise(graph.vector_math("ADD", vector, (salt, salt * 0.37, salt * 0.71)), scale, detail=3.0, roughness=0.6).outputs["Factor"]
    return graph.map_range(field, 0.3, 0.7, low, high)


def layered_veins(graph, vector, p):
    flow = flowing(graph, vector, p["turbulence"])
    width = MAIN_WIDTH + MAIN_WIDTH_RANGE * p["vein_width"]
    reach = 2.0 + 6.0 * p["vein_softness"]
    main_distance = distance_to_isoline(graph, flow, MAIN_SCALE, 4.0)
    main_width = graph.math("MULTIPLY", varying(graph, vector, STRAND_SCALE, 0.35, 1.3, 13.0), width)
    strength = varying(graph, vector, STRAND_SCALE * 2.0, 0.25, 0.95, 29.0)
    main = graph.math("MULTIPLY", soft_line(graph, main_distance, main_width, reach, 1.0, 0.45), strength)
    smoke = graph.map_range(main_distance, 0.0, SMOKE_WIDTH * (0.2 + 1.6 * p["vein_softness"]), SMOKE_STRENGTH * (0.3 + 1.4 * p["vein_softness"]), 0.0, "SMOOTHSTEP")
    branch_distance = distance_to_isoline(graph, graph.vector_math("ADD", graph.vector_math("SCALE", flow, scale=BRANCH_RATIO), (3.1, 7.7, 1.9)), MAIN_SCALE, 5.0)
    nearby = graph.map_range(main_distance, 0.0, BRANCH_REACH, 1.0, 0.0, "SMOOTHSTEP")
    branch_width = graph.math("MULTIPLY", varying(graph, vector, STRAND_SCALE * 3.0, 0.3, 1.0, 47.0), width * 0.5)
    branches = graph.math("MULTIPLY", soft_line(graph, branch_distance, branch_width, reach, 0.55, 0.2), graph.math("MULTIPLY_ADD", nearby, p["branching"], 0.1))
    drift_distance = distance_to_isoline(graph, graph.vector_math("SCALE", flow, scale=DRIFT_RATIO), MAIN_SCALE, 3.0)
    drift = graph.map_range(drift_distance, 0.0, DRIFT_WIDTH, DRIFT_STRENGTH * min(1.2, 0.2 + 1.6 * p["vein_softness"]), 0.0, "SMOOTHSTEP")
    second_distance = distance_to_isoline(graph, graph.vector_math("ADD", graph.vector_math("SCALE", flow, scale=SECOND_RATIO), (11.3, 2.9, 5.3)), MAIN_SCALE, 4.0)
    second = graph.math("MULTIPLY", soft_line(graph, second_distance, graph.math("MULTIPLY", main_width, 0.7), reach, SECOND_STRENGTH, 0.3), strength)
    veins = graph.math("MAXIMUM", graph.math("MAXIMUM", main, second), branches)
    return graph.math("MAXIMUM", veins, graph.math("MAXIMUM", drift, smoke))


def relief(graph, p, grain, mask):
    share = FINISHES[p["finish"]]
    if share == 0.0:
        return 0.0
    height = graph.math("MULTIPLY_ADD", grain, 0.35, graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", mask, 0.4)))
    return graph.math("MULTIPLY", height, share)


def marble(graph, p):
    vector = preset_vector(graph, p)
    surface, grain = clouds(graph, vector, p["color"], p["secondary_color"])
    mask = layered_veins(graph, vector, p)
    low = max(0.0, p["roughness"] - 0.07)
    return {
        "base_color": graph.mix(mask, surface, p["vein_color"]),
        "roughness": graph.map_range(graph.math("ADD", graph.math("MULTIPLY", grain, 0.5), graph.math("MULTIPLY", mask, 0.5)), 0.0, 1.0, low, min(1.0, p["roughness"] + 0.18)),
        "metallic": 0.0,
        "height": relief(graph, p, grain, mask),
    }
