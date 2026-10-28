import json
import os

import bpy

from ..blendfile import open_blend, save_atomically
from ..errors import bad_args, failed, forbidden
from ..gltf_extras import add_skeleton_extras
from ..exporting import check_options, forced_png, option_fields, resolved_tangents, run_exporter, shown, triangulated
from ..operators import only_selected, operator_context
from ..policy import REPLACES_FILE
from ..registry import command
from ..schema import boolean, names, string
from ..util import GEOMETRY_TYPES, get_objects
from ..workspace import IMPORT_EXTENSIONS
from .checkpoints import DISCARD, ensure_may_replace, opened
from .hierarchy import get_collection

EXPORT_FORMATS = {"glb": ".glb", "fbx": ".fbx", "obj": ".obj"}
EXPORTABLE_TYPES = GEOMETRY_TYPES + ("EMPTY",)


@command(
    "export",
    "Export the scene, a collection or named objects to a .glb, .fbx or .obj file in the workspace; options for modifiers, hidden objects, up axis, tangents, texture format and Draco.",
    {
        "path": string("File path inside the workspace, relative to it.", max_length=1024),
        "format": string("File format. Default: from the path's extension.", list(EXPORT_FORMATS)),
        "names": names("Objects to export. Default: every visible mesh, curve and text object."),
        "collection": string("Export the objects of this collection and its nested collections instead of the whole scene."),
        "ancestors": boolean("Also export the empties these objects are parented under, so the hierarchy survives.", True),
        **option_fields(),
    },
    ["path"],
    mutates=False,
    slow=True,
    writes_files=True,
    destructive_when="the file already exists",
    family="output",
    intents=("export a .glb, .fbx or .obj file", "deliver the asset for a game engine"),
    nearest=(("save_blend", "for a .blend file"),),
)
def export(ctx, args):
    extension = os.path.splitext(args["path"])[1].lower()
    file_format = args.get("format") or next((key for key, value in EXPORT_FORMATS.items() if value == extension), None)
    if file_format is None:
        raise forbidden(f"export writes only {', '.join(EXPORT_FORMATS.values())} files")
    if extension != EXPORT_FORMATS[file_format]:
        raise bad_args(f"a {file_format} export needs a {EXPORT_FORMATS[file_format]} path")
    check_options(file_format, args)
    path = ctx.workspace.output(args["path"], tuple(EXPORT_FORMATS.values()))
    objects = chosen_objects(ctx, args)
    if args["ancestors"]:
        objects = with_ancestor_empties(objects, ctx.scene)
    tangents = resolved_tangents(args, objects) if file_format == "glb" else None
    active = objects[0]
    with shown(objects, ctx.view_layer, args["include_hidden"]), forced_png(objects, args.get("image_format") == "png"), triangulated(objects, bool(tangents)):
        with only_selected(ctx.view_layer, active, objects):
            with bpy.context.temp_override(**operator_context(active, objects)):
                run_exporter(file_format, path, args, tangents)
    if not os.path.isfile(path):
        raise failed(f"the {file_format} exporter wrote no file")
    result = {
        "path": ctx.workspace.relative(path),
        "format": file_format,
        "bytes": os.path.getsize(path),
        "objects": sorted(obj.name for obj in objects),
        "options": {name: args[name] for name in ("apply_modifiers", "include_hidden", "yup")},
    }
    if file_format == "glb":
        skeletons = add_skeleton_extras(path, objects)
        if skeletons:
            result["skeletons"] = skeletons
        result["options"].update({"tangents": tangents, "image_format": args.get("image_format", "auto"), "draco": args.get("draco", False)})
    return result


def chosen_objects(ctx, args):
    if "names" in args and "collection" in args:
        raise bad_args("give names or collection, not both")
    if "names" in args:
        objects = get_objects(args["names"])
        hidden = [obj.name for obj in objects if obj.type in EXPORTABLE_TYPES and not obj.visible_get(view_layer=ctx.view_layer)]
        if hidden and not args["include_hidden"]:
            raise bad_args(f"{', '.join(hidden)} is hidden; set include_hidden to export hidden objects")
    else:
        pool = get_collection(ctx.scene, args["collection"]).all_objects if "collection" in args else ctx.scene.objects
        objects = [
            obj
            for obj in pool
            if obj.name in ctx.scene.objects and obj.type in GEOMETRY_TYPES and (args["include_hidden"] or obj.visible_get(view_layer=ctx.view_layer))
        ]
    objects = [obj for obj in objects if obj.type in EXPORTABLE_TYPES]
    if not objects:
        raise bad_args("there is nothing to export")
    return objects


