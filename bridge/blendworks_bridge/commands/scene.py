import bpy

from .. import limits
from ..inspect_scene import DETAILS, scene_report
from ..registry import command
from ..schema import integer, names, string
from ..util import get_object, get_objects
from .checkpoints import list_checkpoints

PROTOCOL_VERSION = 2


@command(
    "describe",
    "List every command with its argument schema, metadata and a one-line description.",
    mutates=False,
    internal=True,
    family="scene",
    intents=("list every command and its arguments",),
    nearest=(("scene_info", "to see what is in the scene"),),
)
def describe(ctx, args):
    return {
        "protocol": PROTOCOL_VERSION,
        "blender": bpy.app.version_string,
        "units": {"length": "metres", "angle": "degrees"},
        "transport": "desktop" if ctx.desktop else "headless",
        "python": ctx.allow_python,
        "autosave": ctx.handler.autosave.status(),
        "limits": {
            "mesh_from_data_vertices": limits.MAX_MESH_FROM_DATA_VERTICES,
            "mesh_vertices": limits.MAX_MESH_VERTICES,
            "render_resolution": limits.MAX_RENDER_RESOLUTION,
            "preview_samples": limits.MAX_PREVIEW_SAMPLES,
            "image_size": limits.MAX_IMAGE_SIZE,
            "bake_size": limits.MAX_BAKE_SIZE,
            "bake_seconds": limits.MAX_BAKE_SECONDS,
            "scene_info_limit": limits.MAX_SCENE_INFO_LIMIT,
            "checkpoints": limits.MAX_CHECKPOINTS,
        },
        "commands": ctx.registry.describe(),
    }


@command(
    "scene_info",
    "Report totals, a page of objects (counts, bounds, materials), materials, cameras, lights, units and checkpoints.",
    {
        "detail": string("summary: totals only; objects: plus a page of objects; full: plus custom properties and materials.", DETAILS, "objects"),
        "names": string("Only objects whose name matches this glob, for example Bolt* or *_low."),
        "limit": integer("Objects per page.", 1, limits.MAX_SCENE_INFO_LIMIT, limits.DEFAULT_SCENE_INFO_LIMIT),
        "offset": integer("Objects to skip, for the next page.", 0, None, 0),
    },
    mutates=False,
    family="scene",
    intents=("how many objects, vertices and triangles", "object sizes, bounds, parents and collections", "list materials, cameras, lights and checkpoints", "find objects by name pattern"),
    nearest=(("mesh_query", "for single faces of one mesh"),),
)
def scene_info(ctx, args):
    return scene_report(ctx, args["detail"], args.get("names"), args["limit"], args["offset"], list_checkpoints(ctx.workspace))


@command(
    "new_scene",
    "Clear the scene: remove every object, collection and unused data, metric units in metres.",
    destructive=True,
    family="scene",
    intents=("clear the whole scene and start fresh", "empty scene in metres"),
    nearest=(("delete", "to remove only some objects"),),
)
def new_scene(ctx, args):
    removed = reset_scene(ctx.scene)
    return {"removed_objects": removed}


def reset_scene(scene):
    objects = list(scene.objects)
    count = len(objects)
    bpy.data.batch_remove(objects)
    for collection in list(scene.collection.children_recursive):
        bpy.data.collections.remove(collection)
    purge_unused()
    scene.camera = None
    scene.cursor.location = (0.0, 0.0, 0.0)
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.unit_settings.scale_length = 1.0
    return count


def purge_unused():
    for name in ("meshes", "curves", "materials", "lights", "cameras", "images", "textures", "node_groups", "collections"):
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
    family="scene",
    intents=("select objects by name", "set the active object", "add to or remove from the selection"),
    nearest=(("mesh_query", "to pick faces inside a mesh; face tools take selectors"),),
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
    destructive=True,
    family="scene",
    intents=("remove objects by name", "delete a helper or cutter object", "delete cameras, lights or meshes"),
    nearest=(("new_scene", "to clear everything"),),
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
