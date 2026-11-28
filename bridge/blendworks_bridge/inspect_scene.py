"""Scene inspection: totals, collections, matching objects and paged listings."""

import fnmatch
import json

import bpy

from .limits import MAX_LISTED_NAMES
from .materials_info import material_summary
from .util import bounds_dict, object_summary, scene_bounds, triangle_count, vec

DETAILS = ("summary", "objects", "full")


class Listing:
    def __init__(self):
        self.notes = []

    def names(self, label, names, hint):
        ordered = sorted(names)
        if len(ordered) <= MAX_LISTED_NAMES:
            return ordered
        self.notes.append(f"{label} lists {MAX_LISTED_NAMES} of {len(ordered)}; {hint}")
        return ordered[:MAX_LISTED_NAMES]


def totals(scene):
    objects = list(scene.objects)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    by_type = {}
    for obj in objects:
        key = obj.type.lower()
        by_type[key] = by_type.get(key, 0) + 1
    return {
        "objects": len(objects),
        "meshes": len(meshes),
        "vertices": sum(len(obj.data.vertices) for obj in meshes),
        "faces": sum(len(obj.data.polygons) for obj in meshes),
        "triangles": sum(triangle_count(obj.data) for obj in meshes),
        "materials": len(bpy.data.materials),
        "by_type": dict(sorted(by_type.items())),
    }


def collection_entries(scene, listing):
    holders = [scene.collection, *scene.collection.children_recursive]
    parents = {child.name: holder.name for holder in holders for child in holder.children}
    entries = [
        {"name": collection.name, "parent": parents[collection.name], "objects": len(collection.objects)}
        for collection in sorted(scene.collection.children_recursive, key=lambda item: item.name)
    ]
    if len(entries) > MAX_LISTED_NAMES:
        listing.notes.append(f"collections lists {MAX_LISTED_NAMES} of {len(entries)}; use the collections of each object for the rest")
    return entries[:MAX_LISTED_NAMES]


def matching(scene, pattern):
    ordered = sorted(scene.objects, key=lambda obj: obj.name)
    if pattern is None:
        return ordered
    return [obj for obj in ordered if fnmatch.fnmatchcase(obj.name, pattern)]


def page_of(matched, offset, limit, pattern, listing):
    chosen = matched[offset : offset + limit]
    end = offset + len(chosen)
    page = {
        "offset": offset,
        "limit": limit,
        "returned": len(chosen),
        "matched": len(matched),
        "next_offset": end if end < len(matched) else None,
    }
    if pattern is not None:
        page["names"] = pattern
    if page["next_offset"] is not None:
        listing.notes.append(
            f"showing objects {offset + 1} to {end} of {len(matched)}; call scene_info with offset {end} for the next "
            f"page, or narrow it with names (a glob such as \"Bolt*\")"
        )
    elif offset > 0 and not chosen:
        listing.notes.append(f"offset {offset} is past the {len(matched)} matching objects")
    return chosen, page


def json_property(value):
    for method in ("to_dict", "to_list"):
        if hasattr(value, method):
            value = getattr(value, method)()
            break
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return repr(value)


def full_entry(entry, obj):
    entry["data"] = obj.data.name if obj.data is not None else None
    entry["hide_render"] = obj.hide_render
    entry["custom_properties"] = {key: json_property(obj[key]) for key in sorted(obj.keys()) if not key.startswith("_")}
    if obj.type == "MESH":
        entry["vertex_groups"] = [group.name for group in obj.vertex_groups]
        keys = obj.data.shape_keys
        entry["shape_keys"] = [block.name for block in keys.key_blocks] if keys is not None else []
    return entry


def scene_report(ctx, detail, pattern, limit, offset, checkpoints):
    scene = ctx.scene
    listing = Listing()
    cache = {}
    hint = "they are all counted in totals"
    report = {"detail": detail, "totals": totals(scene)}
    if detail != "summary":
        depsgraph = ctx.depsgraph()
        chosen, page = page_of(matching(scene, pattern), offset, limit, pattern, listing)
        objects = [object_summary(obj, ctx.view_layer, depsgraph, cache) for obj in chosen]
        if detail == "full":
            objects = [full_entry(entry, obj) for entry, obj in zip(objects, chosen)]
            used = {slot.material for obj in chosen for slot in obj.material_slots if slot.material is not None}
            report["material_details"] = [material_summary(material) for material in sorted(used, key=lambda m: m.name)]
        report["objects"] = objects
        report["page"] = page
    used_names = {slot.material.name for obj in scene.objects for slot in obj.material_slots if slot.material is not None}
    report.update(
        {
            "materials": listing.names("materials", (material.name for material in bpy.data.materials), hint),
            "used_materials": listing.names("used_materials", used_names, hint),
            "collections": collection_entries(scene, listing),
            "cameras": listing.names("cameras", (obj.name for obj in scene.objects if obj.type == "CAMERA"), hint),
            "active_camera": scene.camera.name if scene.camera else None,
            "lights": listing.names("lights", (obj.name for obj in scene.objects if obj.type == "LIGHT"), hint),
            "bounds": bounds_dict(scene_bounds(ctx, cache=cache)),
            "cursor": vec(scene.cursor.location),
            "units": {
                "system": scene.unit_settings.system.lower(),
                "length": scene.unit_settings.length_unit.lower(),
                "scale_length": scene.unit_settings.scale_length,
                "angle": "degrees",
            },
            "checkpoints": checkpoints,
            "autosave": ctx.handler.autosave.status(),
        }
    )
    if listing.notes:
        report["notes"] = listing.notes
    return report