def with_ancestor_empties(objects, scene):
    chosen = list(objects)
    seen = {obj.name for obj in chosen}
    for obj in objects:
        parent = obj.parent
        while parent is not None:
            if parent.type == "EMPTY" and parent.name not in seen and parent.name in scene.objects:
                seen.add(parent.name)
                chosen.append(parent)
            parent = parent.parent
    return chosen


@command(
    "save_blend",
    "Save a copy of the whole scene as a .blend file in the workspace.",
    {"path": string("File path inside the workspace, relative to it.", max_length=1024)},
    ["path"],
    mutates=False,
    slow=True,
    writes_files=True,
    destructive_when="the file already exists",
    family="files",
    intents=("save the scene as a .blend file",),
    nearest=(("checkpoint", "for a quick restore point"), ("export", "for .glb, .fbx or .obj")),
)
def save_blend(ctx, args):
    path = ctx.workspace.output(args["path"], (".blend",))
    return {"path": ctx.workspace.relative(path), "bytes": save_atomically(path)}


@command(
    "load_blend",
    "Open a .blend file from the workspace in place of the scene; its scripts and drivers never run.",
    {"path": string("File path inside the workspace, relative to it.", max_length=1024), "discard_unsaved": DISCARD},
    ["path"],
    slow=True,
    destructive=True,
    snapshot=REPLACES_FILE,
    family="files",
    intents=("open a .blend file in place of the scene",),
    nearest=(("import", "to add a .glb, .fbx or .obj model"),),
)
def load_blend(ctx, args):
    path = ctx.workspace.existing(args["path"], (".blend",))
    ensure_may_replace(ctx, args["discard_unsaved"])
    open_blend(path)
    return opened(ctx, path)


@command(
    "import",
    "Import a .glb, .gltf, .fbx or .obj file from the workspace into the scene.",
    {
        "path": string("File path inside the workspace, relative to it.", max_length=1024),
        "select": boolean("Leave only the imported objects selected.", True),
    },
    ["path"],
    slow=True,
    family="files",
    intents=("import a .glb, .gltf, .fbx or .obj model into the scene",),
    nearest=(("load_blend", "to open a .blend file"),),
)
def import_command(ctx, args):
    path = ctx.workspace.existing(args["path"], IMPORT_EXTENSIONS)
    extension = os.path.splitext(path)[1].lower()
    check_references(ctx.workspace, path, extension)
    before = {obj.as_pointer() for obj in bpy.data.objects}
    with bpy.context.temp_override(**operator_context(None, [])):
        if extension in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=path)
        elif extension == ".fbx":
            bpy.ops.import_scene.fbx(filepath=path, use_image_search=False)
        else:
            bpy.ops.wm.obj_import(filepath=path)
    imported = [obj for obj in ctx.scene.objects if obj.as_pointer() not in before]
    if not imported:
        raise failed(f"{args['path']} holds no objects to import")
    if not args["select"]:
        for obj in imported:
            obj.select_set(False, view_layer=ctx.view_layer)
    return {"path": ctx.workspace.relative(path), "objects": sorted(obj.name for obj in imported)}


def check_references(workspace, path, extension):
    folder = os.path.dirname(path)
    if extension == ".gltf":
        for reference in gltf_references(path):
            check_reference(workspace, folder, reference)
    elif extension == ".obj":
        for library in obj_libraries(path):
            library_path = check_reference(workspace, folder, library)
            if os.path.isfile(library_path):
                for texture in mtl_textures(library_path):
                    check_reference(workspace, os.path.dirname(library_path), texture)


def check_reference(workspace, folder, reference):
    if "://" in reference and not reference.startswith("file://"):
        raise forbidden(f"the file refers to {reference}, which is not a file in the workspace")
    reference = reference[len("file://"):] if reference.startswith("file://") else reference
    resolved = os.path.realpath(os.path.join(folder, reference))
    if not workspace.contains(resolved):
        raise forbidden(f"the file refers to {reference}, which is outside the workspace")
    return resolved


def gltf_references(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as error:
        raise failed(f"the .gltf file is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise failed("the .gltf file is not a glTF document")
    references = []
    for key in ("buffers", "images"):
        for entry in document.get(key) or []:
            uri = entry.get("uri") if isinstance(entry, dict) else None
            if isinstance(uri, str) and not uri.startswith("data:"):
                references.append(uri.replace("%20", " "))
    return references


def obj_libraries(path):
    return [name for words in statements(path, ("mtllib",)) for name in words]


def mtl_textures(path):
    return [name for words in statements(path, ("map_", "bump", "disp", "decal", "refl", "norm")) for name in words]


def statements(path, prefixes):
    found = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].lower().startswith(prefixes):
                rest = parts[1].strip()
                found.append([rest] + rest.split())
    return found
