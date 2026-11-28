"""Bark mesh: tubes skinned or voxel remeshed with density control."""

import math

import bpy
import numpy

from .errors import bad_args
from .limits import MAX_MESH_VERTICES
from .tree_axes import CUT, build_axes
from .tree_join import joined_tubes, skin_union, voxel_remesh
from .tree_rings import closed_tube
from .tree_tubes import Frame, Settings, is_base_root, predicted_triangles, radius_factors, root_directions
from .tree_voxel import smooth_junctions, transfer

VOXEL_SHARE = 0.3
VOXEL_DEFAULT_TRIANGLES = 400_000
LOD_TOLERANCE = 0.04
LOD_BUILDS = 5
VOXEL_POWER = 2.5
DENSITY_RANGE = (0.02, 8.0)
SEARCH_STEPS = 40


class Built:
    def __init__(self, mesh, frames, axes, twigs, settings, cut, extra):
        self.mesh = mesh
        self.frames = frames
        self.axes = axes
        self.twigs = twigs
        self.settings = settings
        self.cut = cut
        self.extra = extra

    def summary(self):
        return {
            "axes": len(self.axes),
            "cut_ends": sum(1 for axis in self.axes if axis.end == CUT),
            "nodes_kept": len({node for axis in self.axes for node in axis.own}),
            "min_radius": self.cut,
            **self.extra,
        }


def build_tubes(skeleton, args, density, cut):
    settings = Settings(args, skeleton, density)
    axes, twigs, _ = build_axes(skeleton, cut)
    directions = root_directions(skeleton, axes)
    has_roots = any(is_base_root(axis) for axis in axes)
    frames = []
    tubes = []
    for axis in axes:
        frame = Frame(skeleton, axis, settings)
        frames.append(frame)
        tubes.append(closed_tube(frame, radius_factors(frame, settings, skeleton, frames, directions), has_roots))
    return settings, axes, twigs, frames, tubes


def skin_mesh(ctx, skeleton, args, name, density, cut):
    settings, axes, twigs, frames, tubes = build_tubes(skeleton, args, density, cut)
    mesh = skin_union(ctx, tubes, name)
    return Built(mesh, frames, axes, twigs, settings, cut, {"density": round(density, 6)})


def smallest_radius(skeleton, cut):
    kept = skeleton.radii[skeleton.radii >= cut]
    return float(kept.min()) if len(kept) else float(skeleton.radii.max())


def voxel_mesh(ctx, skeleton, args, name, voxel, cut, target=VOXEL_DEFAULT_TRIANGLES):
    settings, axes, twigs, frames, tubes = build_tubes(skeleton, args, 1.0, cut)
    joined = joined_tubes(tubes, f"{name}_tubes")
    try:
        area = sum(polygon.area for polygon in joined.polygons)
        if voxel is None:
            voxel = max(VOXEL_SHARE * smallest_radius(skeleton, cut), math.sqrt(2.0 * area / target))
        coarser = voxel / VOXEL_SHARE
        if coarser > cut * (1.0 + 1e-9) and coarser > smallest_radius(skeleton, cut):
            bpy.data.meshes.remove(joined)
            joined = None
            return voxel_mesh(ctx, skeleton, args, name, voxel, coarser, target)
        expected = 2.0 * area / (voxel * voxel)
        if expected / 2.0 > MAX_MESH_VERTICES:
            raise bad_args(f"a voxel size of {voxel:.4g} m would make about {int(expected)} triangles; give a larger voxel_size, a larger min_radius or a lod budget")
        remeshed = voxel_remesh(ctx, joined, voxel, f"{name}_remeshed")
        try:
            mesh, crease = transfer(remeshed, joined)
        finally:
            bpy.data.meshes.remove(remeshed)
    finally:
        if joined is not None:
            bpy.data.meshes.remove(joined)
    smoothed = smooth_junctions(mesh, crease)
    return Built(mesh, frames, axes, twigs, settings, cut, {"voxel_size": round(voxel, 6), "smoothed_vertices": smoothed})


