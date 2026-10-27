import bmesh
import numpy

from ..mesh_attributes import ATTRIBUTES, write_attributes
from ..noise_stack import STACK_FIELDS, finest_wavelength, stack_field
from ..registry import command
from ..schema import array, number, string
from ..selection import EXTENDED_FACE_PROPERTIES, has_selector, select_faces
from ..util import get_mesh_object, mesh_counts, rounded
from .wear import vertex_weights

POSITION_QUANTUM = 1e-6

ATTRIBUTE_FIELD = array(
    string("Attribute name.", list(ATTRIBUTES)),
    "Named float point attributes to write for later masks: slope (degrees from vertical, area-weighted over the faces at each vertex), height (world z) and curvature (mean curvature in 1/m, convex positive).",
    1,
    len(ATTRIBUTES),
)


def allowed_mask(obj, args):
    mask = numpy.ones(len(obj.data.vertices), dtype=bool)
    if not has_selector(args):
        return mask
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        chosen = {vert.index for face in select_faces(bm, obj, args) for vert in face.verts}
    finally:
        bm.free()
    mask[:] = False
    mask[list(chosen)] = True
    return mask


def weight_array(obj, group_name, count):
    weights = vertex_weights(obj, group_name)
    if weights is None:
        return numpy.ones(count)
    values = numpy.zeros(count)
    if weights:
        values[list(weights)] = list(weights.values())
    return values


def merged_directions(world_points, normals, along_normal):
    keys = numpy.round(world_points / POSITION_QUANTUM).astype(numpy.int64)
    _, first, group = numpy.unique(keys, axis=0, return_index=True, return_inverse=True)
    group = group.ravel()
    if not along_normal:
        return first, group, numpy.tile([0.0, 0.0, 1.0], (len(first), 1))
    summed = numpy.zeros((len(first), 3))
    numpy.add.at(summed, group, normals)
    length = numpy.linalg.norm(summed, axis=1)
    return first, group, numpy.divide(summed, length[:, None], out=numpy.zeros_like(summed), where=length[:, None] > 0)


def read_world(obj):
    mesh = obj.data
    count = len(mesh.vertices)
    local = numpy.empty(count * 3)
    mesh.vertices.foreach_get("co", local)
    normals = numpy.empty(count * 3)
    mesh.vertex_normals.foreach_get("vector", normals)
    matrix = numpy.array(obj.matrix_world)
    linear = matrix[:3, :3]
    local = local.reshape(count, 3)
    return local, local @ linear.T + matrix[:3, 3], normals.reshape(count, 3) @ numpy.linalg.inv(linear), linear


@command(
    "noise_displace",
    "Displace a mesh with a seeded noise stack in metres: perlin or worley fBm, ridged or billow, domain warp; no vertex moves more than amplitude and coincident vertices move together.",
    {
        "name": string("Mesh object."),
        "amplitude": number("Largest displacement of any vertex in metres (a hard bound); 0 leaves the shape alone.", 0.0, 100.0),
        **STACK_FIELDS,
        "direction": string("normal moves along the averaged vertex normal; z straight up in world space.", ["normal", "z"], "normal"),
        "vertex_group": string("Only move vertices in this vertex group, scaled by their weight."),
        "attributes": ATTRIBUTE_FIELD,
        **EXTENDED_FACE_PROPERTIES,
    },
    ["name", "amplitude"],
    slow=True,
    family="wear",
    intents=("fractal noise displacement in metres for rock or ground", "ridged, billowy or worley cell noise with a hurst exponent", "domain-warped strata on a mesh"),
    nearest=(("displace_noise", "for dents or per-vertex jitter"), ("heightfield", "for a terrain tile from a flat grid")),
)
def noise_displace(ctx, args):
    obj = get_mesh_object(args["name"])
    ctx.view_layer.update()
    mesh = obj.data
    count = len(mesh.vertices)
    local, world, normals, linear = read_world(obj)
    weights = weight_array(obj, args.get("vertex_group"), count)
    allowed = allowed_mask(obj, args) & (weights > 0)
    first, group, direction = merged_directions(world, normals, args["direction"] == "normal")
    heights = args["amplitude"] * stack_field(world[first], args)[group] * weights
    heights[~allowed] = 0.0
    moves = direction[group] * heights[:, None]
    mesh.vertices.foreach_set("co", (local + moves @ numpy.linalg.inv(linear).T).ravel())
    mesh.update()
    moved = int(numpy.count_nonzero(allowed))
    result = {"name": obj.name, "mesh": mesh_counts(mesh), "displaced_vertices": moved}
    result["max_displacement"] = rounded(float(numpy.linalg.norm(moves, axis=1).max()) if count else 0.0, 9)
    result["height_range"] = [rounded(float(heights[allowed].min()), 9), rounded(float(heights[allowed].max()), 9)] if moved else [0.0, 0.0]
    result["finest_wavelength"] = rounded(finest_wavelength(args), 9)
    if "attributes" in args:
        result["attributes"] = write_attributes(obj, args["attributes"])
    return result
