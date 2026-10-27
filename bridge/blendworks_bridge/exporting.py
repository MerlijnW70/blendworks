import contextlib

import bpy
import numpy

from .errors import bad_args
from .schema import boolean, integer, string

IMAGE_FORMATS = ("auto", "png", "jpeg")
GLB_ONLY = ("tangents", "image_format", "jpeg_quality", "draco", "draco_level")
DEFAULT_JPEG_QUALITY = 85
DEFAULT_DRACO_LEVEL = 6


def option_fields():
    return {
        "apply_modifiers": boolean("Bake the modifier stack into the exported meshes.", True),
        "include_hidden": boolean("Also export hidden objects: those named in names, or else every hidden mesh, curve and text object.", False),
        "yup": boolean("Write Y up, as glTF, FBX and OBJ readers expect; false keeps Blender's Z up.", True),
        "tangents": boolean("glb only: write tangent vectors. Default: on when an exported mesh uses a normal map."),
        "image_format": string("glb only: auto keeps JPEG sources and writes the rest as PNG; png and jpeg convert every texture. Default auto.", IMAGE_FORMATS),
        "jpeg_quality": integer(f"glb only, with image_format jpeg: quality from 1 to 100. Default {DEFAULT_JPEG_QUALITY}.", 1, 100),
        "draco": boolean("glb only: compress mesh geometry with Draco (KHR_draco_mesh_compression). Default false."),
        "draco_level": integer(f"glb only, with draco true: level from 0 (fast) to 10 (small). Default {DEFAULT_DRACO_LEVEL}.", 0, 10),
    }


def check_options(file_format, args):
    if file_format != "glb":
        given = [name for name in GLB_ONLY if name in args]
        if given:
            raise bad_args(f"{', '.join(given)} apply to glb exports only")
    if "jpeg_quality" in args and args.get("image_format") != "jpeg":
        raise bad_args("jpeg_quality applies with image_format jpeg")
    if "draco_level" in args and not args.get("draco", False):
        raise bad_args("draco_level applies with draco true")


def uses_normal_map(obj):
    for slot in obj.material_slots:
        tree = slot.material.node_tree if slot.material is not None else None
        if tree is not None and any(node.type == "NORMAL_MAP" and node.outputs["Normal"].is_linked for node in tree.nodes):
            return True
    return False


def has_polygons_over_four(mesh):
    if len(mesh.polygons) == 0:
        return False
    sizes = numpy.empty(len(mesh.polygons), dtype=numpy.int32)
    mesh.polygons.foreach_get("loop_total", sizes)
    return bool((sizes > 4).any())


def resolved_tangents(args, objects):
    meshes = [obj for obj in objects if obj.type == "MESH"]
    crowded = [obj.name for obj in meshes if has_polygons_over_four(obj.data)]
    if "tangents" in args:
        if args["tangents"] and crowded and not args["apply_modifiers"]:
            raise bad_args(f"tangents need triangles and quads, and {crowded[0]} has larger polygons; export with apply_modifiers so they are triangulated, or triangulate the mesh")
        return args["tangents"]
    return any(uses_normal_map(obj) for obj in meshes) and not (crowded and not args["apply_modifiers"])


@contextlib.contextmanager
def triangulated(objects, active):
    added = []
    if active:
        for obj in objects:
            if obj.type == "MESH" and has_polygons_over_four(obj.data):
                modifier = obj.modifiers.new("blendworks_triangulate", "TRIANGULATE")
                modifier.min_vertices = 5
                modifier.ngon_method = "BEAUTY"
                modifier.keep_custom_normals = True
                added.append((obj, modifier))
    try:
        yield
    finally:
        for obj, modifier in added:
            obj.modifiers.remove(modifier)


LOSSY_SIGNATURES = (bytes([0xFF, 0xD8, 0xFF]),)
LOSSY_SUFFIXES = (".jpg", ".jpeg", ".jpe", ".webp")


