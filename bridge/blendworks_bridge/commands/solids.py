import math

from ..builder import SHAPE_FIELDS, finish_shape
from ..errors import bad_args
from ..extrusion import extrusion_data
from ..gears import gear_outline, sprocket_outline
from ..kit_limits import MAX_HOLES, MAX_OUTLINE_POINTS, MAX_TEETH
from ..outlines import circle_points
from ..registry import command
from ..schema import array, boolean, integer, length, number, points2, string
from ..util import require_free_name

THICKNESS = length("Extrusion height along Z in metres.", maximum=1000.0)
EXTRUSION_FIELDS = {
    "chamfer": number("Width in metres of a bevel on the rims of both faces; 0 for none.", 0.0, 1000.0, 0.0),
    "bevel_segments": integer("Segments of the rim bevel: 1 is a flat chamfer, more round it.", 1, 16, 1),
    "centered": boolean("Centre the thickness on z = 0 instead of extruding from z = 0 up.", False),
}


def shape_fields(name, extra):
    fields = dict(SHAPE_FIELDS)
    fields["name"] = string("Object name; must be unused.", default=name)
    fields.update(extra)
    return fields


def bore_loop(diameter, outline_radius, segments):
    if diameter <= 0:
        return []
    if diameter / 2.0 >= outline_radius * 0.9:
        raise bad_args(f"bore {diameter} leaves no wall; it must be below {1.8 * outline_radius:.6f} here")
    return [circle_points(diameter / 2.0, segments)]


def rotate_points(points, degrees):
    if degrees == 0:
        return points
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return [(x * cosine - y * sine, x * sine + y * cosine) for x, y in points]


@command(
    "extrude_outline",
    "Turn a 2D outline with optional holes into a solid plate of a given thickness with optional rim bevel and caps; for plates, brackets and signs.",
    shape_fields(
        "Plate",
        {
            "outline": points2("Outline [x, y] points in metres, any winding, in the XY plane.", 3, MAX_OUTLINE_POINTS),
            "holes": array(points2("One hole outline.", 3, MAX_OUTLINE_POINTS), "Hole outlines inside the outline, not touching it or each other.", 0, MAX_HOLES, []),
            "depth": THICKNESS,
            "caps": boolean("Close the top and bottom with flat faces; false leaves an open wall.", True),
            **EXTRUSION_FIELDS,
        },
    ),
    ["outline", "depth"],
    family="shapes",
    intents=("solid plate from a 2D outline with holes", "bracket, sign or cookie cutter shape"),
    nearest=(("extrude", "to pull faces of an existing mesh"),),
)
def extrude_outline(ctx, args):
    require_free_name(args["name"])
    data = extrusion_data(args["outline"], args["holes"], args["depth"], args["chamfer"], args["bevel_segments"], args["centered"], args["caps"])
    result = finish_shape(ctx, data, args)
    result["holes"] = len(args["holes"])
    return result


@command(
    "gear",
    "Make a spur gear with involute or simplified straight-flank teeth from teeth and module (or circular pitch), with optional bore; built on extrude_outline.",
    shape_fields(
        "Gear",
        {
            "teeth": integer("Number of teeth, at least 6.", 6, MAX_TEETH),
            "module": length("Module in metres: pitch diameter divided by teeth.", maximum=10.0),
            "pitch": length("Circular pitch in metres (module times pi) instead of module.", maximum=30.0),
            "pressure_angle": number("Pressure angle in degrees.", 5.0, 35.0, 20.0),
            "tooth_profile": string("involute is the standard curved flank; simple has straight flanks.", ["involute", "simple"], "involute"),
            "tooth_samples": integer("Points along each involute flank.", 1, 24, 6),
            "bore": number("Diameter in metres of the central hole; 0 for none.", 0.0, 1000.0, 0.0),
            "phase": number("Rotate the teeth around Z by this many degrees.", -360.0, 360.0, 0.0),
            "thickness": THICKNESS,
            **EXTRUSION_FIELDS,
        },
    ),
    ["teeth", "thickness"],
    family="shapes",
    intents=("spur gear with teeth and a bore", "cog wheel from module or pitch"),
    nearest=(("sprocket", "for a chain wheel"),),
)
def gear(ctx, args):
    require_free_name(args["name"])
    if ("module" in args) == ("pitch" in args):
        raise bad_args("give the tooth size as exactly one of module or pitch")
    module = args["module"] if "module" in args else args["pitch"] / math.pi
    outline, sizes = gear_outline(args["teeth"], module, args["pressure_angle"], args["tooth_profile"], args["tooth_samples"])
    holes = bore_loop(args["bore"], sizes["root_radius"], 48)
    data = extrusion_data(rotate_points(outline, args["phase"]), holes, args["thickness"], args["chamfer"], args["bevel_segments"], args["centered"])
    result = finish_shape(ctx, data, args)
    result.update(
        {
            "teeth": args["teeth"],
            "module": module,
            "pitch_diameter": 2 * sizes["pitch_radius"],
            "outer_diameter": 2 * sizes["tip_radius"],
            "root_diameter": 2 * sizes["root_radius"],
        }
    )
    return result


@command(
    "sprocket",
    "Make a roller-chain sprocket with seated roller pockets from teeth, chain pitch and roller diameter, with optional bore; pair it with roller_chain.",
    shape_fields(
        "Sprocket",
        {
            "teeth": integer("Number of teeth, at least 6.", 6, MAX_TEETH),
            "chain_pitch": length("Distance between chain pins in metres.", maximum=10.0),
            "roller_diameter": length("Roller diameter in metres; default 0.625 times the chain pitch.", maximum=10.0),
            "seat_samples": integer("Points along each roller seat.", 2, 24, 8),
            "bore": number("Diameter in metres of the central hole; 0 for none.", 0.0, 1000.0, 0.0),
            "phase": number("Rotate the teeth around Z by this many degrees.", -360.0, 360.0, 0.0),
            "thickness": THICKNESS,
            **EXTRUSION_FIELDS,
        },
    ),
    ["teeth", "chain_pitch", "thickness"],
    family="shapes",
    intents=("chain wheel for a roller chain", "bicycle chainring"),
    nearest=(("gear", "for a gear that meshes with gears"),),
)
def sprocket(ctx, args):
    require_free_name(args["name"])
    roller = args.get("roller_diameter", 0.625 * args["chain_pitch"])
    outline, sizes = sprocket_outline(args["teeth"], args["chain_pitch"], roller, args["seat_samples"])
    holes = bore_loop(args["bore"], sizes["root_radius"], 48)
    data = extrusion_data(rotate_points(outline, args["phase"]), holes, args["thickness"], args["chamfer"], args["bevel_segments"], args["centered"])
    result = finish_shape(ctx, data, args)
    result.update(
        {
            "teeth": args["teeth"],
            "pitch_diameter": 2 * sizes["pitch_radius"],
            "outer_diameter": 2 * sizes["tip_radius"],
            "root_diameter": 2 * sizes["root_radius"],
        }
    )
    return result
