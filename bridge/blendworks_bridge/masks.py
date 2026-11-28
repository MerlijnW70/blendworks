"""Geometric masks for procedural materials (window, axis and height masks)."""

from .errors import bad_args
from .limits import FRACTION, HALF_TURN, MAX_RELIEF, QUARTER_TURN
from .schema import array, number, string

GEOMETRIC = ("slope", "height", "up_facing", "attribute")
MASK_PARAMS = {
    "noise": (),
    "edges": (),
    "cavity": (),
    "vertex_color": (),
    "slope": ("angle_min", "angle_max", "angle_edge"),
    "height": ("z_min", "z_max", "z_edge"),
    "up_facing": ("strength",),
    "attribute": ("attribute", "value_min", "value_max"),
}
DEFAULT_ANGLE_EDGE = 5.0
DEFAULT_Z_EDGE = 0.5
MINIMUM_EDGE = 1e-4
MASK_HELP = "noise: patches; edges: worn convex edges; cavity: crevices; vertex_color: a painted colour attribute; slope: surface angle from horizontal in world space; height: world z in metres; up_facing: surfaces that face up; attribute: a named float attribute such as slope, height or curvature."


def geometric_schema():
    return {
        "with_masks": array(string("Mask kind.", list(MASK_PARAMS)), "More masks to combine with mask, each read with the settings given here.", 1, len(MASK_PARAMS) - 1),
        "combine": string("all multiplies the masks (moss on up-facing slopes in noise patches); any takes the largest.", ["all", "any"], "all"),
        "angle_min": number("slope: surfaces steeper than this many degrees from horizontal (0 flat, 90 vertical, up to 180 facing down) are covered, in world space.", 0.0, HALF_TURN),
        "angle_max": number("slope: surfaces flatter than this many degrees are covered; give angle_min, angle_max or both.", 0.0, HALF_TURN),
        "angle_edge": number(f"slope: width in degrees of the soft edge inside the limits (default {DEFAULT_ANGLE_EDGE}).", 0.0, QUARTER_TURN),
        "z_min": number("height: world z in metres above which the mask is 1, beyond the soft edge; below it 0."),
        "z_max": number("height: world z in metres below which the mask is 1, beyond the soft edge; give z_min, z_max or both."),
        "z_edge": number(f"height: width in metres of the soft edge inside the limits (default {DEFAULT_Z_EDGE}).", 0.0, MAX_RELIEF),
        "strength": number("up_facing: how far down the slopes the mask creeps, 0 only on faces looking straight up, 1 down to vertical walls (default 0.5).", 0.0, FRACTION),
        "attribute": string("attribute: name of a float point attribute, for example slope, height or curvature from heightfield or noise_displace."),
        "value_min": number("attribute: value that maps to a mask of 0 (default 0)."),
        "value_max": number("attribute: value that maps to a mask of 1 (default 1)."),
    }


def mask_kinds(args):
    kinds = [args["mask"]]
    kinds += [kind for kind in args.get("with_masks", []) if kind not in kinds]
    return kinds


def check_geometric_args(args, kinds):
    for kind, names in MASK_PARAMS.items():
        for name in names:
            if name in args and kind not in kinds:
                raise bad_args(f"{name} belongs to the {kind} mask")
    if "slope" in kinds and "angle_min" not in args and "angle_max" not in args:
        raise bad_args("the slope mask needs angle_min, angle_max or both")
    if "height" in kinds and "z_min" not in args and "z_max" not in args:
        raise bad_args("the height mask needs z_min, z_max or both")
    if "attribute" in kinds and "attribute" not in args:
        raise bad_args("the attribute mask needs attribute, the name of a float attribute to read")
    if "attribute" in kinds and args.get("value_min", 0.0) == args.get("value_max", 1.0):
        raise bad_args("value_min and value_max must differ")
    for low, high in (("angle_min", "angle_max"), ("z_min", "z_max")):
        if low in args and high in args and args[low] >= args[high]:
            raise bad_args(f"{low} must be below {high}")


def window(graph, value, low, high, edge):
    edge = max(edge, MINIMUM_EDGE)
    result = None
    if low is not None:
        result = graph.map_range(value, low, low + edge, 0.0, 1.0, "SMOOTHSTEP")
    if high is not None:
        falling = graph.map_range(value, high - edge, high, 1.0, 0.0, "SMOOTHSTEP")
        result = falling if result is None else graph.math("MULTIPLY", result, falling)
    return result


def geometry_axis(graph, output, axis):
    split = graph.node("ShaderNodeSeparateXYZ", {"Vector": graph.node("ShaderNodeNewGeometry").outputs[output]})
    return split.outputs[axis]


def up_component(graph):
    return graph.map_range(geometry_axis(graph, "Normal", "Z"), -1.0, 1.0, -1.0, 1.0)


def geometric_mask(graph, args, kind):
    if kind == "slope":
        degrees = graph.math("DEGREES", graph.math("ARCCOSINE", up_component(graph)))
        return window(graph, degrees, args.get("angle_min"), args.get("angle_max"), args.get("angle_edge", DEFAULT_ANGLE_EDGE))
    if kind == "height":
        return window(graph, geometry_axis(graph, "Position", "Z"), args.get("z_min"), args.get("z_max"), args.get("z_edge", DEFAULT_Z_EDGE))
    if kind == "up_facing":
        reach = max(args.get("strength", 0.5), MINIMUM_EDGE)
        return graph.map_range(up_component(graph), 1.0 - reach, 1.0, 0.0, 1.0, "SMOOTHSTEP")
    value = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=args["attribute"]).outputs["Fac"]
    return graph.map_range(value, args.get("value_min", 0.0), args.get("value_max", 1.0))


def combined(graph, values, how):
    result = values[0]
    for value in values[1:]:
        result = graph.math("MULTIPLY" if how == "all" else "MAXIMUM", result, value)
    return result
