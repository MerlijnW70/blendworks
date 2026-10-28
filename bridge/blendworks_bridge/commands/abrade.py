import bmesh
import numpy
from mathutils import Vector

from .. import kit_limits
from ..abrasion import EDGE_DIVISOR, MAX_VOLUME_LOSS, abrade_points, convexity_of, edge_table, mesh_triangles, refine
from ..errors import bad_args
from ..meshdata import MeshData
from ..registry import command
from ..schema import integer, length, number, string
from ..topology import describe_problems, manifold_report
from ..util import get_mesh_object, mesh_counts, rounded

DEFAULT_AMOUNT = 0.5


def require_closed(mesh, name):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        report = manifold_report(bm)
    finally:
        bm.free()
    if not report["manifold"]:
        raise bad_args(f"{name} is not a closed solid: {describe_problems(report)}")


def write_back(mesh, local, triangles, uvs, materials, smooth):
    data = MeshData()
    data.verts = [Vector(point) for point in local]
    for number, face in enumerate(triangles.tolist()):
        data.face(face, uvs[number], 0, int(materials[number]), bool(smooth[number]))
    data.to_mesh(mesh, mesh.uv_layers.active.name if mesh.uv_layers.active is not None else "UVMap")
    mesh.update()


@command(
    "abrade",
    f"Round edges as abrasion does: curvature-weighted smoothing moves the sharpest vertices first so edges round while large faces stay; the mesh stays closed and loses at most {int(MAX_VOLUME_LOSS * 100)} % of its volume.",
    {
        "name": string("Closed mesh object; it is triangulated and refined to edge_length first, which drops vertex groups and attributes."),
        "amount": number("Wear from 0 to 1 as the share of the largest allowed volume loss to use; give amount or target_convexity.", 0.0, 1.0),
        "target_convexity": number("Stop once the volume over the volume of the convex hull reaches this value (1 is convex); a convex input meets it at once, so use amount.", 0.5, 1.0),
        "iterations": integer("Largest number of curvature-weighted passes.", 1, kit_limits.MAX_ABRADE_ITERATIONS, 100),
        "seed": integer("Random seed of the smooth field that makes some edges wear faster than others.", 0, 2**31 - 1, 0),
        "edge_length": length("Edges longer than this in metres are split first so edges have vertices to round; omit for a thirty-second of the longest side."),
    },
    ["name"],
    slow=True,
    family="wear",
    intents=("round the edges of a rock like river wear", "abrade a fresh fragment so its edges soften", "curvature driven smoothing that keeps large flat faces"),
    nearest=(("chip", "to cut planar chips instead of rounding"), ("displace_noise", "to roughen instead of smoothing")),
)
def abrade(ctx, args):
    obj = get_mesh_object(args["name"])
    if "amount" in args and "target_convexity" in args:
        raise bad_args("give amount or target_convexity, not both")
    amount, target = args.get("amount"), args.get("target_convexity")
    if amount is None and target is None:
        amount = DEFAULT_AMOUNT
    require_closed(obj.data, obj.name)
    matrix = numpy.array(obj.matrix_world, dtype=numpy.float64)
    local, triangles, uvs, materials, smooth = mesh_triangles(obj.data)
    world = local @ matrix[:3, :3].T + matrix[:3, 3]
    extent = float(numpy.ptp(world, axis=0).max())
    points, triangles, uvs, materials, smooth = refine(world, triangles, uvs, materials, smooth, args.get("edge_length", extent / EDGE_DIVISOR))
    mirrored = numpy.linalg.det(matrix[:3, :3]) < 0.0
    oriented = triangles[:, ::-1] if mirrored else triangles
    box_before = numpy.ptp(points, axis=0)
    moved, done, loss, stopped = abrade_points(points, oriented, edge_table(triangles), amount, target, args["iterations"], args["seed"], extent)
    inverse = numpy.linalg.inv(matrix)
    write_back(obj.data, moved @ inverse[:3, :3].T + inverse[:3, 3], triangles, uvs, materials, smooth)
    return {
        "name": obj.name,
        "iterations_run": done,
        "stopped": stopped,
        "volume_loss": rounded(loss, 6),
        "max_volume_loss": MAX_VOLUME_LOSS,
        "axis_change": [rounded(value, 6) for value in numpy.ptp(moved, axis=0) / box_before - 1.0],
        "convexity": rounded(convexity_of(moved, oriented), 6),
        "mesh": mesh_counts(obj.data),
    }
