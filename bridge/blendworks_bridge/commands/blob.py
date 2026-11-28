"""The blob command: a smooth union of spheres built as metaballs and voxel remeshed into one closed mesh."""

import math

import bpy
import numpy

from .. import kit_limits
from ..edge_order import canonical_edges
from ..errors import bad_args, failed
from ..limits import LEAST_METABALL_LEVEL, MAX_MESH_VERTICES, MAX_METABALL_LEVEL
from ..registry import command
from ..schema import CREATES, array, length, number, obj, ref, string, vector3
from ..topology import mesh_report
from ..util import link_object, mesh_counts, require_free_name, rounded
from .remesh import MIN_VOXEL, shell_count, voxel_remesh

INFLUENCE = 2.0
MAX_CELLS = 50_000_000
MIN_RADIUS_VOXELS = 2.0
SURFACE_SHARE = 1.0 - 1.0 / (INFLUENCE * INFLUENCE)

POINT = obj(
    {
        "position": vector3("Centre of the sphere in metres."),
        "radius": length("Radius in metres of this sphere on its own; neighbours blend into it."),
    },
    ["position", "radius"],
)


def stiffness_for(threshold):
    return threshold / SURFACE_SHARE**3


def refuse_oversize(centres, radii, voxel_size):
    area = float(sum(4.0 * math.pi * radius * radius for radius in radii))
    if area / (voxel_size * voxel_size) > MAX_MESH_VERTICES:
        raise bad_args(f"a voxel size of {voxel_size} m would give about {int(area / voxel_size**2)} vertices; the cap is {MAX_MESH_VERTICES}. Use a larger voxel size")
    reach = radii * INFLUENCE
    size = (centres + reach[:, None]).max(axis=0) - (centres - reach[:, None]).min(axis=0)
    if float(numpy.prod(size / voxel_size)) > MAX_CELLS:
        raise bad_args(f"a voxel size of {voxel_size} m needs more than {MAX_CELLS} cells for this blob; use a larger voxel size")


def metaball_mesh(ctx, centres, radii, threshold, voxel_size):
    ball = bpy.data.metaballs.new("BlobField")
    ball.threshold = threshold
    ball.resolution = voxel_size
    ball.render_resolution = voxel_size
    for centre, radius in zip(centres, radii):
        element = ball.elements.new(type="BALL")
        element.co = tuple(centre)
        element.radius = float(radius) * INFLUENCE
        element.stiffness = stiffness_for(threshold)
    field = bpy.data.objects.new("BlobField", ball)
    ctx.scene.collection.objects.link(field)
    try:
        ctx.view_layer.update()
        mesh = bpy.data.meshes.new_from_object(field.evaluated_get(ctx.depsgraph()))
        canonical_edges(mesh)
        return mesh
    finally:
        bpy.data.objects.remove(field)
        bpy.data.metaballs.remove(ball)
        ctx.view_layer.update()


@command(
    "blob",
    "Build a smooth union of spheres as metaballs, converted and voxel remeshed into one closed mesh with no modifiers; an isolated sphere keeps exactly its radius and close spheres blend.",
    {
        "name": ref(string("Name of the new mesh object."), "object", CREATES),
        "points": array(POINT, "Spheres to blend.", 1, kit_limits.MAX_BLOB_POINTS),
        "threshold": number(f"Field level of the surface, {LEAST_METABALL_LEVEL:g} to {MAX_METABALL_LEVEL:g}: lower blends over a wider neck, higher gives tighter necks; a sphere on its own keeps its radius.", LEAST_METABALL_LEVEL, MAX_METABALL_LEVEL, 1.0),
        "voxel_size": length("Cell size in metres of the metaball surface and the remesh; every radius must be at least two voxels.", 0.05),
    },
    ["name", "points"],
    slow=True,
    family="shapes",
    intents=("blobby organic lump from overlapping spheres", "metaball union of spheres as one mesh", "smooth blended boulder base shape"),
    nearest=(("add_primitive", "for one plain sphere"), ("remesh", "to rebuild an existing mesh")),
)
def blob(ctx, args):
    require_free_name(args["name"])
    voxel = args["voxel_size"]
    if voxel < MIN_VOXEL:
        raise bad_args(f"voxel_size must be at least {MIN_VOXEL} m")
    centres = numpy.array([point["position"] for point in args["points"]], dtype=numpy.float64)
    radii = numpy.array([point["radius"] for point in args["points"]], dtype=numpy.float64)
    if float(radii.min()) < MIN_RADIUS_VOXELS * voxel:
        raise bad_args(f"every radius must be at least {MIN_RADIUS_VOXELS:g} voxels ({MIN_RADIUS_VOXELS * voxel:g} m); lower voxel_size")
    refuse_oversize(centres, radii, voxel)
    mesh = metaball_mesh(ctx, centres, radii, args["threshold"], voxel)
    if len(mesh.polygons) == 0:
        bpy.data.meshes.remove(mesh)
        raise failed("the metaballs produced no surface; lower voxel_size or raise the radii")
    mesh.name = args["name"]
    solid = link_object(ctx, args["name"], mesh)
    voxel_remesh(ctx, solid, voxel, 0.0, True)
    report = mesh_report(solid.data)
    if not report["manifold"]:
        raise failed("the blob did not remesh to a closed surface; try a different voxel_size")
    return {
        "name": solid.name,
        "mesh": mesh_counts(solid.data),
        "volume": rounded(report["volume"], 9),
        "shells": shell_count(solid.data),
        "modifiers": len(solid.modifiers),
    }
