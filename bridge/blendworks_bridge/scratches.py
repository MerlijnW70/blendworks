import math

from .errors import bad_args
from .procedural import AXES, AXIS_VECTORS, seed_offset
from .schema import vector3

AROUND_AXES = [f"around_{axis}" for axis in AXES]
DIRECTIONS = list(AXES) + AROUND_AXES + ["around", "u", "v"]
SCRATCH_DIRECTION_HELP = (
    "Which way the fine scratches run. x, y, z: straight along that axis, for flat stock (faces that look along the axis stay smooth). "
    "around_x, around_y, around_z and around (about scratch_axis): circles about the axis, concentric on its end faces and ringing its sides, "
    "as on a turned or polished ring, disc or lathe part; they follow the object's own geometry, so they ignore coordinates. "
    "u, v: along the UV map's u or v direction, whatever coordinates says; a lathe unwraps with u around the part and a sweep with v along its path."
)
SCRATCH_AXIS_HELP = "Axis in the object's local space that around scratches circle about, for direction around; the default is the Z axis, which lathe and ring shapes turn about."
DEFAULT_AXIS = [0.0, 0.0, 1.0]
ALONG = 0.4
ACROSS = 25.0
FADE_START = 0.55
FADE_END = 0.85


def scratch_axis_schema():
    return vector3(SCRATCH_AXIS_HELP, DEFAULT_AXIS)


def is_around(direction):
    return direction in AROUND_AXES or direction == "around"


def check_direction(direction, coordinates):
    if coordinates == "uv" and direction == "z":
        raise bad_args("scratch_direction with z needs object coordinates; uv coordinates have no z axis")


def around_axis(params):
    direction = params["scratch_direction"]
    if direction in AROUND_AXES:
        return AXIS_VECTORS[direction[len("around_"):]]
    given = params.get("scratch_axis", DEFAULT_AXIS)
    size = math.sqrt(sum(value * value for value in given))
    if size < 1e-6:
        raise bad_args("scratch_axis must not be the zero vector")
    return tuple(value / size for value in given)


def line_vector(graph, vector, direction):
    slow, fast = (ALONG, ACROSS)
    factors = tuple(slow if value else fast for value in AXIS_VECTORS[direction])
    return graph.vector_math("MULTIPLY", vector, factors)


def mapped(graph, source, params, factors):
    mapping = graph.node("ShaderNodeMapping", vector_type="POINT")
    graph.set(mapping.inputs["Vector"], source)
    mapping.inputs["Location"].default_value = seed_offset(params["seed"] * 7919)
    mapping.inputs["Scale"].default_value = tuple(params["scale"] * factor for factor in factors)
    return mapping.outputs["Vector"]


def around_vector(graph, params):
    axis = around_axis(params)
    position = graph.node("ShaderNodeTexCoord").outputs["Object"]
    height = graph.vector_math("DOT_PRODUCT", position, axis)
    radial = graph.vector_math("LENGTH", graph.vector_math("SUBTRACT", position, graph.vector_math("SCALE", axis, scale=height)))
    plane = graph.node("ShaderNodeCombineXYZ", {"X": radial, "Y": height}).outputs["Vector"]
    return mapped(graph, plane, params, (ACROSS, ACROSS, 0.0))


def uv_vector(graph, params):
    uv = graph.node("ShaderNodeTexCoord").outputs["UV"]
    along_u = params["scratch_direction"] == "u"
    return mapped(graph, uv, params, (ALONG, ACROSS, 0.0) if along_u else (ACROSS, ALONG, 0.0))


def facing_fade(graph, direction):
    normal = graph.node("ShaderNodeTexCoord").outputs["Normal"]
    along = graph.math("ABSOLUTE", graph.vector_math("DOT_PRODUCT", normal, AXIS_VECTORS[direction]))
    return graph.map_range(along, FADE_START, FADE_END, 1.0, 0.0)


def scratch_lines(graph, vector, params, thickness, frequency=4.0):
    direction = params["scratch_direction"]
    check_direction(direction, params["coordinates"])
    if is_around(direction):
        source = around_vector(graph, params)
    elif direction in ("u", "v"):
        source = uv_vector(graph, params)
    else:
        source = line_vector(graph, vector, direction)
    lines = graph.noise(source, frequency * params["scratch_scale"], detail=1.0)
    centred = graph.math("ABSOLUTE", graph.math("SUBTRACT", lines.outputs["Factor"], 0.5))
    mask = graph.map_range(centred, 0.0, thickness, 1.0, 0.0)
    if direction in AXES and params["coordinates"] == "object":
        mask = graph.math("MULTIPLY", mask, facing_fade(graph, direction))
    return mask
