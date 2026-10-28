import bpy
from mathutils import Vector

from ..copies import linked_copies, realized_copy
from ..errors import bad_args
from ..instancing import (
    circle_placements,
    edge_chain,
    finish_placements,
    path_placements,
    point_placements,
)
from ..kit_limits import MAX_INSTANCES, MAX_PATH_POINTS
from ..paths import object_curve
from ..phyllotaxis import CURVES, MODES, Layout, phyllotaxis_layout
from ..registry import command
from ..revolve import lathe_data
from ..schema import array, boolean, described, integer, length, number, obj, point3, points3, string, vector3
from ..util import get_mesh_object, mesh_counts, require_free_name, vec

PLACEMENT_MODES = ("points", "waypoints", "curve", "edges", "circle", "phyllotaxis")

CIRCLE = described(
    obj(
        {
            "centre": point3("Circle centre [x, y, z] in metres."),
            "radius": length("Circle radius in metres.", maximum=10_000.0),
            "count": integer("Number of instances.", 1, MAX_INSTANCES),
            "normal": vector3("Axis of the circle; instances are placed counter-clockwise around it.", [0.0, 0.0, 1.0]),
            "start_angle": number("Angle of the first instance in degrees.", -360.0, 360.0, 0.0),
            "sweep": number("Angle covered in degrees; 360 spaces the instances evenly all the way round, less puts the last one at the end.", 1.0, 360.0, 360.0),
        },
        ["centre", "radius", "count"],
    ),
    "Place instances on a circle.",
)

def age_curve(description, minimum, maximum, unit):
    return described(
        obj(
            {
                "from": number(f"{unit} of the first organ.", minimum, maximum),
                "to": number(f"{unit} of the last organ.", minimum, maximum),
                "curve": string("How the value runs from the first organ to the last, by the organ's share of the way (0 to 1): linear t, ease_in t^2, ease_out 1-(1-t)^2, smooth 3t^2-2t^3.", CURVES, "linear"),
            },
            ["from", "to"],
        ),
        description,
    )


PHYLLOTAXIS = described(
    obj(
        {
            "count": integer("Number of organs.", 1, MAX_INSTANCES),
            "mode": string(
                "disc: radius c*sqrt(n) on the XY plane. cylinder: constant radius, height growing linearly with n. cone: apex up at height, base radius at z 0, spaced down the slope so each organ has the same area. sphere: Archimedes bands of equal area from the top pole. surface: the same, on the target, a mesh of revolution about its own Z axis.",
                MODES,
                "disc",
            ),
            "c": length("disc: scale in metres, organ n at radius c*sqrt(n). cone: the same along the slope from the apex, default fills the slope down to the base edge.", maximum=10_000.0),
            "divergence": number("Angle in degrees between successive organs; default 137.5.", 0.0, 360.0),
            "golden": boolean("Use the exact golden angle 360 * (1 - 1/phi) = 137.50776 degrees instead of divergence.", False),
            "radius": length("cylinder, cone, sphere: radius in metres.", maximum=10_000.0),
            "height": length("cylinder: height reached by the last organ. cone: height of the cone.", maximum=10_000.0),
            "polar_extent": number("sphere: angle from the top pole to the last organ's band edge, in degrees (default 180 covers the whole sphere, 120 makes a rosette cap).", 1.0, 180.0),
            "target": string("surface: mesh object of revolution about its own Z axis, scaled uniformly; organs sit on the outer profile."),
            "start": integer("Index of the first organ; organs are numbered start, start+1, ... Disc radii and every angle follow the index.", 0, 1_000_000, 0),
            "scale_by_age": age_curve("Scale of each organ from its place in the sequence (first organ to last), multiplying scale.", 0.0001, 1000.0, "Scale"),
            "tilt_by_age": age_curve("Opening of each organ from its place in the sequence: its X axis lifts towards the surface normal by this many degrees, as petals and scales open. Needs align frame or radial.", -180.0, 180.0, "Angle in degrees"),
            "jitter": described(
                obj(
                    {
                        "amount": number("Position shift as a share of the spacing between organs.", 0.0, 1.0, 0.0),
                        "rotation": number("Turn about the organ's Z axis, up to this many degrees either way.", 0.0, 180.0, 0.0),
                        "scale": number("Scale change, up to this share either way.", 0.0, 0.99, 0.0),
                        "seed": integer("Seed; the same seed gives the same result.", 0, 2**31 - 1, 0),
                    },
                    ["seed"],
                ),
                "Optional seeded randomness; without it the arrangement is exact and identical every run.",
            ),
        },
        ["count"],
    ),
    "Place organs in the golden-angle arrangement of sunflower heads, pine cones and rosettes (organ n at angle n * divergence). The organ's X axis points away from the centre along the surface and Z is the surface normal with align frame; with align radial, X points away from the axis and Z up.",
)

