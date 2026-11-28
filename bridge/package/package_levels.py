"""LOD level checks and naming."""

import re

import bpy

from package_decimate import UNCHANGED, reduce_mesh
from package_error import geometric_error
from package_plan import level_plan, screen_error_pixels, switch_distance
from package_surface import mesh_surface, triangle_soup

LOD_SUFFIX = re.compile(r"_LOD\d+$")


class LodError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def bounds_of(surface):
    low, high = surface.bounds()
    return {"min": [float(value) for value in low], "max": [float(value) for value in high]}


def lod_name(base, level):
    return f"{base}_LOD{level}"


def check_sources(sources):
    if not sources:
        raise LodError("bad_args", "there is no mesh object to make levels of detail from")
    for obj in sources:
        if LOD_SUFFIX.search(obj.name):
            raise LodError("bad_args", f"{obj.name} already ends in _LOD<n>; give the source objects their plain names")
        if obj.data.shape_keys is not None:
            raise LodError("unsupported", f"{obj.name} has shape keys, which decimation cannot keep")
        if is_skinned(obj):
            raise LodError("unsupported", f"{obj.name} is skinned to an armature, which decimation cannot keep")


def is_skinned(obj):
    if any(modifier.type == "ARMATURE" for modifier in obj.modifiers):
        return True
    return bool(obj.vertex_groups) and obj.parent is not None and obj.parent.type == "ARMATURE"


def evaluated_copy(obj, depsgraph):
    return bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)


def share_key(obj):
    return obj.data.name if not obj.modifiers and obj.data.users > 1 else None


def copy_slots(source, created):
    for index, slot in enumerate(source.material_slots):
        if index >= len(created.material_slots):
            break
        if slot.link != created.material_slots[index].link:
            created.material_slots[index].link = slot.link
        created.material_slots[index].material = slot.material


def place_object(source, mesh, name):
    mesh.name = name
    created = bpy.data.objects.new(name, mesh)
    for collection in source.users_collection:
        collection.objects.link(created)
    copy_slots(source, created)
    created.matrix_basis = source.matrix_basis.copy()
    created.hide_render = source.hide_render
    created.hide_viewport = source.hide_viewport
    return created


def adopt_parents(pairs):
    lookup = {source: created for source, created in pairs}
    for source, created in pairs:
        parent = lookup.get(source.parent, source.parent)
        created.parent = parent
        created.matrix_parent_inverse = source.matrix_parent_inverse.copy()
        created.matrix_basis = source.matrix_basis.copy()


def refresh():
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return depsgraph


def reference_surfaces(sources, depsgraph):
    surfaces = {}
    for obj in sources:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            surfaces[obj] = mesh_surface(mesh, evaluated.matrix_world)
        finally:
            evaluated.to_mesh_clear()
    return surfaces


def reduce_level(sources, entry, depsgraph, surfaces):
    shared = {}
    pairs = []
    reductions = []
    for source in sources:
        key = share_key(source)
        cached = shared.get(key) if key is not None else None
        if cached is None:
            base = evaluated_copy(source, depsgraph)
            try:
                cached = reduce_mesh(base, source.matrix_world, entry["ratio"], entry["budget"], surfaces[source])
            finally:
                bpy.data.meshes.remove(base)
            if key is not None:
                shared[key] = cached
            reductions.append(cached)
            mesh = cached.mesh
        else:
            mesh = cached.mesh
        pairs.append((source, mesh))
    return pairs, reductions


def mode_counts(reductions):
    counts = {}
    for reduction in reductions:
        counts[reduction.mode] = counts.get(reduction.mode, 0) + 1
    return counts


def build_lods(sources, config, rename_source=True):
    check_sources(sources)
    plan = level_plan(config)
    sources = sorted(sources, key=lambda obj: obj.name)
    names = [obj.name for obj in sources]
    for name in names:
        for level in range(0 if rename_source else 1, len(plan) + 1):
            if bpy.data.objects.get(lod_name(name, level)) is not None:
                raise LodError("bad_args", f"{lod_name(name, level)} already exists")
    depsgraph = refresh()
    surfaces = reference_surfaces(sources, depsgraph)
    reference = triangle_soup(sources, depsgraph)
    source_triangles = len(reference.triangles)
    radius = reference.diagonal() / 2
    levels = [{"level": 0, "names": [lod_name(name, 0) for name in names], "triangles": source_triangles, "ratio": 1.0, "bounds": bounds_of(reference)}]
    created_levels = {0: list(sources)}
    previous = 0.0
    for entry in plan:
        pairs, reductions = reduce_level(sources, entry, depsgraph, surfaces)
        made = [place_object(source, mesh, lod_name(base, entry["level"])) for (source, mesh), base in zip(pairs, names)]
        adopt_parents([(source, created) for (source, _), created in zip(pairs, made)])
        depsgraph = refresh()
        soup = triangle_soup(made, depsgraph)
        error = geometric_error(reference, soup)
        distance = entry["distance"] if entry["distance"] is not None else switch_distance(error["hausdorff"], radius, previous)
        previous = distance
        pixels = screen_error_pixels(error["hausdorff"], distance)
        triangles = len(soup.triangles)
        levels.append(
            {
                "level": entry["level"],
                "names": [created.name for created in made],
                "triangles": triangles,
                "ratio": triangles / source_triangles if source_triangles else 1.0,
                "targetRatio": entry["ratio"],
                "distance": distance,
                "screenErrorPixels": pixels,
                "maxScreenErrorPixels": config.get("maxScreenError"),
                "error": error,
                "bounds": bounds_of(soup),
                "modes": mode_counts(reductions),
                "reduced": any(reduction.mode != UNCHANGED for reduction in reductions),
            }
        )
        created_levels[entry["level"]] = made
    if rename_source:
        for source, name in zip(sources, names):
            source.name = lod_name(name, 0)
            if source.data.users == 1:
                source.data.name = lod_name(name, 0)
    return {"levels": levels, "objects": created_levels, "radius": radius, "diagonal": reference.diagonal()}
