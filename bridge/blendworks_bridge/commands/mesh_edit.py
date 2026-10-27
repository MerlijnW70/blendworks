import math

import bmesh

from ..errors import bad_args, failed
from ..limits import MAX_MESH_VERTICES
from ..registry import command
from ..normals import hardened_loop_normals
from ..schema import boolean, indices, integer, length, number, string
from ..selection import EXTENDED_FACE_PROPERTIES, has_selector, select_faces
from ..util import EditMesh, get_mesh_object, mesh_counts

OBJECT = string("Mesh object.")


def with_faces(properties):
    merged = {"name": OBJECT}
    merged.update(properties)
    merged.update(EXTENDED_FACE_PROPERTIES)
    return merged


def world_scale(obj):
    x, y, z = (abs(value) for value in obj.matrix_world.to_scale())
    mean = (x * y * z) ** (1.0 / 3.0)
    if mean == 0:
        raise bad_args(f"{obj.name} has a zero scale")
    return mean


def local_length(obj, metres):
    return metres / world_scale(obj)


def local_direction(obj, world_vector):
    return obj.matrix_world.to_3x3().inverted_safe() @ world_vector


def world_normal(obj, normal):
    result = obj.matrix_world.to_3x3().inverted_safe().transposed() @ normal
    return result.normalized() if result.length > 0 else result


def edit_result(obj, extra=None):
    result = {"name": obj.name, "mesh": mesh_counts(obj.data)}
    result.update(extra or {})
    return result


@command(
    "extrude",
    "Extrude faces along their normals by a distance in metres (negative goes inward).",
    with_faces(
        {
            "distance": number("Distance in metres; not zero.", -1000.0, 1000.0),
            "individual": boolean("Extrude each face on its own instead of as one region.", False),
        }
    ),
    ["name", "distance"],
    family="mesh_edit",
    intents=("pull faces out along their normals", "push selected faces inward"),
    nearest=(("extrude_outline", "to make a solid from a 2D outline"),),
)
def extrude(ctx, args):
    obj = get_mesh_object(args["name"])
    if args["distance"] == 0:
        raise bad_args("distance must not be zero")
    with EditMesh(obj) as bm:
        faces = select_faces(bm, obj, args)
        if args["individual"]:
            extruded = bmesh.ops.extrude_discrete_faces(bm, faces=faces)["faces"]
            for face in extruded:
                direction = local_direction(obj, world_normal(obj, face.normal) * args["distance"])
                bmesh.ops.translate(bm, vec=direction, verts=list(face.verts))
        else:
            normal = sum((world_normal(obj, face.normal) for face in faces), faces[0].normal * 0)
            if normal.length < 1e-9:
                raise failed("the selected faces point in opposite directions; use individual=true")
            region = bmesh.ops.extrude_face_region(bm, geom=faces)
            verts = [element for element in region["geom"] if isinstance(element, bmesh.types.BMVert)]
            bmesh.ops.translate(bm, vec=local_direction(obj, normal.normalized() * args["distance"]), verts=verts)
            bmesh.ops.delete(bm, geom=faces, context="FACES")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return edit_result(obj, {"extruded_faces": len(faces)})


@command(
    "inset",
    "Inset faces by a thickness in metres, optionally pushed in or out by depth.",
    with_faces(
        {
            "thickness": length("Inset width in metres.", maximum=1000.0),
            "depth": number("Move the inner faces along their normals by this many metres.", -1000.0, 1000.0, 0.0),
            "individual": boolean("Inset each face on its own instead of as one region.", False),
        }
    ),
    ["name", "thickness"],
    family="mesh_edit",
    intents=("inset faces to make a border or frame", "rim inside a face"),
    nearest=(("bevel", "to round edges"),),
)
def inset(ctx, args):
    obj = get_mesh_object(args["name"])
    thickness = local_length(obj, args["thickness"])
    depth = local_length(obj, args["depth"])
    with EditMesh(obj) as bm:
        faces = select_faces(bm, obj, args)
        if args["individual"]:
            bmesh.ops.inset_individual(bm, faces=faces, thickness=thickness, depth=depth, use_even_offset=True)
        else:
            bmesh.ops.inset_region(bm, faces=faces, thickness=thickness, depth=depth, use_even_offset=True)
    return edit_result(obj, {"inset_faces": len(faces)})


@command(
    "bevel",
    "Bevel edges by a width in metres: the edges sharper than angle, those of the selected faces, or the listed edges; harden_normals keeps flat faces flat-shaded.",
    {
        **with_faces(
            {
                "width": length("Bevel width in metres.", maximum=1000.0),
                "segments": integer("Number of bevel segments.", 1, 16, 1),
                "profile": number("Profile shape; 0.5 is round.", 0.0, 1.0, 0.5),
                "angle": number("Only edges whose faces meet at least this many degrees off flat (not used with edges).", 0.0, 180.0, 30.0),
                "clamp": boolean("Keep bevels from overlapping.", True),
                "harden_normals": boolean("Set custom normals so flat faces keep their normals and the bevel blends into them.", False),
            }
        ),
        "edges": indices("Edge indices to bevel instead of choosing by angle; each must border two faces.", 1, 100_000),
    },
    ["name", "width"],
    family="mesh_edit",
    intents=("round or chamfer edges", "soften sharp corners", "harden normals after bevelling"),
    nearest=(("add_modifier", "for a bevel modifier that stays editable"),),
)
def bevel(ctx, args):
    obj = get_mesh_object(args["name"])
    width = local_length(obj, args["width"])
    normals = None
    with EditMesh(obj) as bm:
        edges = bevel_edges(bm, obj, args)
        verts = list({vert for edge in edges for vert in edge.verts})
        created = bmesh.ops.bevel(
            bm,
            geom=edges + verts,
            offset=width,
            offset_type="OFFSET",
            segments=args["segments"],
            profile=args["profile"],
            affect="EDGES",
            clamp_overlap=args["clamp"],
        )
        if args["harden_normals"]:
            normals = hardened_loop_normals(bm, created["faces"])
            for face in bm.faces:
                face.smooth = True
    if normals is not None:
        obj.data.normals_split_custom_set(normals)
    return edit_result(obj, {"bevelled_edges": len(edges)})


