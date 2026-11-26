import contextlib
import json
import os
import struct

import bpy
import numpy

from ..cover_gltf import add_instancing
from ..cover_nodes import CARD, CARDS_PROPERTY, KEY, MODIFIER_NAME, PICK, TINT, TRANSFORM, get_input, realized_vertices, set_input
from ..errors import bad_args, failed
from ..limits import MAX_MESH_VERTICES
from ..operators import only_selected, operator_context
from ..registry import command
from ..schema import boolean, integer, names, string
from ..util import get_object

MODES = ("instances", "realized")
INSTANCING = "EXT_mesh_gpu_instancing"
TINT_EXPORT = "_gc_tint"


def cover_objects(name):
    root = get_object(name)
    if root.type == "MESH" and root.modifiers.get(MODIFIER_NAME) is not None:
        return [root]
    found = sorted((child for child in root.children if child.type == "MESH" and child.modifiers.get(MODIFIER_NAME) is not None), key=lambda obj: obj.name)
    if not found:
        raise bad_args(f"{name} holds no ground cover; give the name used with ground_cover or one of its population objects")
    return found


def instance_count(obj):
    return len(obj.data.vertices)


def glb_json(path):
    with open(path, "rb") as handle:
        header = handle.read(20)
        length = struct.unpack("<I", header[12:16])[0]
        return json.loads(handle.read(length))


def instancing_summary(path):
    document = glb_json(path)
    accessors = document.get("accessors", [])
    nodes = [node for node in document.get("nodes", []) if INSTANCING in node.get("extensions", {})]
    counts = [accessors[node["extensions"][INSTANCING]["attributes"]["TRANSLATION"]]["count"] for node in nodes]
    colors = sum(1 for mesh in document.get("meshes", []) for primitive in mesh["primitives"] if "COLOR_0" in primitive["attributes"])
    return {"instanced_nodes": len(nodes), "instances": sum(counts), "extensions_used": document.get("extensionsUsed", []), "primitives_with_color": colors}


def point_values(obj, name, kind, width=1):
    values = numpy.empty(len(obj.data.vertices) * width, dtype=kind)
    obj.data.attributes[name].data.foreach_get("value", values)
    return values


def level_vertices(obj, level, cards):
    elements = list(get_input(obj.modifiers[MODIFIER_NAME], "Elements").objects)
    counts = [len(element.data.vertices) for element in elements]
    index = point_values(obj, CARD if cards and level > 0 else PICK, numpy.int32)
    return realized_vertices(counts, index, point_values(obj, KEY, numpy.float32), 0.5**level)


def require_realizable(covers, levels):
    for obj in covers:
        cards = has_cards(obj)
        for level in range(levels):
            vertices = level_vertices(obj, level, cards)
            if vertices > MAX_MESH_VERTICES:
                raise bad_args(f"{obj.name} LOD{level} would have {vertices} vertices, more than the {MAX_MESH_VERTICES} allowed; export instances, or lower the budget or the number of levels")


def realized_level(ctx, obj, level, cards):
    modifier = obj.modifiers[MODIFIER_NAME]
    saved = {key: get_input(modifier, key) for key in ("Realize", "Cards", "Share")}
    try:
        set_input(modifier, "Realize", True)
        set_input(modifier, "Cards", cards and level > 0)
        set_input(modifier, "Share", 0.5**level)
        obj.update_tag()
        depsgraph = ctx.depsgraph()
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
    finally:
        for key, value in saved.items():
            set_input(modifier, key, value)
        obj.update_tag()
    if len(mesh.vertices) > MAX_MESH_VERTICES:
        bpy.data.meshes.remove(mesh)
        raise failed(f"{obj.name} LOD{level} has more than {MAX_MESH_VERTICES} vertices")
    carried = mesh.attributes.get(TINT)
    if carried is not None:
        carried.name = TINT_EXPORT
    copy = bpy.data.objects.new(f"{obj.name}_LOD{level}", mesh)
    ctx.scene.collection.objects.link(copy)
    return copy


def has_cards(obj):
    return bool(obj.get(CARDS_PROPERTY, False))


