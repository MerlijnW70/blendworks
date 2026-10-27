import json
import os

import bpy
from mathutils import Vector

from .. import kit_limits, limits
from ..errors import bad_args, not_found
from ..meshdata import MeshData
from ..registry import command
from ..schema import array, boolean, integer, length, names, number, obj as object_schema, string, validate, vector3
from ..util import link_object, mesh_counts, place, require_free_name, vec

POINT = {"type": "array", "items": {"type": "number", "minimum": -10_000.0, "maximum": 10_000.0}, "minItems": 3, "maxItems": 3}
INDEX = {"type": "integer", "minimum": 0}
UV = {"type": "array", "items": {"type": "number", "minimum": -1000.0, "maximum": 1000.0}, "minItems": 2, "maxItems": 2}
PLACEMENT = {
    "location": vector3("Object location in metres.", [0.0, 0.0, 0.0]),
    "rotation": vector3("Euler XYZ rotation in degrees.", [0.0, 0.0, 0.0]),
}


def with_placement(properties):
    merged = dict(properties)
    merged.update(PLACEMENT)
    return merged


DATA_FIELDS = {
    "vertices": array(POINT, "Vertex positions [x, y, z] in metres.", 1, limits.MAX_MESH_FROM_DATA_VERTICES),
    "faces": array(
        {"type": "array", "items": INDEX, "minItems": 3, "maxItems": 10_000},
        "Faces, each a list of three or more distinct vertex indices.",
        0,
        limits.MAX_MESH_FROM_DATA_FACES,
    ),
    "edges": array(
        {"type": "array", "items": INDEX, "minItems": 2, "maxItems": 2},
        "Loose edges as pairs of vertex indices.",
        0,
        limits.MAX_MESH_FROM_DATA_FACES,
    ),
    "material_indices": array(
        {"type": "integer", "minimum": 0, "maximum": 32767}, "Material slot index of each face, one per face.", 1, limits.MAX_MESH_FROM_DATA_FACES
    ),
    "materials": names("Existing materials to put in the slots, in order.", 1, 256),
    "uvs": array(UV, "UV [u, v] of every face corner, in face order: as many as the faces have corners in total.", 1, 4 * limits.MAX_MESH_FROM_DATA_FACES),
    "vertex_uvs": array(UV, "UV [u, v] per vertex, shared by all its corners; an alternative to uvs.", 1, limits.MAX_MESH_FROM_DATA_VERTICES),
    "smooth": boolean("Shade every face smooth."),
    "smooth_faces": array(INDEX, "Indices of the faces to shade smooth; the others stay flat.", 1, limits.MAX_MESH_FROM_DATA_FACES),
    "sharp_edges": array(
        {"type": "array", "items": INDEX, "minItems": 2, "maxItems": 2}, "Edges to mark sharp, as vertex index pairs.", 1, limits.MAX_MESH_FROM_DATA_FACES
    ),
    "creases": array(
        object_schema(
            {
                "edge": array(INDEX, "The edge as two vertex indices.", 2, 2),
                "value": {"type": "number", "description": "Crease from 0 (none) to 1 (full).", "minimum": 0.0, "maximum": 1.0},
            },
            ["edge", "value"],
        ),
        "Subdivision creases: each an edge as two vertex indices and a value from 0 to 1.",
        1,
        limits.MAX_MESH_FROM_DATA_FACES,
    ),
}
DATA_SCHEMA = object_schema(DATA_FIELDS)


def read_data_file(ctx, path):
    resolved = ctx.workspace.existing(path, (".json",))
    if os.path.getsize(resolved) > kit_limits.MAX_DATA_FILE_BYTES:
        raise bad_args(f"{path} is larger than {kit_limits.MAX_DATA_FILE_BYTES} bytes")
    try:
        with open(resolved, "r", encoding="utf-8") as handle:
            content = json.load(handle)
    except (OSError, ValueError) as error:
        raise bad_args(f"{path} is not readable JSON: {error}") from error
    return validate(DATA_SCHEMA, content)


