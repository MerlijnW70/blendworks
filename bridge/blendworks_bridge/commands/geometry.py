import bpy

from .. import limits
from ..errors import bad_args
from ..registry import command
from ..schema import array, boolean, integer, length, number, string, vector3
from ..util import link_object, mesh_counts, place, require_free_name, vec

POINT = {"type": "array", "items": {"type": "number", "minimum": -10_000.0, "maximum": 10_000.0}, "minItems": 3, "maxItems": 3}
INDEX = {"type": "integer", "minimum": 0}
PLACEMENT = {
    "location": vector3("Object location in metres.", [0.0, 0.0, 0.0]),
    "rotation": vector3("Euler XYZ rotation in degrees.", [0.0, 0.0, 0.0]),
}


def with_placement(properties):
    merged = dict(properties)
    merged.update(PLACEMENT)
    return merged


@command(
    "mesh_from_data",
    f"Build a mesh object from vertex positions in metres and faces as vertex index lists "
    f"(at most {limits.MAX_MESH_FROM_DATA_VERTICES} vertices).",
    with_placement(
        {
            "name": string("Object name; must be unused.", default="Mesh"),
            "vertices": array(POINT, "Vertex positions [x, y, z] in metres.", 1, limits.MAX_MESH_FROM_DATA_VERTICES),
            "faces": array(
                {"type": "array", "items": INDEX, "minItems": 3, "maxItems": 10_000},
                "Faces, each a list of three or more distinct vertex indices.",
                0,
                limits.MAX_MESH_FROM_DATA_FACES,
                [],
            ),
            "edges": array(
                {"type": "array", "items": INDEX, "minItems": 2, "maxItems": 2},
                "Loose edges as pairs of vertex indices.",
                0,
                limits.MAX_MESH_FROM_DATA_FACES,
                [],
            ),
        }
    ),
    ["vertices"],
)
def mesh_from_data(ctx, args):
    require_free_name(args["name"])
    vertices, faces, edges = args["vertices"], args["faces"], args["edges"]
    count = len(vertices)
    for kind, groups in (("face", faces), ("edge", edges)):
        for position, indices in enumerate(groups):
            if max(indices) >= count:
                raise bad_args(f"{kind} {position} uses vertex {max(indices)}, but there are {count} vertices")
            if len(set(indices)) != len(indices):
                raise bad_args(f"{kind} {position} repeats a vertex")
    if not faces and not edges:
        raise bad_args("give faces or edges")
    mesh = bpy.data.meshes.new(args["name"])
    mesh.from_pydata(vertices, edges, faces)
    corrected = mesh.validate(verbose=False)
    mesh.update()
    obj = link_object(ctx, args["name"], mesh)
    place(obj, args["location"], args["rotation"])
    return {"name": obj.name, "mesh": mesh_counts(mesh), "corrected": bool(corrected), "dimensions": vec(obj.dimensions)}


@command(
    "curve_from_points",
    "Build a curve through points in metres, optionally with a round thickness (bevel_depth).",
    with_placement(
        {
            "name": string("Object name; must be unused.", default="Curve"),
            "points": array(POINT, "Points [x, y, z] in metres.", 2, limits.MAX_CURVE_POINTS),
            "kind": string("poly joins points with straight lines; bezier and nurbs are smooth.", ["poly", "bezier", "nurbs"], "poly"),
            "closed": boolean("Join the last point back to the first.", False),
            "bevel_depth": number("Radius of the round profile in metres; 0 for a bare curve.", 0.0, 1000.0, 0.0),
            "bevel_resolution": integer("Segments in a quarter of the profile.", 0, 32, 4),
            "resolution": integer("Segments between two points of a smooth curve.", 1, 64, 12),
        }
    ),
    ["points"],
)
def curve_from_points(ctx, args):
    require_free_name(args["name"])
    points = args["points"]
    curve = bpy.data.curves.new(args["name"], "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = args["resolution"]
    curve.bevel_depth = args["bevel_depth"]
    curve.bevel_resolution = args["bevel_resolution"]
    curve.use_fill_caps = args["bevel_depth"] > 0 and not args["closed"]
    spline = curve.splines.new(args["kind"].upper())
    if args["kind"] == "bezier":
        spline.bezier_points.add(len(points) - 1)
        for point, position in zip(spline.bezier_points, points):
            point.co = position
            point.handle_left_type = "AUTO"
            point.handle_right_type = "AUTO"
    else:
        spline.points.add(len(points) - 1)
        for point, position in zip(spline.points, points):
            point.co = (*position, 1.0)
        if args["kind"] == "nurbs":
            spline.order_u = min(4, len(points))
            spline.use_endpoint_u = not args["closed"]
    spline.use_cyclic_u = args["closed"]
    obj = link_object(ctx, args["name"], curve)
    place(obj, args["location"], args["rotation"])
    ctx.view_layer.update()
    return {"name": obj.name, "points": len(points), "dimensions": vec(obj.dimensions)}


@command(
    "text_object",
    "Add a 3D text object; size is the letter height in metres, extrude its depth.",
    with_placement(
        {
            "text": string("The text.", max_length=limits.MAX_TEXT_LENGTH),
            "name": string("Object name; must be unused.", default="Text"),
            "size": length("Letter size in metres.", 1.0, 1000.0),
            "extrude": number("Depth in metres (each side of the text plane).", 0.0, 1000.0, 0.0),
            "align": string("Horizontal alignment around the location.", ["left", "centre", "right"], "left"),
        }
    ),
    ["text"],
)
def text_object(ctx, args):
    require_free_name(args["name"])
    font = bpy.data.curves.new(args["name"], "FONT")
    font.body = args["text"]
    font.size = args["size"]
    font.extrude = args["extrude"]
    font.align_x = {"left": "LEFT", "centre": "CENTER", "right": "RIGHT"}[args["align"]]
    obj = link_object(ctx, args["name"], font)
    place(obj, args["location"], args["rotation"])
    ctx.view_layer.update()
    return {"name": obj.name, "characters": len(args["text"]), "dimensions": vec(obj.dimensions)}