def instance_groups(covers):
    groups, tints_by_element = {}, {}
    for obj in covers:
        mesh = obj.data
        count = len(mesh.vertices)
        picks = numpy.empty(count, dtype=numpy.int32)
        mesh.attributes[PICK].data.foreach_get("value", picks)
        values = numpy.empty(count * 16, dtype=numpy.float32)
        mesh.attributes[TRANSFORM].data.foreach_get("value", values)
        tints = point_values(obj, TINT, numpy.float32)
        matrices = numpy.array(obj.matrix_world) @ values.reshape(count, 4, 4).transpose(0, 2, 1).astype(numpy.float64)
        elements = sorted(get_input(obj.modifiers[MODIFIER_NAME], "Elements").objects, key=lambda element: element.name)
        for index, element in enumerate(elements):
            chosen = picks == index
            if chosen.any():
                groups[element.name] = matrices[chosen]
                tints_by_element[element.name] = tints[chosen]
    return groups, tints_by_element


@contextlib.contextmanager
def linked_for_export(ctx, objects):
    added = [obj for obj in objects if obj.name not in ctx.scene.collection.objects]
    for obj in added:
        ctx.scene.collection.objects.link(obj)
    try:
        yield
    finally:
        for obj in added:
            ctx.scene.collection.objects.unlink(obj)


def export_arguments(path, yup, wind):
    arguments = {
        "filepath": path,
        "export_format": "GLB",
        "use_selection": True,
        "export_apply": True,
        "export_attributes": True,
        "export_cameras": False,
        "export_lights": False,
        "export_yup": yup,
    }
    if wind:
        arguments["export_vertex_color"] = "ACTIVE"
    return arguments


@command(
    "ground_cover_export",
    "Write a ground cover of grass, flowers and litter to a .glb as GPU instances (one instanced node per element mesh), or as real meshes that halve the elements per level.",
    {
        "path": string("File path inside the workspace, relative to it, ending in .glb.", max_length=1024),
        "name": string("The ground_cover name (its empty) or one population object."),
        "mode": string("instances: EXT_mesh_gpu_instancing; realized: real meshes population_LOD0, population_LOD1 and so on.", list(MODES), "instances"),
        "levels": integer("realized: how many meshes per population; level n keeps 1 / 2^n of the elements, as cards from level 1 where the population has cards.", 1, 4, 2),
        "with_objects": names("Other objects to export along, such as the ground."),
        "wind": boolean("Write the active colour attribute (the wind colours) as COLOR_0.", True),
        "yup": boolean("Convert to glTF's Y-up axes.", True),
    },
    ["path", "name"],
    mutates=False,
    slow=True,
    writes_files=True,
    destructive_when="the file already exists",
    family="ground_cover",
    intents=("ground cover grass as gpu instances in a file", "meadow grass instanced for a game engine"),
    nearest=(("export", "for ordinary objects"), ("ground_cover", "to make the cover first")),
)
def ground_cover_export(ctx, args):
    if os.path.splitext(args["path"])[1].lower() != ".glb":
        raise bad_args("ground_cover_export writes a .glb file")
    path = ctx.workspace.output(args["path"], (".glb",))
    covers = cover_objects(args["name"])
    extra = [get_object(name) for name in args.get("with_objects", [])]
    counts = {obj.name: instance_count(obj) for obj in covers}
    temporary, groups, tints, written = [], {}, {}, {}
    try:
        if args["mode"] == "realized":
            require_realizable(covers, args["levels"])
            for obj in covers:
                cards = has_cards(obj)
                temporary.extend(realized_level(ctx, obj, level, cards) for level in range(args["levels"]))
            chosen = temporary + extra
        else:
            groups, tints = instance_groups(covers)
            chosen = [bpy.data.objects[name] for name in sorted(groups)] + extra
        with linked_for_export(ctx, chosen):
            ctx.view_layer.update()
            with only_selected(ctx.view_layer, chosen[0], chosen):
                with bpy.context.temp_override(**operator_context(chosen[0], chosen)):
                    bpy.ops.export_scene.gltf(**export_arguments(path, args["yup"], args["wind"]))
        levels = {obj.name: {"vertices": len(obj.data.vertices), "triangles": sum(len(polygon.vertices) - 2 for polygon in obj.data.polygons)} for obj in temporary}
        if groups and os.path.isfile(path):
            written = add_instancing(path, groups, args["yup"], tints)
    finally:
        for obj in temporary:
            mesh = obj.data
            bpy.data.objects.remove(obj)
            bpy.data.meshes.remove(mesh)
    if not os.path.isfile(path):
        raise failed("the glTF exporter wrote no file")
    result = {"path": ctx.workspace.relative(path), "bytes": os.path.getsize(path), "mode": args["mode"], "populations": counts, "count": sum(counts.values())}
    result.update(instancing_summary(path))
    if args["mode"] == "realized":
        result["levels"] = levels
    elif sum(written.values()) != result["count"]:
        raise failed(f"the glb holds {sum(written.values())} of {result['count']} instances")
    return result
