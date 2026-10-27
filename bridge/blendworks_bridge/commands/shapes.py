from mathutils import Vector

from ..builder import SHAPE_FIELDS, finish_shape
from ..errors import bad_args
from ..kit_limits import MAX_PATH_POINTS, MAX_PROFILE_POINTS, MAX_SECTIONS, MAX_SEGMENTS
from ..lofting import loft_rings
from ..meshdata import MeshData
from ..paths import clean_path, drop_coinciding, fillet_path, object_curve
from ..profiles import profile_fields, resolve_profile
from ..registry import command
from ..revolve import lathe_data
from ..schema import array, boolean, integer, length, number, obj, point3, points2, points3, string, vector3
from ..skin import cap, skin
from ..sweeping import check_closed_arguments, sweep_rings
from ..util import require_free_name


def with_shape_fields(properties, name):
    merged = dict(SHAPE_FIELDS)
    merged["name"] = string("Object name; must be unused.", default=name)
    merged.update(properties)
    return merged


@command(
    "lathe",
    "Revolve a profile of [x, z] points (x is the distance from the axis) into a turned part with UVs; closed and manifold when both ends lie on the axis.",
    with_shape_fields(
        {
            "profile": points2(
                "Profile [x, z] points in metres in the XZ plane with x >= 0; the first and last point may lie on the axis (x = 0).",
                2,
                MAX_PROFILE_POINTS,
            ),
            "axis": string("Axis to revolve around: z (profile z is the height) or x (profile x is the height, profile z the distance).", ["z", "x"], "z"),
            "segments": integer("Steps around the axis.", 3, MAX_SEGMENTS, 32),
            "angle": number("Sweep angle in degrees, above 0 and at most 360.", None, 360.0, 360.0, exclusive_minimum=0.0),
            "caps": boolean("Close the open ends: flat discs at a full turn, flat wedge faces at a partial one.", True),
            "seam_merge": boolean("Share the vertices at the seam of a full turn; false leaves a duplicated, open seam.", True),
            "closed": boolean("Join the last profile point to the first (a ring such as a torus); the profile must not touch the axis.", False),
        },
        "Lathe",
    ),
    ["profile"],
)
def lathe(ctx, args):
    require_free_name(args["name"])
    data = lathe_data(args["profile"], args["axis"], args["segments"], args["angle"], args["caps"], args["seam_merge"], args["closed"])
    result = finish_shape(ctx, data, args)
    result["profile_points"] = len(args["profile"])
    return result


def sweep_path(args):
    given = [key for key in ("waypoints", "curve") if key in args]
    if len(given) != 1:
        raise bad_args("give the route as exactly one of waypoints or curve")
    if "waypoints" in args:
        closed = args.get("closed", False)
        return clean_path(args["waypoints"], closed), closed
    points, cyclic = object_curve(args["curve"])
    closed = args.get("closed", cyclic)
    return clean_path(points, closed, f"curve {args['curve']}"), closed


@command(
    "sweep",
    "Sweep a closed profile along points or a curve with rotation-minimising frames (no flips); taper, twist, corner fillets, caps, closed loops; UVs unwrapped along the length.",
    with_shape_fields(
        {
            **profile_fields(),
            "waypoints": points3("Path points [x, y, z] in metres; the profile origin follows them.", 2, MAX_PATH_POINTS),
            "curve": string("Name of an existing curve object (one spline) to follow instead of waypoints, in world space."),
            "closed": boolean("Join the end of the path to its start (default: the curve's own setting, else false)."),
            "up": vector3("Direction the profile's v axis points at the start of the path.", [0.0, 0.0, 1.0]),
            "scale_start": length("Profile scale at the start of the path.", 1.0, 1000.0),
            "scale_end": length("Profile scale at the end of the path; the scale changes linearly with distance.", 1.0, 1000.0),
            "twist": number("Total twist in degrees along the path; on a closed path a multiple of 360.", -36000.0, 36000.0, 0.0),
            "fillet_radius": number("Round every path corner with a circular arc of this radius in metres; 0 keeps mitred corners.", 0.0, 1000.0, 0.0),
            "fillet_segments": integer("Segments per rounded corner.", 1, 64, 8),
            "caps": boolean("Close the ends of an open path with flat faces.", True),
        },
        "Sweep",
    ),
    slow=True,
)
def sweep(ctx, args):
    require_free_name(args["name"])
    profile = resolve_profile(args)
    points, closed = sweep_path(args)
    if closed:
        check_closed_arguments(args["twist"], args["scale_start"], args["scale_end"])
    if args["fillet_radius"] > 0:
        points = drop_coinciding(fillet_path(points, args["fillet_radius"], args["fillet_segments"], closed), closed)
    if len(points) > MAX_PATH_POINTS:
        raise bad_args(f"the path has {len(points)} points; the cap is {MAX_PATH_POINTS}")
    up = Vector(args["up"])
    if up.length == 0:
        raise bad_args("up must not be zero")
    rings, total = sweep_rings(points, closed, profile, up, args["twist"], args["scale_start"], args["scale_end"])
    data = MeshData()
    indices = skin(data, rings, closed_v=closed)
    if args["caps"] and not closed:
        cap(data, indices[0], rings[0], points[0] - points[1])
        cap(data, indices[-1], rings[-1], points[-1] - points[-2])
    result = finish_shape(ctx, data, args)
    result.update({"length": round(total, 6), "rings": len(rings), "closed": closed})
    return result


SECTION = obj(
    {
        **profile_fields(),
        "position": point3("Section centre [x, y, z] in metres."),
        "rotation": vector3("Euler XYZ rotation in degrees; the section plane is XY and its normal +Z before rotating.", [0.0, 0.0, 0.0]),
        "scale": length("Section scale.", 1.0, 1000.0),
    },
    ["position"],
)


@command(
    "loft",
    "Skin a surface through cross-sections with their own shape, position and orientation; short sections get points by splitting their longest edges, and starts are aligned to avoid twist.",
    with_shape_fields(
        {
            "sections": array(SECTION, "Sections in order, from two.", 2, MAX_SECTIONS),
            "closed": boolean("Join the last section back to the first (a ring of at least three).", False),
            "caps": boolean("Close the first and last section with flat faces on an open loft.", True),
            "samples": integer("Points per section; default the largest section's count, and never fewer.", 3, MAX_PROFILE_POINTS),
            "align": boolean("Rotate each section's start point to the position that twists the skin least.", True),
        },
        "Loft",
    ),
    ["sections"],
    slow=True,
)
def loft(ctx, args):
    require_free_name(args["name"])
    sections = args["sections"]
    if args["closed"] and len(sections) < 3:
        raise bad_args("a closed loft needs at least three sections")
    rings, directions = loft_rings(sections, args["closed"], args.get("samples"), args["align"])
    data = MeshData()
    indices = skin(data, rings, closed_v=args["closed"])
    if args["caps"] and not args["closed"]:
        cap(data, indices[0], rings[0], -directions[0])
        cap(data, indices[-1], rings[-1], directions[-1])
    result = finish_shape(ctx, data, args)
    result.update({"sections": len(sections), "points_per_section": len(rings[0])})
    return result