def keeps_lossy_source(image):
    if image.source not in ("FILE", "TILED"):
        return False
    if image.filepath_raw == "" and image.packed_file:
        data = image.packed_file.data
        return data[:3] in LOSSY_SIGNATURES or data[8:12] == b"WEBP"
    return image.filepath_raw.lower().endswith(LOSSY_SUFFIXES)


def texture_nodes(objects):
    found = []
    for obj in objects:
        for slot in obj.material_slots:
            tree = slot.material.node_tree if slot.material is not None else None
            if tree is not None:
                found.extend(node for node in tree.nodes if node.type == "TEX_IMAGE" and node.image is not None and keeps_lossy_source(node.image))
    return found


def lossless_copy(image):
    copy = bpy.data.images.new(f"{image.name}.png", image.size[0], image.size[1], alpha=image.channels == 4, float_buffer=image.is_float)
    copy.colorspace_settings.name = image.colorspace_settings.name
    pixels = numpy.empty(image.size[0] * image.size[1] * 4, dtype=numpy.float32)
    image.pixels.foreach_get(pixels)
    copy.pixels.foreach_set(pixels)
    copy.alpha_mode = image.alpha_mode
    return copy


@contextlib.contextmanager
def forced_png(objects, active):
    swapped = []
    copies = {}
    if active:
        for node in texture_nodes(objects):
            if node.image.name not in copies:
                copies[node.image.name] = lossless_copy(node.image)
            swapped.append((node, node.image))
            node.image = copies[node.image.name]
    try:
        yield
    finally:
        for node, image in swapped:
            node.image = image
        for copy in copies.values():
            bpy.data.images.remove(copy)


@contextlib.contextmanager
def shown(objects, view_layer, active):
    saved = []
    if active:
        for obj in objects:
            saved.append((obj, obj.hide_get(view_layer=view_layer), obj.hide_viewport))
            obj.hide_set(False, view_layer=view_layer)
            obj.hide_viewport = False
    try:
        yield
    finally:
        for obj, hidden, disabled in saved:
            obj.hide_set(hidden, view_layer=view_layer)
            obj.hide_viewport = disabled


def glb_arguments(path, args, tangents):
    arguments = {
        "filepath": path,
        "export_format": "GLB",
        "use_selection": True,
        "export_apply": args["apply_modifiers"],
        "export_cameras": False,
        "export_lights": False,
        "export_yup": args["yup"],
        "export_tangents": tangents,
        "export_image_format": "JPEG" if args.get("image_format") == "jpeg" else "AUTO",
        "export_draco_mesh_compression_enable": args.get("draco", False),
    }
    if args.get("image_format") == "jpeg":
        quality = args.get("jpeg_quality", DEFAULT_JPEG_QUALITY)
        arguments["export_jpeg_quality"] = quality
        arguments["export_image_quality"] = quality
    if args.get("draco", False):
        arguments["export_draco_mesh_compression_level"] = args.get("draco_level", DEFAULT_DRACO_LEVEL)
    return arguments


def fbx_arguments(path, args):
    return {
        "filepath": path,
        "use_selection": True,
        "use_mesh_modifiers": args["apply_modifiers"],
        "object_types": {"MESH", "EMPTY", "OTHER"},
        "path_mode": "STRIP",
        "axis_forward": "-Z" if args["yup"] else "Y",
        "axis_up": "Y" if args["yup"] else "Z",
    }


def obj_arguments(path, args):
    return {
        "filepath": path,
        "export_selected_objects": True,
        "apply_modifiers": args["apply_modifiers"],
        "export_materials": True,
        "path_mode": "STRIP",
        "forward_axis": "NEGATIVE_Z" if args["yup"] else "Y",
        "up_axis": "Y" if args["yup"] else "Z",
    }


def run_exporter(file_format, path, args, tangents):
    if file_format == "glb":
        bpy.ops.export_scene.gltf(**glb_arguments(path, args, tangents))
    elif file_format == "fbx":
        bpy.ops.export_scene.fbx(**fbx_arguments(path, args))
    else:
        bpy.ops.wm.obj_export(**obj_arguments(path, args))