def triangle_count(mesh):
    sizes = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_total", sizes)
    return int((sizes - 2).sum())


def density_for(skeleton, args, cut, target):
    axes, _, _ = build_axes(skeleton, cut)
    low, high = DENSITY_RANGE
    if predicted_triangles(skeleton, axes, Settings(args, skeleton, low)) > target:
        return None
    if predicted_triangles(skeleton, axes, Settings(args, skeleton, high)) <= target:
        return high
    for _ in range(SEARCH_STEPS):
        middle = math.sqrt(low * high)
        if predicted_triangles(skeleton, axes, Settings(args, skeleton, middle)) > target:
            high = middle
        else:
            low = middle
    return low


def cut_for(skeleton, args, cut, target):
    radii = numpy.unique(skeleton.radii[skeleton.radii > cut])
    low, high = 0, len(radii) - 1
    if high < 0:
        return cut
    while low < high:
        middle = (low + high) // 2
        axes, _, _ = build_axes(skeleton, float(radii[middle]))
        if predicted_triangles(skeleton, axes, Settings(args, skeleton, DENSITY_RANGE[0])) > target:
            low = middle + 1
        else:
            high = middle
    return float(radii[low])


def skin_with_budget(ctx, skeleton, args, name, budget):
    cut = args["min_radius"]
    ratio = 1.0
    built = None
    trials = []
    for _ in range(LOD_BUILDS):
        target = budget / ratio
        density = density_for(skeleton, args, cut, target)
        if density is None:
            cut = cut_for(skeleton, args, cut, target)
            density = density_for(skeleton, args, cut, target) or DENSITY_RANGE[0]
        if built is not None:
            bpy.data.meshes.remove(built.mesh)
        built = skin_mesh(ctx, skeleton, args, name, density, cut)
        count = triangle_count(built.mesh)
        trials.append({"density": round(density, 6), "min_radius": cut, "triangles": count})
        predicted = predicted_triangles(skeleton, built.axes, built.settings)
        ratio = count / max(predicted, 1)
        if abs(count - budget) <= LOD_TOLERANCE * budget:
            break
    built.extra["lod_trials"] = trials
    return built


def voxel_with_budget(ctx, skeleton, args, name, budget):
    voxel = args.get("voxel_size")
    built = None
    trials = []
    for _ in range(LOD_BUILDS):
        if built is not None:
            bpy.data.meshes.remove(built.mesh)
        cut = args["min_radius"] if voxel is None else max(args["min_radius"], min(voxel / VOXEL_SHARE, float(skeleton.radii.max())))
        built = voxel_mesh(ctx, skeleton, args, name, voxel, cut, budget)
        count = triangle_count(built.mesh)
        voxel = built.extra["voxel_size"]
        trials.append({"voxel_size": voxel, "min_radius": built.cut, "triangles": count})
        if abs(count - budget) <= LOD_TOLERANCE * budget:
            break
        power = VOXEL_POWER
        if len(trials) > 1 and trials[-2]["voxel_size"] != voxel and trials[-2]["triangles"] != count:
            power = min(6.0, max(1.0, -math.log(count / trials[-2]["triangles"]) / math.log(voxel / trials[-2]["voxel_size"])))
        voxel *= (count / budget) ** (1.0 / power)
    built.extra["lod_trials"] = trials
    return built


def build_bark(ctx, skeleton, args, name):
    budget = args.get("lod")
    if args["junction"] == "voxel":
        if budget is not None:
            return voxel_with_budget(ctx, skeleton, args, name, budget)
        return voxel_mesh(ctx, skeleton, args, name, args.get("voxel_size"), args["min_radius"])
    if budget is not None:
        return skin_with_budget(ctx, skeleton, args, name, budget)
    return skin_mesh(ctx, skeleton, args, name, 1.0, args["min_radius"])
