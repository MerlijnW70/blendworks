from .occlusion import occlusion_mask
from .procedural import preset_vector
from .scratches import DIRECTIONS, SCRATCH_DIRECTION_HELP, scratch_lines
from .schema import color, number, string

DEFAULT_BRASS = [0.62, 0.36, 0.09]
DEFAULT_PATINA = [0.075, 0.08, 0.04]
RECESS_REACH = 0.012
EDGE_REACH = 0.012
STAIN_SHARE = 0.3
EDGE_GAIN = 2.0
EDGE_BRIGHTNESS = 1.45
PATINA_START = 0.85
PATINA_REACH = 1.0
PATINA_WIDTH = 0.25
FINE_SCRATCH_WIDTH = 0.018
FINE_SCRATCH_FREQUENCY = 8.0


def brass_schema():
    return {
        "color": color("Polished brass colour, linear RGB.", DEFAULT_BRASS, False),
        "patina_color": color("Colour of the patina in the recesses, linear RGB.", DEFAULT_PATINA, False),
        "patina": number("Patina amount, 0 to 1: how far the dark tarnish spreads out of the recesses.", 0.0, 1.0, 0.35),
        "polish": number("Polish, 0 to 1: 1 is a smooth mirror finish, 0 a dull, scratched one.", 0.0, 1.0, 0.6),
        "scratch_scale": number("Scratch density multiplier.", 0.1, 20.0, 1.0),
        "scratch_direction": string(SCRATCH_DIRECTION_HELP, DIRECTIONS, "x"),
    }


def lighter(values, factor):
    return [min(1.0, value * factor) for value in values]


def brass(graph, p):
    vector = preset_vector(graph, p)
    polish, patina = p["polish"], p["patina"]
    lines = scratch_lines(graph, vector, p, FINE_SCRATCH_WIDTH, FINE_SCRATCH_FREQUENCY)
    sparse = graph.map_range(graph.noise(vector, 3.0, detail=3.0).outputs["Factor"], 0.35, 0.65)
    scratches = graph.math("MULTIPLY", graph.math("MULTIPLY", lines, sparse), 1.0 - 0.85 * polish)
    stains = graph.map_range(graph.noise(vector, 2.5, detail=6.0, roughness=0.6).outputs["Factor"], 0.3, 0.7)
    edges = graph.math("MULTIPLY", occlusion_mask(graph, EDGE_REACH, True), EDGE_GAIN, clamp=True)
    recess = graph.math("MULTIPLY_ADD", stains, STAIN_SHARE, occlusion_mask(graph, RECESS_REACH, False))
    middle = PATINA_START - PATINA_REACH * patina
    spread = graph.map_range(recess, middle - PATINA_WIDTH, middle + PATINA_WIDTH)
    tarnish = graph.math("MULTIPLY", graph.math("MULTIPLY", spread, graph.math("SUBTRACT", 1.0, edges)), min(1.0, patina * 10.0))
    tone = graph.mix(graph.map_range(stains, 0.0, 1.0, 0.0, 0.12), p["color"], lighter(p["color"], 1.12))
    bright = graph.mix(graph.math("MAXIMUM", scratches, edges), tone, lighter(p["color"], EDGE_BRIGHTNESS))
    base = 0.06 + 0.4 * (1.0 - polish)
    return {
        "base_color": graph.mix(tarnish, bright, p["patina_color"]),
        "roughness": graph.math("ADD", graph.math("MULTIPLY_ADD", tarnish, 0.4, base), graph.math("MULTIPLY", scratches, 0.12), clamp=True),
        "metallic": graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", tarnish, 0.5)),
        "height": graph.math("SUBTRACT", 1.0, scratches),
    }
