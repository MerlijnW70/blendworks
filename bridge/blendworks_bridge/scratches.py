from .errors import bad_args
from .procedural import AXES, AXIS_VECTORS

DIRECTIONS = list(AXES) + [f"around_{axis}" for axis in AXES]
SCRATCH_DIRECTION_HELP = "Axis the scratches run along (x, y, z), or around_x, around_y, around_z for rings around the axis; faces that look along the axis stay smooth."
ALONG = 0.4
ACROSS = 25.0
FADE_START = 0.55
FADE_END = 0.85


def parse_direction(direction):
    around = direction.startswith("around_")
    return direction[len("around_"):] if around else direction, around


def check_direction(direction, coordinates):
    axis, _ = parse_direction(direction)
    if coordinates == "uv" and axis == "z":
        raise bad_args("scratch_direction with z needs object coordinates; uv coordinates have no z axis")


def line_vector(graph, vector, direction):
    axis, around = parse_direction(direction)
    slow, fast = (ACROSS, ALONG) if around else (ALONG, ACROSS)
    factors = tuple(slow if value else fast for value in AXIS_VECTORS[axis])
    return graph.vector_math("MULTIPLY", vector, factors)


def facing_fade(graph, direction):
    axis, _ = parse_direction(direction)
    normal = graph.node("ShaderNodeTexCoord").outputs["Normal"]
    along = graph.math("ABSOLUTE", graph.vector_math("DOT_PRODUCT", normal, AXIS_VECTORS[axis]))
    return graph.map_range(along, FADE_START, FADE_END, 1.0, 0.0)


def scratch_lines(graph, vector, params, thickness, frequency=4.0):
    direction = params["scratch_direction"]
    check_direction(direction, params["coordinates"])
    lines = graph.noise(line_vector(graph, vector, direction), frequency * params["scratch_scale"], detail=1.0)
    centred = graph.math("ABSOLUTE", graph.math("SUBTRACT", lines.outputs["Factor"], 0.5))
    mask = graph.map_range(centred, 0.0, thickness, 1.0, 0.0)
    if params["coordinates"] == "object":
        mask = graph.math("MULTIPLY", mask, facing_fade(graph, direction))
    return mask
