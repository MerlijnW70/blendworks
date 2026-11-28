"""Tree canopy: writes meshes with materials and reports leaf variation and area."""

import math

import bpy
import numpy
from mathutils import Matrix

from .copies import linked_copies
from .edge_order import canonical_edges
from .errors import bad_args
from .limits import MAX_MESH_VERTICES
from .tree_foliage import ATTRIBUTES, leaf_attributes, spray_matrix
from .tree_sprays import build_sprays
from .util import link_object, require_free_name


def write_mesh(name, batch, attributes):
    if len(batch.points) > MAX_MESH_VERTICES:
        raise bad_args(f"the foliage would have {len(batch.points)} vertices, more than the cap of {MAX_MESH_VERTICES}; raise clusters.spacing or lower clusters.leaves, forks or per_tip")
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(batch.points))
    mesh.vertices.foreach_set("co", batch.points.astype(numpy.float32).reshape(-1))
    count = len(batch.triangles)
    mesh.loops.add(3 * count)
    mesh.loops.foreach_set("vertex_index", batch.triangles.astype(numpy.int32).reshape(-1))
    mesh.polygons.add(count)
    mesh.polygons.foreach_set("loop_start", numpy.arange(0, 3 * count, 3, dtype=numpy.int32))
    mesh.update(calc_edges=True)
    canonical_edges(mesh)
    layer = mesh.uv_layers.new(name="UVMap")
    layer.data.foreach_set("uv", batch.uvs.astype(numpy.float32).reshape(-1))
    mesh.polygons.foreach_set("material_index", batch.materials.astype(numpy.int32))
    mesh.polygons.foreach_set("use_smooth", numpy.ones(count, dtype=bool))
    leafy = batch.leaf_of >= 0
    for key in ATTRIBUTES:
        values = numpy.zeros(count, dtype=numpy.float32)
        values[leafy] = attributes[key][batch.leaf_of[leafy]]
        mesh.attributes.new(key, "FLOAT", "FACE").data.foreach_set("value", values)
    mesh.validate(clean_customdata=False)
    return mesh


def with_materials(mesh, leaf_material, twig_material):
    for material in (leaf_material, twig_material):
        mesh.materials.append(material)


def realized(ctx, name, style, args, sprays, leaf_material, twig_material):
    require_free_name(name)
    matrices = numpy.array([spray_matrix(spray) for spray in sprays])
    batch, leaves = build_sprays(style, numpy.random.default_rng([args["seed"], 12]), matrices)
    outer = numpy.array([spray.outer for spray in sprays])
    attributes = leaf_attributes(numpy.random.default_rng([args["seed"], 13]), outer, leaves, args["variation"], args["shapes"])
    mesh = write_mesh(name, batch, attributes)
    with_materials(mesh, leaf_material, twig_material)
    return link_object(ctx, name, mesh), leaves, attributes, matrices


def linked(ctx, name, style, args, sprays, leaf_material, twig_material, world):
    require_free_name(name)
    rng = numpy.random.default_rng([args["seed"], 12])
    variants = []
    counts = []
    for index in range(args["variants"]):
        batch, leaves = build_sprays(style, rng, numpy.identity(4)[None])
        own = leaf_attributes(numpy.random.default_rng([args["seed"], 13, index]), numpy.full(1, 0.5), leaves, args["variation"], args["shapes"])
        mesh = write_mesh(f"{name}_cluster_{index}", batch, own)
        with_materials(mesh, leaf_material, twig_material)
        variants.append(mesh)
        counts.append(leaves.count)
    choice = rng.integers(0, len(variants), len(sprays))
    parent = link_object(ctx, name, None) if args["group"] else None
    tone = numpy.random.default_rng([args["seed"], 14]).uniform(-1.0, 1.0, (len(sprays), 3))
    variation = args["variation"]
    for variant, mesh in enumerate(variants):
        chosen = numpy.flatnonzero(choice == variant)
        if not len(chosen):
            continue
        matrices = [world @ Matrix(spray_matrix(sprays[index]).tolist()) for index in chosen]
        _, made = linked_copies(ctx, f"{name}_{variant}", mesh, matrices, False)
        for index, copy in zip(chosen, made):
            if parent is not None:
                copy.parent = parent
            copy["leaf_hue"] = float(variation["hue"] * tone[index, 0])
            copy["leaf_saturation"] = float(variation["saturation"] * tone[index, 1])
            copy["leaf_value"] = float(variation["value"] * (tone[index, 2] + 0.6 * (sprays[index].outer - 0.5)))
    return parent, int(sum(counts[variant] for variant in choice)), variants


def facing_spread(leaves, matrices):
    normals = numpy.einsum("nij,nj->ni", matrices[leaves.spray, :3, :3], leaves.axes[:, :, 2])
    normals /= numpy.maximum(numpy.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    mean = normals.mean(axis=0)
    mean /= max(float(numpy.linalg.norm(mean)), 1e-12)
    return math.degrees(float(numpy.arccos(numpy.clip(normals @ mean, -1.0, 1.0)).std()))


def variation_report(leaves, attributes, matrices):
    if not leaves.count:
        return {}
    report = {
        "size_cv": round(float(leaves.blade.std() / leaves.blade.mean()), 4),
        "curl_spread": round(math.degrees(float(leaves.curl.std())), 3),
        "fold_spread": round(math.degrees(float(leaves.fold.std())), 3),
        "facing_spread": round(facing_spread(leaves, matrices), 3),
        "shapes": int(len(numpy.unique(leaves.shape))),
    }
    for key in ("leaf_hue", "leaf_saturation", "leaf_value", "leaf_age", "leaf_damage"):
        report[key.removeprefix("leaf_") + "_spread"] = round(float(numpy.std(attributes[key])), 4)
    report["damaged_share"] = round(float(numpy.mean(attributes["leaf_damage"] > 0.0)), 4)
    return report


VOXEL = 0.5
CARD_COVER = {"tuft": 0.3, "needle": 0.9, "brush": 0.35}
DEFAULT_COVER = 0.6


def leaf_area_report(leaves, matrices, card_width, shape):
    scale = numpy.linalg.norm(matrices[leaves.spray, :3, 0], axis=1)
    blades = leaves.blade * scale
    area = float((blades * blades).sum() * card_width * CARD_COVER.get(shape, DEFAULT_COVER))
    origins = numpy.einsum("nij,nj->ni", matrices[leaves.spray, :3, :3], leaves.origin) + matrices[leaves.spray, :3, 3]
    cells = numpy.unique(numpy.floor(origins / VOXEL).astype(numpy.int64), axis=0)
    ground = numpy.unique(cells[:, :2], axis=0)
    volume = len(cells) * VOXEL**3
    footprint = len(ground) * VOXEL**2
    return {
        "leaf_area": round(area, 3),
        "crown_volume": round(volume, 3),
        "leaf_area_density": round(area / volume, 4) if volume else 0.0,
        "leaf_area_index": round(area / footprint, 4) if footprint else 0.0,
    }
