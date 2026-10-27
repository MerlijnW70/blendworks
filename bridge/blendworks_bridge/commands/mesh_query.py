import math

import bmesh
from mathutils import Matrix, Vector

from ..errors import bad_args
from ..kit_limits import DEFAULT_QUERY_PAGE, MAX_QUERY_PAGE
from ..registry import command
from ..schema import indices, integer, number, point3, string, vector3
from ..selection import EXTENDED_FACE_PROPERTIES, face_islands, has_selector, select_faces, world_area
from ..util import EditMesh, bounds_dict, bounds_of, get_mesh_object, mesh_counts, rounded, vec

OBJECT = string("Mesh object.")


def selection_fields(extra):
    fields = {"name": OBJECT}
    fields.update(extra)
    fields.update(EXTENDED_FACE_PROPERTIES)
    return fields


def material_name(obj, index):
    materials = obj.data.materials
    if 0 <= index < len(materials) and materials[index] is not None:
        return materials[index].name
    return None


@command(
    "mesh_query",
    "List faces with world centre, normal, area, material and island, paged; use the same selectors as extrude (faces, facing, box, with_material, normal, island, area_min, area_max).",
    selection_fields(
        {
            "offset": integer("Number of matching faces to skip.", 0, None, 0),
            "limit": integer("Faces per page.", 1, MAX_QUERY_PAGE, DEFAULT_QUERY_PAGE),
        }
    ),
    ["name"],
    mutates=False,
)
def mesh_query(ctx, args):
    obj = get_mesh_object(args["name"])
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        faces = select_faces(bm, obj, args, allow_empty=True)
        islands = face_islands(bm)
        matrix = obj.matrix_world
        normal_matrix = matrix.to_3x3().inverted_safe().transposed()
        page = faces[args["offset"] : args["offset"] + args["limit"]]
        entries = []
        for face in page:
            normal = normal_matrix @ face.normal
            entries.append(
                {
                    "index": face.index,
                    "centre": vec(matrix @ face.calc_center_median()),
                    "normal": vec(normal.normalized() if normal.length > 0 else normal),
                    "area": rounded(world_area(matrix, face), 9),
                    "material": material_name(obj, face.material_index),
                    "island": islands[face.index],
                    "vertices": len(face.verts),
                }
            )
        end = args["offset"] + len(page)
        return {
            "name": obj.name,
            "total": len(faces),
            "offset": args["offset"],
            "faces": entries,
            "next_offset": end if end < len(faces) else None,
            "islands": len(set(islands.values())),
        }
    finally:
        bm.free()


def pivot_of(obj, vertices, args):
    if "pivot" in args:
        return Vector(args["pivot"])
    bounds = bounds_of([obj.matrix_world @ vert.co for vert in vertices])
    return (bounds[0] + bounds[1]) / 2.0


def selected_vertices(bm, obj, args):
    if "vertices" in args:
        if has_selector(args):
            raise bad_args("give vertices or a face selection, not both")
        bm.verts.ensure_lookup_table()
        wanted = sorted(set(args["vertices"]))
        if wanted[-1] >= len(bm.verts):
            raise bad_args(f"vertex index {wanted[-1]} is out of range; {obj.name} has {len(bm.verts)} vertices")
        return [bm.verts[index] for index in wanted], []
    faces = select_faces(bm, obj, args)
    return list({vert for face in faces for vert in face.verts}), faces


@command(
    "transform_selection",
    "Move, rotate and scale the vertices of selected faces (same selectors as extrude) or listed vertices about a pivot, in world space: scale, then rotate, then move.",
    selection_fields(
        {
            "vertices": indices("Vertex indices to transform instead of a face selection."),
            "move": vector3("Translation in metres.", [0.0, 0.0, 0.0]),
            "push": number("Extra translation in metres along the selection's average face normal.", -10_000.0, 10_000.0, 0.0),
            "rotate": vector3("Euler XYZ rotation in degrees about the pivot.", [0.0, 0.0, 0.0]),
            "scale": vector3("Scale factors per world axis about the pivot; none may be zero.", [1.0, 1.0, 1.0], -1000.0, 1000.0),
            "pivot": point3("Pivot [x, y, z] in metres; default the centre of the selection's bounds."),
        }
    ),
    ["name"],
)
def transform_selection(ctx, args):
    obj = get_mesh_object(args["name"])
    if any(value == 0 for value in args["scale"]):
        raise bad_args("scale must not be zero on any axis")
    inverse = obj.matrix_world.inverted_safe()
    with EditMesh(ctx, obj) as bm:
        verts, faces = selected_vertices(bm, obj, args)
        push = Vector((0.0, 0.0, 0.0))
        if args["push"] != 0:
            if not faces:
                raise bad_args("push needs a face selection")
            normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
            total = sum(((normal_matrix @ face.normal).normalized() for face in faces), Vector((0.0, 0.0, 0.0)))
            if total.length < 1e-9:
                raise bad_args("the selected faces point in opposite directions; use move instead of push")
            push = total.normalized() * args["push"]
        pivot = pivot_of(obj, verts, args)
        rotation = Matrix.Rotation(0, 4, "X")
        for axis, degrees in zip("XYZ", args["rotate"]):
            rotation = Matrix.Rotation(math.radians(degrees), 4, axis) @ rotation
        scaling = Matrix.Diagonal((*args["scale"], 1.0))
        around = Matrix.Translation(pivot) @ rotation @ scaling @ Matrix.Translation(-pivot)
        shift = Matrix.Translation(Vector(args["move"]) + push)
        full = inverse @ shift @ around @ obj.matrix_world
        for vert in verts:
            vert.co = full @ vert.co
    return {"name": obj.name, "mesh": mesh_counts(obj.data), "transformed_vertices": len(verts), "bounds": bounds_dict(bounds_of([obj.matrix_world @ v.co for v in obj.data.vertices]))}
