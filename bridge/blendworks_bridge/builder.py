"""Shared finishing step for shape builders."""

import bmesh
import bpy

from .errors import failed
from .limits import HALF_TURN
from .schema import CREATES, number, ref, string, vector3
from .shading import SHADING, apply_shading
from .topology import manifold_report
from .uvlayout import pack_islands
from .util import check_vertex_cap, link_object, mesh_counts, place, require_free_name, vec

SHAPE_FIELDS = {
    "name": ref(string("Object name; must be unused.", default="Shape"), "object", CREATES),
    "location": vector3("Object location in metres.", [0.0, 0.0, 0.0]),
    "rotation": vector3("Euler XYZ rotation in degrees.", [0.0, 0.0, 0.0]),
    "shading": string("smooth shades everything smooth, flat everything flat, auto smooths all but edges sharper than smooth_angle.", SHADING, "auto"),
    "smooth_angle": number("auto shading: edges sharper than this many degrees stay sharp.", 0.0, HALF_TURN, 35.0),
}


def finish_shape(ctx, data, args, pack=True):
    require_free_name(args["name"])
    check_vertex_cap(len(data.verts))
    if not data.faces:
        raise failed("the shape has no faces")
    if pack:
        pack_islands(data)
    mesh = bpy.data.meshes.new(args["name"])
    data.to_mesh(mesh)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        report = manifold_report(bm)
        if report["manifold"]:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        apply_shading(bm, args["shading"], args["smooth_angle"])
        report["volume"] = bm.calc_volume(signed=True) if report["manifold"] else None
        bm.normal_update()
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    obj = link_object(ctx, args["name"], mesh)
    place(obj, args["location"], args["rotation"])
    ctx.view_layer.update()
    return {
        "name": obj.name,
        "mesh": mesh_counts(mesh),
        "dimensions": vec(obj.dimensions),
        "manifold": report["manifold"],
        "volume": round(abs(report["volume"]), 9) if report["volume"] is not None else None,
    }
