import bmesh
import numpy

from ..errors import bad_args
from ..limits import FRACTION, MAX_MESH_VERTICES
from ..registry import command
from ..schema import boolean, length, number, ref, string
from ..topology import mesh_report
from ..util import get_mesh_object, mesh_counts, rounded
from .modifiers import add_modifier

UNIFORM = 1e-6
MIN_VOXEL = 1e-4


def surface_area(mesh):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        return float(sum(face.calc_area() for face in bm.faces))
    finally:
        bm.free()


def shell_count(mesh):
    parent = list(range(len(mesh.vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for polygon in mesh.polygons:
        first = find(polygon.vertices[0])
        for index in polygon.vertices[1:]:
            parent[find(index)] = first
    return len({find(index) for polygon in mesh.polygons for index in polygon.vertices})


def local_voxel(obj, voxel_size):
    scale = numpy.array(obj.matrix_world.to_scale())
    if numpy.ptp(scale) > UNIFORM * max(abs(scale).max(), 1.0):
        raise bad_args(f"{obj.name} has a non-uniform scale; apply it first so the voxel size is in metres")
    return voxel_size / float(abs(scale[0]))


def refuse_oversize(area, voxel_size):
    vertices = area / (voxel_size * voxel_size)
    if vertices > MAX_MESH_VERTICES:
        raise bad_args(f"a voxel size of {voxel_size} m would give about {int(vertices)} vertices; the cap is {MAX_MESH_VERTICES}. Use a larger voxel size")


def voxel_remesh(ctx, obj, voxel_size, adaptivity, smooth):
    scale = numpy.array(obj.matrix_world.to_scale())
    refuse_oversize(surface_area(obj.data) * float(abs(scale[0])) ** 2, voxel_size)
    settings = {"mode": "VOXEL", "voxel_size": local_voxel(obj, voxel_size), "adaptivity": adaptivity, "use_smooth_shade": smooth}
    return add_modifier(ctx, obj, "REMESH", settings, True)


@command(
    "remesh",
    "Rebuild a mesh as one clean surface of even voxels (Remesh modifier, voxel mode) and apply it at once; refuses a voxel size that would exceed the vertex cap.",
    {
        "name": ref(string("Mesh object."), "object"),
        "voxel_size": length("Voxel edge in metres; smaller is finer and slower; the mesh_vertices limit caps how fine.", 0.05),
        "adaptivity": number("0 keeps even quads; larger values merge flat areas into fewer triangles.", 0.0, FRACTION, 0.0),
        "smooth_shading": boolean("Shade the result smooth.", False),
    },
    ["name", "voxel_size"],
    slow=True,
    family="modifiers",
    intents=("remesh a mesh into even voxels", "voxel remesh to merge overlapping shells into one", "rebuild a messy boolean result as a clean surface"),
    nearest=(("clean_mesh", "to fix a mesh without rebuilding it"), ("decimate", "to reduce the triangle count")),
)
def remesh(ctx, args):
    obj = get_mesh_object(args["name"])
    voxel_remesh(ctx, obj, args["voxel_size"], args["adaptivity"], args["smooth_shading"])
    report = mesh_report(obj.data)
    return {
        "name": obj.name,
        "voxel_size": args["voxel_size"],
        "mesh": mesh_counts(obj.data),
        "manifold": report["manifold"],
        "volume": rounded(report["volume"], 9) if report["volume"] is not None else None,
        "shells": shell_count(obj.data),
        "modifiers": len(obj.modifiers),
    }
