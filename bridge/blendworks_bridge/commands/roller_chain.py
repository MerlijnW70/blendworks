"""The roller_chain command: a roller chain with alternating inner and outer links."""

from mathutils import Vector

from ..builder import SHAPE_FIELDS, finish_shape
from ..chain import ChainRoute, ChainSizes, chain_data, wheel_path
from ..errors import bad_args
from ..kit_limits import MAX_CHAIN_LINKS, MAX_PATH_POINTS
from ..limits import CHAIN_WHEELS, PAIR
from ..paths import object_curve
from ..registry import command
from ..schema import CREATES, array, boolean, length, obj, point3, points3, string, vector3, ref
from ..util import require_free_name

WHEEL = obj({"centre": point3("Wheel centre [x, y, z] in metres."), "radius": length("Radius the chain wraps around in metres; for a sprocket, its pitch radius.")}, ["centre", "radius"])


@command(
    "roller_chain",
    "Build a roller chain with alternating inner and outer link plates, rollers and pins along a closed or open path, a curve, or wrapped around wheels; pair it with sprocket.",
    {
        **{**SHAPE_FIELDS, "name": ref(string("Object name; must be unused.", default="Chain"), "object", CREATES)},
        "waypoints": points3("Path points [x, y, z] in metres.", PAIR, MAX_PATH_POINTS),
        "curve": ref(string("Name of an existing curve object (one spline) to follow, in world space."), "object"),
        "wheels": array(WHEEL, "Wheels to wrap the chain around: its path is the convex hull of the circles.", PAIR, CHAIN_WHEELS),
        "closed": boolean("Run the chain as a closed loop (default for wheels and closed curves)."),
        "pitch": length("Distance between pins in metres. A closed chain uses the nearest even number of links, so its real pitch is pitch_actual."),
        "plane_normal": vector3("Direction the pins point; the chain lies in the plane perpendicular to it.", [0.0, 0.0, 1.0]),
        "roller_diameter": length("Roller diameter; default 0.625 times the pitch."),
        "pin_diameter": length("Pin diameter; default 0.31 times the pitch."),
        "inner_width": length("Gap between the inner plates, the roller length; default 0.625 times the pitch."),
        "plate_thickness": length("Thickness of each link plate; default 0.1 times the pitch."),
        "plate_height": length("Width of a link plate across the chain; default 0.8 times the pitch."),
    },
    ["pitch"],
    slow=True,
    family="shapes",
    intents=("roller chain around sprockets", "bike or conveyor chain along a path"),
    nearest=(("instances", "for other repeated parts"),),
)
def roller_chain(ctx, args):
    require_free_name(args["name"])
    given = [key for key in ("waypoints", "curve", "wheels") if key in args]
    if len(given) != 1:
        raise bad_args("give the route as exactly one of waypoints, curve or wheels")
    normal = Vector(args["plane_normal"])
    if normal.length == 0:
        raise bad_args("plane_normal must not be zero")
    normal.normalize()
    if "wheels" in args:
        points, closed = wheel_path(args["wheels"], normal), True
        if args.get("closed") is False:
            raise bad_args("a chain around wheels is always closed")
    elif "curve" in args:
        points, cyclic = object_curve(args["curve"])
        closed = args.get("closed", cyclic)
    else:
        points, closed = [Vector(p) for p in args["waypoints"]], args.get("closed", False)
    sizes = ChainSizes(args["pitch"], args)
    route = ChainRoute(points, closed, args["pitch"])
    route.check_links(MAX_CHAIN_LINKS)
    pins = route.pins()
    data = chain_data(pins, closed, normal, sizes)
    result = finish_shape(ctx, data, args, pack=False)
    result.update({"links": route.links, "pins": len(pins), "pitch_actual": round(route.step, 9), "path_length": round(route.total, 6), "closed": closed})
    return result