def check_indices(kind, groups, count):
    for position, indices in enumerate(groups):
        if max(indices) >= count:
            raise bad_args(f"{kind} {position} uses vertex {max(indices)}, but there are {count} vertices")
        if len(set(indices)) != len(indices):
            raise bad_args(f"{kind} {position} repeats a vertex")


def corner_uvs(data, faces):
    total = sum(len(face) for face in faces)
    if "uvs" in data and "vertex_uvs" in data:
        raise bad_args("give uvs or vertex_uvs, not both")
    if "uvs" in data:
        if len(data["uvs"]) != total:
            raise bad_args(f"uvs has {len(data['uvs'])} entries but the faces have {total} corners")
        cursor = 0
        out = []
        for face in faces:
            out.append(data["uvs"][cursor : cursor + len(face)])
            cursor += len(face)
        return out
    if "vertex_uvs" in data:
        if len(data["vertex_uvs"]) != len(data["vertices"]):
            raise bad_args(f"vertex_uvs has {len(data['vertex_uvs'])} entries for {len(data['vertices'])} vertices")
        return [[data["vertex_uvs"][index] for index in face] for face in faces]
    return None


def mesh_data_from(data):
    faces = data.get("faces", [])
    edges = data.get("edges", [])
    count = len(data["vertices"])
    check_indices("face", faces, count)
    check_indices("edge", edges, count)
    if not faces and not edges:
        raise bad_args("give faces or edges")
    if "smooth" in data and "smooth_faces" in data:
        raise bad_args("give smooth or smooth_faces, not both")
    if "material_indices" in data and len(data["material_indices"]) != len(faces):
        raise bad_args(f"material_indices has {len(data['material_indices'])} entries for {len(faces)} faces")
    if "smooth_faces" in data and max(data["smooth_faces"]) >= len(faces):
        raise bad_args(f"smooth_faces uses face {max(data['smooth_faces'])}, but there are {len(faces)} faces")
    uvs = corner_uvs(data, faces)
    smooth = set(data.get("smooth_faces", ()))
    mesh_data = MeshData()
    mesh_data.verts = [Vector(point) for point in data["vertices"]]
    for position, face in enumerate(faces):
        mesh_data.face(
            face,
            uvs[position] if uvs is not None else None,
            0,
            data["material_indices"][position] if "material_indices" in data else 0,
            data.get("smooth", False) or position in smooth,
        )
    mesh_data.edges = [tuple(edge) for edge in edges]
    for a, b in data.get("sharp_edges", ()):
        check_indices("sharp edge", [[a, b]], count)
        mesh_data.sharp.add((min(a, b), max(a, b)))
    for crease in data.get("creases", ()):
        check_indices("crease", [crease["edge"]], count)
        mesh_data.creases[tuple(sorted(crease["edge"]))] = crease["value"]
    return mesh_data


@command(
    "mesh_from_data",
    f"Build a mesh object from vertices in metres and faces as vertex index lists (at most {limits.MAX_MESH_FROM_DATA_VERTICES} vertices), "
    "with material indices, UVs, smooth flags and creases; or read it all from a JSON file.",
    with_placement(
        {
            "name": string("Object name; must be unused.", default="Mesh"),
            "path": string("JSON file in the workspace holding vertices, faces and the optional fields below, instead of giving them here."),
            **DATA_FIELDS,
        }
    ),
    [],
)
def mesh_from_data(ctx, args):
    require_free_name(args["name"])
    fields = {key: args[key] for key in DATA_FIELDS if key in args}
    if "path" in args:
        if fields:
            raise bad_args("give the mesh in path or in the fields, not both")
        fields = read_data_file(ctx, args["path"])
    if "vertices" not in fields:
        raise bad_args("give vertices, or a path to a file that has them")
    materials = [bpy.data.materials.get(name) for name in fields.get("materials", [])]
    missing = [name for name, material in zip(fields.get("materials", []), materials) if material is None]
    if missing:
        raise not_found(f"no material named {missing[0]}; create it with add_material")
    mesh_data = mesh_data_from(fields)
    mesh = bpy.data.meshes.new(args["name"])
    corrected = mesh_data.to_mesh(mesh)
    for material in materials:
        mesh.materials.append(material)
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
