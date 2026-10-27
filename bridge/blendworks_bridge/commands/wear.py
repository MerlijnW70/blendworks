from ..errors import bad_args, not_found
from ..kit_limits import MAX_DENTS
from ..registry import command
from ..schema import integer, length, string
from ..selection import EXTENDED_FACE_PROPERTIES, has_selector, select_faces
from ..util import EditMesh, get_mesh_object, mesh_counts, rounded
from ..wear import dent_displacements, jitter_displacements


def vertex_weights(obj, group_name):
    if group_name is None:
        return None
    group = obj.vertex_groups.get(group_name)
    if group is None:
        raise not_found(f"{obj.name} has no vertex group named {group_name}")
    weights = {}
    for vertex in obj.data.vertices:
        for assignment in vertex.groups:
            if assignment.group == group.index:
                weights[vertex.index] = assignment.weight
    return weights


def allowed_vertices(bm, obj, args):
    if not has_selector(args):
        return None
    return {vert.index for face in select_faces(bm, obj, args) for vert in face.verts}


@command(
    "displace_noise",
    "Add seeded, bounded wear to a mesh: jitter (random vertex noise) or dents (hammer facets), masked by a face selection or vertex group; no vertex moves more than amplitude.",
    {
        "name": string("Mesh object."),
        "mode": string("jitter nudges every vertex; dents presses flat-bottomed hammer facets into the surface.", ["jitter", "dents"], "jitter"),
        "amplitude": length("Largest displacement of any vertex in metres.", maximum=100.0),
        "seed": integer("Random seed; the same seed gives the same result.", 0, 2**31 - 1, 0),
        "direction": string("jitter: along each vertex normal or in any direction.", ["normal", "any"], "normal"),
        "count": integer("dents: number of facets.", 1, MAX_DENTS, 20),
        "radius": length("dents: facet radius in metres.", maximum=100.0),
        "vertex_group": string("Only move vertices in this vertex group, scaled by their weight."),
        **EXTENDED_FACE_PROPERTIES,
    },
    ["name", "amplitude"],
)
def displace_noise(ctx, args):
    obj = get_mesh_object(args["name"])
    if args["mode"] == "dents" and "radius" not in args:
        raise bad_args("dents needs radius")
    if args["mode"] == "jitter" and "radius" in args:
        raise bad_args("radius works only with dents")
    weights = vertex_weights(obj, args.get("vertex_group"))
    inverse = obj.matrix_world.to_3x3().inverted_safe()
    with EditMesh(ctx, obj) as bm:
        bm.verts.ensure_lookup_table()
        bm.normal_update()
        allowed = allowed_vertices(bm, obj, args)
        if args["mode"] == "jitter":
            moves = jitter_displacements(bm, allowed, args["amplitude"], args["seed"], args["direction"] == "normal", obj.matrix_world.to_3x3())
        else:
            faces = select_faces(bm, obj, args) if has_selector(args) else list(bm.faces)
            moves = dent_displacements(bm, obj.matrix_world, faces, allowed, args["amplitude"], args["radius"], args["count"], args["seed"])
        peak = 0.0
        for index, world_move in moves.items():
            weight = weights.get(index, 0.0) if weights is not None else 1.0
            move = world_move * weight
            peak = max(peak, move.length)
            bm.verts[index].co += inverse @ move
    return {"name": obj.name, "mesh": mesh_counts(obj.data), "displaced_vertices": len(moves), "max_displacement": rounded(peak, 9)}
