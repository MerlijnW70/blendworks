"""Engraving engine: samples the surface, chooses a solver and applies the cutter."""

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

from .commands.clean import clean_object
from .cutmarks import mark_cutter, mark_cut_edges
from .commands.modifiers import add_modifier, remove_stand_in
from .errors import failed
from .slivers import SLIVER_AREA, SLIVER_ASPECT
from .topology import describe_problems, mesh_report
from .util import mesh_counts



class UvSampler:
    def __init__(self, obj):
        mesh = obj.data
        layer = mesh.uv_layers.active
        self.name = layer.name
        matrix = obj.matrix_world
        mesh.calc_loop_triangles()
        self.points = [matrix @ vertex.co for vertex in mesh.vertices]
        self.triangles = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
        self.uvs = [tuple(Vector(layer.uv[loop].vector).to_3d() for loop in triangle.loops) for triangle in mesh.loop_triangles]
        self.tree = BVHTree.FromPolygons(self.points, self.triangles, all_triangles=True)

    def nearest(self, point):
        found = self.tree.find_nearest(point)
        return found[2]

    def uv(self, point, triangle):
        a, b, c = (self.points[index] for index in self.triangles[triangle])
        normal = (b - a).cross(c - a)
        if normal.length == 0:
            return self.uvs[triangle][0].to_2d()
        flat = point - normal.normalized() * (point - a).dot(normal.normalized())
        return barycentric_transform(flat, a, b, c, *self.uvs[triangle]).to_2d()


def sampler_for(obj):
    return UvSampler(obj) if obj.data.uv_layers.active is not None and obj.data.polygons else None


def choose_solver(report):
    if report["manifold"]:
        return "MANIFOLD", "the mesh is a closed manifold, and the manifold solver always returns a closed manifold for closed inputs; it also needs no 32-bit rounding of an exact result"
    return "EXACT", f"the mesh is not a closed manifold ({describe_problems(report)}), which the manifold solver cannot take"


def apply_cutter(ctx, target, data, cutting, uv_name, solver):
    mesh = bpy.data.meshes.new("blendworks_engrave_cutter")
    data.to_mesh(mesh, uv_name or "UVMap")
    mark_cutter(mesh)
    cutter = bpy.data.objects.new("blendworks_engrave_cutter", mesh)
    ctx.scene.collection.objects.link(cutter)
    try:
        settings = {"operation": "DIFFERENCE" if cutting else "UNION", "solver": solver, "object": cutter}
        if solver == "EXACT":
            settings["use_self"] = True
        add_modifier(ctx, target, "BOOLEAN", settings, True)
    finally:
        remove_stand_in(cutter)


def sort_edges(mesh):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.index_update()
        count = len(bm.verts)
        bm.edges.sort(key=lambda edge: min(edge.verts[0].index, edge.verts[1].index) * count + max(edge.verts[0].index, edge.verts[1].index))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()


def rounded_volume(report, other=None):
    if report["volume"] is None or (other is not None and other["volume"] is None):
        return None
    return round(report["volume"] - (other["volume"] if other is not None else 0.0), 12)


def cut(ctx, target, data, cutting, clean, what):
    before = mesh_report(target.data)
    solver, reason = choose_solver(before)
    uv_name = target.data.uv_layers.active.name if target.data.uv_layers.active is not None else None
    apply_cutter(ctx, target, data, cutting, uv_name, solver)
    sort_edges(target.data)
    sharp = mark_cut_edges(target)
    cleaned = clean_object(target, max_aspect=SLIVER_ASPECT) if clean else None
    after = mesh_report(target.data)
    if before["volume"] is not None and after["volume"] is not None and abs(after["volume"] - before["volume"]) <= 1e-12 * abs(before["volume"]):
        raise failed(f"{what} did not change {target.name}: the surface does not meet the mesh, so check its position")
    if before["manifold"] and not after["manifold"]:
        raise failed(f"{what} left the mesh open ({describe_problems(after)}); try a smaller depth, a larger tolerance or a surface that matches the mesh")
    result = {
        "name": target.name,
        "mode": "cut" if cutting else "emboss",
        "mesh": mesh_counts(target.data),
        "manifold": after["manifold"],
        "volume_before": rounded_volume(before),
        "volume_after": rounded_volume(after),
        "volume_change": rounded_volume(after, before),
        "solver": {"used": solver.lower(), "reason": reason},
        "sharp_edges": sharp,
    }
    if cleaned is not None:
        result["cleaned"] = {key: value for key, value in cleaned.items() if key not in ("mesh", "manifold", "volume", "quality")}
        result["quality"] = {**cleaned["quality"], "max_aspect": SLIVER_ASPECT, "min_area": SLIVER_AREA}
    return result