COMMON = {
    "name": string("Name of the group (linked copies) or of the realised mesh; copies are named name_000, name_001 and so on.", default="Instances"),
    "spacing": length("Distance in metres between instances along waypoints, a curve or edges.", maximum=10_000.0),
    "count": integer("Number of instances along waypoints, a curve or edges, spread over its whole length.", 1, MAX_INSTANCES),
    "offset": number("Distance in metres from the start of the path to the first instance (with spacing).", 0.0, 10_000.0),
    "up": vector3("Direction instances' Z axis leans toward along a path, at the start.", [0.0, 0.0, 1.0]),
    "align": string(
        "none keeps the world axes; frame turns X along the path (or the circle tangent) and Z to the up or normal direction; radial (circle and phyllotaxis) turns X away from the centre.",
        ["none", "frame", "radial"],
        "frame",
    ),
    "rotation": vector3("Extra Euler XYZ rotation in degrees applied to every instance in its own axes.", [0.0, 0.0, 0.0]),
    "scale": length("Scale of every instance.", 1.0, 1000.0),
    "rotations": array(vector3("Euler XYZ degrees."), "One extra rotation per instance, replacing rotation.", 1, MAX_INSTANCES),
    "scales": array({"type": "number", "exclusiveMinimum": 0, "maximum": 1000.0}, "One scale per instance, replacing scale.", 1, MAX_INSTANCES),
    "realize": boolean("Merge the copies into one real mesh (for export) instead of linked objects.", False),
    "group": boolean("Parent linked copies to an empty named name so they move together.", True),
}


def placements_from(ctx, args):
    given = [mode for mode in PLACEMENT_MODES if mode in args]
    if len(given) != 1:
        raise bad_args(f"give the places as exactly one of {', '.join(PLACEMENT_MODES)}")
    mode = given[0]
    align = args["align"]
    if align == "radial" and mode not in ("circle", "phyllotaxis"):
        raise bad_args("align radial works only with circle and phyllotaxis")
    stray = [key for key in ("spacing", "count", "offset") if key in args]
    if mode in ("points", "circle", "phyllotaxis") and stray:
        raise bad_args(f"{', '.join(stray)} works only with waypoints, curve or edges")
    if mode == "phyllotaxis":
        spec = args["phyllotaxis"]
        target = get_mesh_object(spec["target"]) if "target" in spec else None
        return phyllotaxis_layout(spec, align, target)
    if mode == "points":
        return point_placements(args["points"], args.get("normals"), align)
    if "normals" in args:
        raise bad_args("normals works only with points")
    if mode == "circle":
        return circle_placements(args["circle"], align)
    closed = args.get("closed", False)
    if mode == "waypoints":
        points = args["waypoints"]
    elif mode == "curve":
        points, cyclic = object_curve(args["curve"])
        closed = args.get("closed", cyclic)
    else:
        points, closed = edge_chain(get_mesh_object(args["edges"]))
    if len(points) > MAX_PATH_POINTS:
        raise bad_args(f"the path has {len(points)} points; the cap is {MAX_PATH_POINTS}")
    return path_placements([Vector(p) for p in points], closed, args.get("spacing"), args.get("count"), args.get("offset", 0.0), Vector(args["up"]), align)


def place_copies(ctx, args, mesh, matrices):
    if not matrices:
        raise bad_args("no instances to place")
    if len(matrices) > MAX_INSTANCES:
        raise bad_args(f"{len(matrices)} instances; the cap is {MAX_INSTANCES}")
    if args["realize"]:
        require_free_name(args["name"])
        merged = realized_copy(ctx, args["name"], mesh, matrices)
        ctx.view_layer.update()
        return {"name": merged.name, "count": len(matrices), "realized": True, "mesh": mesh_counts(merged.data), "dimensions": vec(merged.dimensions)}
    require_free_name(args["name"] if args["group"] else None)
    parent, copies = linked_copies(ctx, args["name"], mesh, matrices, args["group"])
    ctx.view_layer.update()
    shown = [copy.name for copy in copies[:3]]
    return {
        "name": parent.name if parent is not None else copies[0].name,
        "count": len(copies),
        "realized": False,
        "objects": shown if len(copies) > 3 else [copy.name for copy in copies],
        "shared_mesh": mesh.name,
        "vertices_per_copy": len(mesh.vertices),
    }


