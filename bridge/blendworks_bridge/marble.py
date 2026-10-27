from .procedural import preset_vector
from .schema import color, number, obj

VEIN_DIRECTIONS = ((0.82, 0.46, 0.34), (-0.35, 0.9, 0.27), (0.12, -0.5, 0.86))
VEIN_FREQUENCIES = (0.9, 1.9, 3.7)
VEIN_STRENGTHS = (1.0, 0.7, 0.42)
VEIN_WIDTH_SHARES = (1.0, 0.6, 0.35)
WARP_SCALE = 0.55
FADE_SCALE = 0.7
DEFAULT_VEIN_COLOR = [0.07, 0.068, 0.065]
HALO_REACH = 5.0
HALO_STRENGTH = 0.2


def veins_schema():
    schema = obj(
        {
            "color": color("Vein colour, linear RGB.", DEFAULT_VEIN_COLOR, False),
            "width": number("Vein width: 0 is hair-thin, 1 is broad bands.", 0.0, 1.0, 0.14),
            "turbulence": number("How far the veins wander: 0 gives straight parallel bands.", 0.0, 1.0, 0.5),
            "strength": number("How dark the veins get, 0 to 1.", 0.0, 1.0, 1.0),
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


def marble(graph, p):
    vector = preset_vector(graph, p)
    surface, grain = clouds(graph, vector, p["color"], p["secondary_color"])
    params = {"width": p["vein_width"], "turbulence": p["turbulence"], "strength": 1.0}
    mask = vein_mask(graph, vector, params)
    low = max(0.0, p["roughness"] - 0.07)
    return {
        "base_color": graph.mix(mask, surface, p["vein_color"]),
        "roughness": graph.map_range(graph.math("ADD", graph.math("MULTIPLY", grain, 0.5), graph.math("MULTIPLY", mask, 0.5)), 0.0, 1.0, low, min(1.0, p["roughness"] + 0.18)),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", grain, 0.35, graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", mask, 0.4))),
    }