def bevel_edges(bm, obj, args):
    if "edges" in args:
        bm.edges.ensure_lookup_table()
        wanted = sorted(set(args["edges"]))
        if wanted[-1] >= len(bm.edges):
            raise bad_args(f"edge index {wanted[-1]} is out of range; {obj.name} has {len(bm.edges)} edges")
        if has_selector(args):
            raise bad_args("give edges or a face selection, not both")
        chosen = [bm.edges[index] for index in wanted]
        open_edge = next((edge.index for edge in chosen if len(edge.link_faces) != 2), None)
        if open_edge is not None:
            raise bad_args(f"edge {open_edge} does not border exactly two faces")
        return chosen
    threshold = math.radians(args["angle"]) - 1e-6
    candidates = {edge for face in select_faces(bm, obj, args) for edge in face.edges} if has_selector(args) else set(bm.edges)
    edges = [edge for edge in bm.edges if edge in candidates and sharp_enough(edge, threshold)]
    if not edges:
        raise bad_args(f"no edges of {obj.name} are at least {args['angle']} degrees sharp")
    return edges


def sharp_enough(edge, threshold):
    if len(edge.link_faces) != 2:
        return False
    return edge.calc_face_angle(0.0) >= threshold


@command(
    "subdivide",
    "Subdivide every edge (or those of the selected faces) into cuts + 1 parts, optionally smoothed.",
    with_faces(
        {
            "cuts": integer("Cuts per edge.", 1, 10, 1),
            "smooth": number("Smoothing of the new vertices, 0 to 1.", 0.0, 1.0, 0.0),
        }
    ),
    ["name"],
    family="mesh_edit",
    intents=("split edges into more parts", "add more faces and smooth"),
    nearest=(("decimate", "to reduce faces"),),
)
def subdivide(ctx, args):
    obj = get_mesh_object(args["name"])
    estimate = len(obj.data.vertices) + len(obj.data.polygons) * (args["cuts"] + 1) ** 2
    if estimate > MAX_MESH_VERTICES:
        raise failed(f"subdividing would give about {estimate} vertices; the cap is {MAX_MESH_VERTICES}")
    with EditMesh(obj) as bm:
        faces = select_faces(bm, obj, args)
        edges = list({edge for face in faces for edge in face.edges})
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=args["cuts"], use_grid_fill=True, smooth=args["smooth"])
    return edit_result(obj)


@command(
    "shade_smooth",
    "Shade faces smooth; with angle, edges sharper than angle degrees stay sharp.",
    with_faces({"angle": number("Keep edges sharper than this many degrees sharp.", 0.0, 180.0)}),
    ["name"],
    family="mesh_edit",
    intents=("smooth shading", "auto smooth by angle"),
    nearest=(("shade_flat", "for faceted shading"),),
)
def shade_smooth(ctx, args):
    obj = get_mesh_object(args["name"])
    with EditMesh(obj) as bm:
        faces = select_faces(bm, obj, args)
        for face in faces:
            face.smooth = True
        threshold = math.radians(args["angle"]) if "angle" in args else None
        for edge in {edge for face in faces for edge in face.edges}:
            edge.smooth = threshold is None or not (len(edge.link_faces) == 2 and edge.calc_face_angle(0.0) > threshold)
    return edit_result(obj, {"smooth_faces": len(faces)})


@command(
    "shade_flat",
    "Shade faces flat.",
    with_faces({}),
    ["name"],
    family="mesh_edit",
    intents=("faceted flat shading", "hard low-poly look"),
    nearest=(("shade_smooth", "for smooth shading"),),
)
def shade_flat(ctx, args):
    obj = get_mesh_object(args["name"])
    with EditMesh(obj) as bm:
        faces = select_faces(bm, obj, args)
        for face in faces:
            face.smooth = False
    return edit_result(obj, {"flat_faces": len(faces)})


@command(
    "recalc_normals",
    "Make face normals consistent, pointing outside (or inside).",
    {"name": OBJECT, "inside": boolean("Point the normals inside instead.", False)},
    ["name"],
    family="mesh_edit",
    intents=("fix normals pointing inward", "flip normals outside"),
    nearest=(("clean_mesh", "for a broader repair"),),
)
def recalc_normals(ctx, args):
    obj = get_mesh_object(args["name"])
    with EditMesh(obj) as bm:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if args["inside"]:
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
    return edit_result(obj)


@command(
    "merge_by_distance",
    "Merge vertices closer together than a distance in metres.",
    {"name": OBJECT, "distance": length("Merge distance in metres.", 0.0001, 10.0)},
    ["name"],
    family="mesh_edit",
    intents=("remove doubles", "weld overlapping vertices"),
    nearest=(("clean_mesh", "for a full repair after booleans"),),
)
def merge_by_distance(ctx, args):
    obj = get_mesh_object(args["name"])
    before = len(obj.data.vertices)
    with EditMesh(obj) as bm:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=local_length(obj, args["distance"]))
    return edit_result(obj, {"removed_vertices": before - len(obj.data.vertices)})