@command(
    "instances",
    "Place linked copies of an object at points, along waypoints, a curve or edge loop, on a circle, or in a golden-angle phyllotaxis; realize merges them.",
    {
        **COMMON,
        "source": string("Mesh object whose mesh is copied; its own transform is not used."),
        "points": points3("Places as [x, y, z] points in metres.", 1, MAX_INSTANCES),
        "normals": points3("One surface normal per point; with align frame the instance's Z axis follows it.", 1, MAX_INSTANCES),
        "waypoints": points3("Places along a polyline through these points.", 2, MAX_PATH_POINTS),
        "curve": string("Places along this curve object (one spline), in world space."),
        "edges": string("Places along the edge loop or edge chain of this mesh object, in world space."),
        "closed": boolean("Treat waypoints or a curve as a closed loop."),
        "circle": CIRCLE,
        "phyllotaxis": PHYLLOTAXIS,
    },
    ["source"],
    slow=True,
    family="placement",
    intents=("linked copies along a curve, edge loop or waypoints", "copies on a circle or at points", "scatter copies", "sunflower seeds, pine cone scales or a rosette in the golden angle"),
    nearest=(("duplicate", "for one copy"), ("rivet_line", "for rivets between two points")),
)
def instances(ctx, args):
    source = get_mesh_object(args["source"])
    placed = placements_from(ctx, args)
    layout = placed if isinstance(placed, Layout) else None
    placements = layout.placements if layout is not None else placed
    matrices = finish_placements(placements, args["rotation"], args["scale"], args.get("rotations"), args.get("scales"))
    result = place_copies(ctx, args, source.data, matrices)
    if layout is not None:
        result["phyllotaxis"] = layout.summary
    return result


def rivet_mesh(name, radius, height):
    profile = [[0.0, 0.0], [radius, 0.0], [radius * 0.97, height * 0.35], [radius * 0.66, height * 0.85], [0.0, height]]
    data = lathe_data(profile, "z", 12, 360.0, True, True, False)
    mesh = bpy.data.meshes.new(name)
    data.to_mesh(mesh)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return mesh


@command(
    "rivet_line",
    "Place a row of rivets or bolts between two points at a spacing or count; uses the given source mesh or a built-in domed rivet head. Convenience over instances.",
    {
        "name": string("Name of the group (linked copies) or of the realised mesh; copies are named name_000, name_001 and so on.", default="Rivets"),
        **{key: COMMON[key] for key in ("spacing", "count", "offset", "rotation", "scale", "rotations", "scales", "realize", "group")},
        "start": point3("First rivet position [x, y, z] in metres."),
        "end": point3("Last possible rivet position [x, y, z] in metres."),
        "source": string("Mesh object to copy as the rivet; default a domed head built from head_radius and head_height."),
        "normal": vector3("Direction the rivets point (their Z axis); default leaves them upright."),
        "head_radius": length("Built-in rivet head radius in metres.", 0.008, 1.0),
        "head_height": length("Built-in rivet head height in metres.", 0.006, 1.0),
    },
    ["start", "end"],
    slow=True,
    family="placement",
    intents=("row of rivets or bolts between two points", "rivets along a seam"),
    nearest=(("instances", "for other patterns"),),
)
def rivet_line(ctx, args):
    start, end = Vector(args["start"]), Vector(args["end"])
    if (end - start).length < 1e-9:
        raise bad_args("start and end must differ")
    mesh = get_mesh_object(args["source"]).data if "source" in args else None
    up = Vector(args["normal"]) if "normal" in args else Vector((0.0, 0.0, 1.0))
    if up.length == 0:
        raise bad_args("normal must not be zero")
    placements = path_placements([start, end], False, args.get("spacing"), args.get("count"), args.get("offset", 0.0), up, "frame")
    matrices = finish_placements(placements, args["rotation"], args["scale"], args.get("rotations"), args.get("scales"))
    built = mesh is None
    if built:
        mesh = rivet_mesh(f"{args['name']}_rivet", args["head_radius"], args["head_height"])
    result = place_copies(ctx, args, mesh, matrices)
    if built and args["realize"]:
        bpy.data.meshes.remove(mesh)
    result["length"] = round((end - start).length, 6)
    return result
