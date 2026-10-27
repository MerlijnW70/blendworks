import json
import os
import struct
from urllib.parse import unquote

import bpy

from judge_budget import check_budget
from judge_common import JudgeError, is_inside
from judge_gltf import glb_binary, precheck_gltf

FORMATS = {".glb": "glb", ".gltf": "gltf", ".fbx": "fbx", ".obj": "obj", ".blend": "blend"}
GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = 0x4E4F534A
EXTERNAL_DATA = ("images", "movieclips", "sounds", "volumes", "cache_files")
MEASURE_FRAME = 1


def detect_format(path):
    return FORMATS.get(os.path.splitext(path)[1].lower())


def empty_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    return bpy.context.scene


def gltf_document(path, file_format):
    with open(path, "rb") as handle:
        data = handle.read()
    binary = None
    if file_format == "glb":
        if len(data) < 20 or data[:4] != GLB_MAGIC:
            raise JudgeError("corrupt", "not a glTF binary: the header is missing")
        version, declared_length = struct.unpack_from("<II", data, 4)
        chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
        if version != 2 or declared_length > len(data) or chunk_type != GLB_JSON_CHUNK or 20 + chunk_length > len(data):
            raise JudgeError("corrupt", "not a glTF 2.0 binary: the header or JSON chunk is damaged")
        binary = glb_binary(data[: min(declared_length, len(data))])
        data = data[20 : 20 + chunk_length]
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise JudgeError("corrupt", "the glTF JSON cannot be parsed") from None
    if not isinstance(document, dict) or not isinstance(document.get("asset"), dict):
        raise JudgeError("corrupt", "the glTF JSON has no asset header")
    return document, binary


def gltf_referenced_files(path, document):
    directory = os.path.dirname(os.path.abspath(path))
    referenced = []
    for key in ("buffers", "images"):
        entries = document.get(key) or []
        if not isinstance(entries, list):
            raise JudgeError("corrupt", f"the glTF {key} entry is not a list")
        for entry in entries:
            uri = entry.get("uri") if isinstance(entry, dict) else None
            if not isinstance(uri, str) or uri.startswith("data:"):
                continue
            decoded = unquote(uri)
            if ":" in decoded or decoded.startswith(("/", "\\")):
                raise JudgeError("external_reference", f"the glTF refers to a file outside the asset folder: {uri[:120]}")
            target = os.path.join(directory, decoded)
            if not is_inside(target, directory):
                raise JudgeError("external_reference", f"the glTF refers to a file outside the asset folder: {uri[:120]}")
            if not os.path.isfile(target):
                raise JudgeError("missing_reference", f"the glTF refers to a missing file: {uri[:120]}")
            referenced.append(os.path.realpath(target))
    return sorted(set(referenced))


def run_importer(operator, **arguments):
    try:
        result = operator(**arguments)
    except MemoryError:
        raise
    except Exception as error:
        first_line = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        raise JudgeError("import_failed", f"the importer refused the file: {first_line[:300]}") from None
    if "FINISHED" not in result:
        raise JudgeError("import_failed", "the importer did not finish")


def load_blend_data(path):
    try:
        with bpy.data.libraries.load(path, link=False) as (source, target):
            if not source.scenes:
                raise JudgeError("no_scene", "the .blend file holds no scene")
            target.scenes = [source.scenes[0]]
    except JudgeError:
        raise
    except MemoryError:
        raise
    except Exception as error:
        raise JudgeError("corrupt", f"the .blend file cannot be read: {str(error).strip()[:300]}") from None
    loaded = target.scenes[0]
    if loaded is None:
        raise JudgeError("corrupt", "the .blend scene could not be loaded")
    unit_scale = loaded.unit_settings.scale_length
    if not 0 < unit_scale < float("inf"):
        raise JudgeError("corrupt", f"the .blend scene has an invalid unit scale {unit_scale}")
    judge_scene = bpy.context.scene
    for child in list(loaded.collection.children):
        judge_scene.collection.children.link(child)
    for obj in list(loaded.collection.objects):
        judge_scene.collection.objects.link(obj)
    bpy.data.scenes.remove(loaded)
    asset = os.path.normcase(os.path.realpath(path))
    for library in bpy.data.libraries:
        library_path = os.path.normcase(os.path.realpath(bpy.path.abspath(library.filepath)))
        if library_path != asset:
            raise JudgeError("external_reference", "the .blend links another library; deliver a self-contained file")
    return unit_scale


def apply_unit_scale(scene, unit_scale):
    if unit_scale == 1.0:
        return
    for obj in scene.objects:
        if obj.parent is None:
            obj.location = obj.location * unit_scale
            obj.delta_location = obj.delta_location * unit_scale
            obj.scale = obj.scale * unit_scale


def refuse_external_files(directory):
    refused = []
    for kind in EXTERNAL_DATA:
        collection = getattr(bpy.data, kind)
        for block in list(collection):
            if getattr(block, "packed_file", None) is not None or not getattr(block, "filepath", ""):
                continue
            if getattr(block, "source", "FILE") not in {"FILE", "SEQUENCE", "TILED", "MOVIE"}:
                continue
            target = bpy.path.abspath(block.filepath, library=block.library)
            if not is_inside(target, directory):
                refused.append(f"{kind}:{block.name}"[:120])
                collection.remove(block)
    return sorted(refused)


def expose_everything(scene):
    for collection in bpy.data.collections:
        collection.hide_viewport = False
        collection.hide_render = False

    def include(layer_collection):
        layer_collection.exclude = False
        layer_collection.hide_viewport = False
        for child in layer_collection.children:
            include(child)

    view_layer = scene.view_layers[0]
    include(view_layer.layer_collection)
    for obj in scene.objects:
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_set(False, view_layer=view_layer)
        for flag in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_shadow"):
            if hasattr(obj, flag):
                setattr(obj, flag, True)
        for modifier in obj.modifiers:
            modifier.show_viewport = modifier.show_render
            if modifier.type in {"SUBSURF", "MULTIRES"}:
                modifier.levels = modifier.render_levels


def load_asset(path, triangle_cap):
    if not os.path.isfile(path):
        raise JudgeError("missing", "the asset file does not exist")
    file_format = detect_format(path)
    if file_format is None:
        raise JudgeError("unsupported_format", "the asset must be .glb, .gltf, .fbx, .obj or .blend")
    scene = empty_scene()
    unit_scale = 1.0
    if file_format in {"glb", "gltf"}:
        document, binary = gltf_document(path, file_format)
        gltf_referenced_files(path, document)
        precheck_gltf(document, os.path.dirname(os.path.abspath(path)), binary, triangle_cap)
        run_importer(bpy.ops.import_scene.gltf, filepath=path, merge_vertices=True, import_pack_images=False)
    elif file_format == "fbx":
        run_importer(bpy.ops.import_scene.fbx, filepath=path, use_image_search=False, use_anim=False)
    elif file_format == "obj":
        run_importer(bpy.ops.wm.obj_import, filepath=path, validate_meshes=True)
    else:
        unit_scale = load_blend_data(path)
    refused = refuse_external_files(os.path.dirname(os.path.abspath(path)))
    expose_everything(scene)
    apply_unit_scale(scene, unit_scale)
    scene.frame_current = MEASURE_FRAME
    check_budget(scene, triangle_cap)
    return {"format": file_format, "unitScale": unit_scale, "externalFilesRefused": refused}
