import bpy

from .. import limits
from ..materials_info import material_summary
from ..registry import command
from ..schema import names, string
from ..util import bounds_dict, get_object, get_objects, object_summary, scene_bounds, triangle_count, vec

PROTOCOL_VERSION = 1


@command("describe", "List every command with its argument schema and a one-line description.", mutates=False)
def describe(ctx, args):
    return {
        "protocol": PROTOCOL_VERSION,
        "blender": bpy.app.version_string,
        "units": {"length": "metres", "angle": "degrees"},
        "transport": "desktop" if ctx.desktop else "headless",
        "python": ctx.allow_python,
        "limits": {
            "mesh_from_data_vertices": limits.MAX_MESH_FROM_DATA_VERTICES,
            "mesh_vertices": limits.MAX_MESH_VERTICES,
            "render_resolution": limits.MAX_RENDER_RESOLUTION,
            "preview_samples": limits.MAX_PREVIEW_SAMPLES,
            "image_size": limits.MAX_IMAGE_SIZE,
            "bake_size": limits.MAX_BAKE_SIZE,
            "bake_seconds": limits.MAX_BAKE_SECONDS,
        },
        "commands": ctx.registry.describe(),
    }


@command(
    "scene_info",
    "Report objects, mesh counts (vertices, faces, triangles), materials, cameras, lights, bounds and units.",
    mutates=False,
)
def scene_info(ctx, args):
    scene = ctx.scene
    depsgraph = ctx.depsgraph()
    objects = [object_summary(obj, ctx.view_layer, depsgraph) for obj in sorted(scene.objects, key=lambda o: o.name)]
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    used_materials = sorted(
        {slot.material.name for obj in scene.objects for slot in obj.material_slots if slot.material is not None}
    )
    return {
        "objects": objects,
        "totals": {
            "objects": len(objects),
            "meshes": len(meshes),
            "vertices": sum(len(obj.data.vertices) for obj in meshes),
            "faces": sum(len(obj.data.polygons) for obj in meshes),
            "triangles": sum(triangle_count(obj.data) for obj in meshes),
        },
        "materials": [material_summary(material) for material in sorted(bpy.data.materials, key=lambda m: m.name)],
        "used_materials": used_materials,
        "cameras": sorted(obj.name for obj in scene.objects if obj.type == "CAMERA"),
        "active_camera": scene.camera.name if scene.camera else None,
        "lights": sorted(obj.name for obj in scene.objects if obj.type == "LIGHT"),
        "bounds": bounds_dict(scene_bounds(ctx)),
        "cursor": vec(scene.cursor.location),
        "units": {
            "system": scene.unit_settings.system.lower(),
            "length": scene.unit_settings.length_unit.lower(),
            "scale_length": scene.unit_settings.scale_length,
            "angle": "degrees",
        },
    }


@command("new_scene", "Clear the scene: remove every object and unused data, metric units in metres.")
def new_scene(ctx, args):
    removed = reset_scene(ctx.scene)
    return {"removed_objects": removed}


def reset_scene(scene):
    objects = list(scene.objects)
    count = len(objects)
    bpy.data.batch_remove(objects)
    purge_unused()
    scene.camera = None
    scene.cursor.location = (0.0, 0.0, 0.0)
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.unit_settings.scale_length = 1.0
    return count


def purge_unused():
    for name in ("meshes", "curves", "materials", "lights", "cameras", "images", "textures", "node_groups"):
        collection = getattr(bpy.data, name)
        unused = [block for block in collection if block.users - int(block.use_fake_user) == 0]
        if unused:
            bpy.data.batch_remove(unused)


@command(
    "select",
    "Select objects by name, replacing, adding to or removing from the selection; optionally set the active object.",
    {
        "names": names("Object names.", min_items=0),
        "mode": string("set replaces the selection, add and remove change it.", ["set", "add", "remove"], "set"),
        "active": string("Object to make active."),
    },
    ["names"],
)
def select(ctx, args):
    objects = get_objects(args["names"])
    active = get_object(args["active"]) if "active" in args else None
    layer = ctx.view_layer
    if args["mode"] == "set":
        for obj in layer.objects:
            obj.select_set(False, view_layer=layer)
    for obj in objects:
        obj.select_set(args["mode"] != "remove", view_layer=layer)
    if active is not None:
        layer.objects.active = active
    return {
        "selected": sorted(obj.name for obj in layer.objects if obj.select_get(view_layer=layer)),
        "active": layer.objects.active.name if layer.objects.active else None,
    }


@command(
    "delete",
    "Delete objects by name; their children keep their place in the world.",
    {"names": names("Objects to delete.")},
    ["names"],
)
def delete(ctx, args):
    objects = get_objects(args["names"])
    doomed = {obj.name for obj in objects}
    for obj in objects:
        for child in obj.children:
            if child.name not in doomed:
                matrix = child.matrix_world.copy()
                child.parent = None
                child.matrix_world = matrix
    data = [obj.data for obj in objects if obj.data is not None]
    bpy.data.batch_remove(objects)
    orphans = {block.as_pointer(): block for block in data if block.users == 0}
    if orphans:
        bpy.data.batch_remove(list(orphans.values()))
    return {"deleted": sorted(doomed)}
