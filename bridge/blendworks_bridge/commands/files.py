import json
import os

import bpy

from ..errors import bad_args, failed, forbidden
from ..operators import only_selected, operator_context
from ..registry import command
from ..schema import boolean, names, string
from ..util import GEOMETRY_TYPES, get_objects
from ..workspace import IMPORT_EXTENSIONS

EXPORT_FORMATS = {"glb": ".glb", "fbx": ".fbx", "obj": ".obj"}
EXPORTABLE_TYPES = GEOMETRY_TYPES + ("EMPTY",)


@command(
    "export",
    "Export the scene (or named objects) to a .glb, .fbx or .obj file in the workspace, modifiers applied.",
    {
        "path": string("File path inside the workspace, relative to it.", max_length=1024),
        "format": string("File format. Default: from the path's extension.", list(EXPORT_FORMATS)),
        "names": names("Objects to export. Default: every visible mesh, curve and text object."),
    },
    ["path"],
    mutates=False,
)
def export(ctx, args):
    extension = os.path.splitext(args["path"])[1].lower()
    file_format = args.get("format") or next((key for key, value in EXPORT_FORMATS.items() if value == extension), None)
    if file_format is None:
        raise forbidden(f"export writes only {', '.join(EXPORT_FORMATS.values())} files")
    if extension != EXPORT_FORMATS[file_format]:
        raise bad_args(f"a {file_format} export needs a {EXPORT_FORMATS[file_format]} path")
    path = ctx.workspace.output(args["path"], tuple(EXPORT_FORMATS.values()))
    if "names" in args:
        objects = get_objects(args["names"])
    else:
        objects = [obj for obj in ctx.scene.objects if obj.type in GEOMETRY_TYPES and obj.visible_get(view_layer=ctx.view_layer)]
    objects = [obj for obj in objects if obj.type in EXPORTABLE_TYPES]
    if not objects:
        raise bad_args("there is nothing to export")
    active = objects[0]
    with only_selected(ctx.view_layer, active, objects):
        with bpy.context.temp_override(**operator_context(active, objects)):
            run_exporter(file_format, path)
    if not os.path.isfile(path):
        raise failed(f"the {file_format} exporter wrote no file")
    return {
        "path": ctx.workspace.relative(path),
        "format": file_format,
        "bytes": os.path.getsize(path),
        "objects": sorted(obj.name for obj in objects),
    }


def run_exporter(file_format, path):
    if file_format == "glb":
        bpy.ops.export_scene.gltf(
            filepath=path,
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_cameras=False,
            export_lights=False,
            export_yup=True,
        )
    elif file_format == "fbx":
        bpy.ops.export_scene.fbx(
            filepath=path,
            use_selection=True,
            use_mesh_modifiers=True,
            object_types={"MESH", "EMPTY", "OTHER"},
            path_mode="STRIP",
        )
    else:
        bpy.ops.wm.obj_export(
            filepath=path,
            export_selected_objects=True,
            apply_modifiers=True,
            export_materials=True,
            path_mode="STRIP",
        )


@command(
    "save_blend",
    "Save a copy of the whole scene as a .blend file in the workspace.",
    {"path": string("File path inside the workspace, relative to it.", max_length=1024)},
    ["path"],
    mutates=False,
)
def save_blend(ctx, args):
    path = ctx.workspace.output(args["path"], (".blend",))
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, check_existing=False)
    if not os.path.isfile(path):
        raise failed("saving wrote no file")
    return {"path": ctx.workspace.relative(path), "bytes": os.path.getsize(path)}


@command(
    "import",
    "Import a .glb, .gltf, .fbx or .obj file from the workspace into the scene.",
    {
        "path": string("File path inside the workspace, relative to it.", max_length=1024),
        "select": boolean("Leave only the imported objects selected.", True),
    },
    ["path"],
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
