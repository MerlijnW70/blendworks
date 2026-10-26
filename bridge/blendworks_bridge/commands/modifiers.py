import bmesh
import bpy

from ..errors import bad_args, failed, not_found
from ..limits import MAX_MESH_VERTICES
from ..registry import command
from ..schema import array, boolean, integer, length, number, string, vector3
from ..util import check_vertex_cap, get_mesh_object, get_object, mesh_counts

OBJECT = string("Mesh object.")
APPLY = boolean("Apply the modifier to the mesh now instead of keeping it live.", False)


def add_modifier(ctx, obj, kind, settings, apply):
    modifier = obj.modifiers.new(name=kind.title(), type=kind)
    for key, value in settings.items():
        setattr(modifier, key, value)
    name = modifier.name
    if apply:
        apply_modifiers(ctx, obj, [name])
        return {"name": obj.name, "modifier": name, "applied": True, "mesh": mesh_counts(obj.data)}
    evaluated = evaluated_counts(ctx, obj)
    if evaluated["faces"] == 0 and len(obj.data.polygons) > 0:
        raise failed(f"the {kind.lower()} modifier leaves {obj.name} with no faces")
    check_vertex_cap(evaluated["vertices"])
    return {"name": obj.name, "modifier": name, "applied": False, "mesh": mesh_counts(obj.data), "evaluated_mesh": evaluated}


def evaluated_counts(ctx, obj):
    evaluated = obj.evaluated_get(ctx.depsgraph())
    mesh = evaluated.to_mesh()
    try:
        return mesh_counts(mesh)
    finally:
        evaluated.to_mesh_clear()


def apply_modifiers(ctx, obj, names):
    if obj.data.users > 1:
        raise bad_args(f"{obj.name} shares its mesh with other objects; duplicate it without linking first")
    if obj.data.shape_keys is not None:
        raise bad_args(f"{obj.name} has shape keys; modifiers cannot be applied to it")
    shown = {modifier.name: modifier.show_viewport for modifier in obj.modifiers}
    for modifier in obj.modifiers:
        modifier.show_viewport = modifier.name in names
    try:
        evaluated = obj.evaluated_get(ctx.depsgraph())
        result = bpy.data.meshes.new_from_object(evaluated)
    finally:
        for modifier in obj.modifiers:
            modifier.show_viewport = shown[modifier.name]
    try:
        if len(result.polygons) == 0 and len(obj.data.polygons) > 0:
            raise failed(f"applying {', '.join(names)} leaves {obj.name} with no faces")
        check_vertex_cap(len(result.vertices))
        replace_geometry(ctx, obj, result)
    finally:
        bpy.data.meshes.remove(result)
    for name in names:
        obj.modifiers.remove(obj.modifiers[name])


def replace_geometry(ctx, obj, source):
    ctx.txn.touch_mesh(obj.data)
    bm = bmesh.new()
    try:
        bm.from_mesh(source)
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.materials.clear()
    for material in source.materials:
        obj.data.materials.append(material)
    obj.data.update()


@command(
    "apply_modifier",
    "Apply one modifier (or, without modifier, the whole stack in order) to the mesh.",
    {"name": OBJECT, "modifier": string("Modifier name, as listed by scene_info.")},
    ["name"],
)
def apply_modifier(ctx, args):
    obj = get_mesh_object(args["name"])
    if "modifier" in args:
        if args["modifier"] not in obj.modifiers:
            raise not_found(f"{obj.name} has no modifier named {args['modifier']}")
        names = [args["modifier"]]
    else:
        names = [modifier.name for modifier in obj.modifiers]
        if not names:
            raise bad_args(f"{obj.name} has no modifiers")
    apply_modifiers(ctx, obj, names)
    return {"name": obj.name, "applied": names, "mesh": mesh_counts(obj.data)}


@command(
    "boolean",
    "Combine a mesh with a cutter mesh: union, difference or intersect; fails if the result would be empty.",
    {
        "name": OBJECT,
        "cutter": string("The other mesh object."),
        "operation": string("Boolean operation.", ["union", "difference", "intersect"], "difference"),
        "solver": string("exact is robust, float is fast, manifold needs closed meshes.", ["exact", "float", "manifold"], "exact"),
        "cutter_action": string("What to do with the cutter: hide it, keep it shown, or delete it (needs apply).", ["hide", "keep", "delete"], "hide"),
        "apply": boolean("Apply the boolean to the mesh now instead of keeping it live.", True),
    },
    ["name", "cutter"],
)
def boolean_command(ctx, args):
    obj = get_mesh_object(args["name"])
    cutter = get_mesh_object(args["cutter"])
    if cutter == obj:
        raise bad_args("an object cannot cut itself")
    if args["cutter_action"] == "delete" and not args["apply"]:
        raise bad_args("cutter_action delete needs apply=true; a live boolean needs its cutter")
    settings = {"operation": args["operation"].upper(), "solver": args["solver"].upper(), "object": cutter}
    result = add_modifier(ctx, obj, "BOOLEAN", settings, args["apply"])
    if args["cutter_action"] == "hide":
        cutter.hide_set(True, view_layer=ctx.view_layer)
        cutter.hide_render = True
    elif args["cutter_action"] == "delete":
        data = cutter.data
        bpy.data.objects.remove(cutter)
        if data.users == 0:
            bpy.data.meshes.remove(data)
    result["cutter"] = args["cutter_action"]
    return result


@command(
    "mirror",
    "Mirror a mesh across its local axes (or another object's), merging the seam.",
    {
        "name": OBJECT,
        "axes": array({"type": "string", "enum": ["x", "y", "z"]}, "Axes to mirror across.", 1, 3, ["x"]),
        "mirror_object": string("Mirror across this object's origin and axes instead of the mesh's own."),
        "merge_distance": length("Merge seam vertices within this many metres.", 0.001, 10.0),
        "bisect": boolean("Cut away the geometry on the far side before mirroring.", False),
        "apply": APPLY,
    },
    ["name"],
)
def mirror(ctx, args):
    obj = get_mesh_object(args["name"])
    if len(set(args["axes"])) != len(args["axes"]):
        raise bad_args("each axis may be given once")
    axes = [axis in args["axes"] for axis in "xyz"]
    settings = {
        "use_axis": axes,
        "use_bisect_axis": [axis and args["bisect"] for axis in axes],
        "use_mirror_merge": True,
        "merge_threshold": args["merge_distance"],
    }
    if "mirror_object" in args:
        settings["mirror_object"] = get_object_for_modifier(args["mirror_object"], obj)
    return add_modifier(ctx, obj, "MIRROR", settings, args["apply"])


def get_object_for_modifier(name, obj):
    other = get_object(name)
    if other == obj:
        raise bad_args("an object cannot be its own mirror object")
    return other


@command(
    "array",
    "Repeat a mesh count times, each copy shifted by relative_offset (times its size) or a fixed offset in metres.",
    {
        "name": OBJECT,
        "count": integer("Total number of copies.", 2, 1000),
        "relative_offset": vector3("Shift per copy as a factor of the mesh's size.", [1.0, 0.0, 0.0], -1000.0, 1000.0),
        "offset": vector3("Shift per copy in metres; replaces relative_offset."),
        "merge": boolean("Merge touching vertices of neighbouring copies.", False),
        "apply": APPLY,
    },
    ["name", "count"],
)
def array_command(ctx, args):
    obj = get_mesh_object(args["name"])
    if len(obj.data.vertices) * args["count"] > MAX_MESH_VERTICES:
        raise failed(f"{args['count']} copies would exceed the cap of {MAX_MESH_VERTICES} vertices")
    settings = {"count": args["count"], "use_merge_vertices": args["merge"]}
    if "offset" in args:
        settings.update({"use_relative_offset": False, "use_constant_offset": True, "constant_offset_displace": args["offset"]})
    else:
        settings.update({"use_relative_offset": True, "use_constant_offset": False, "relative_offset_displace": args["relative_offset"]})
    return add_modifier(ctx, obj, "ARRAY", settings, args["apply"])


@command(
    "solidify",
    "Give a surface thickness in metres.",
    {
        "name": OBJECT,
        "thickness": number("Thickness in metres; not zero.", -1000.0, 1000.0),
        "offset": number("-1 grows inward, 1 outward, 0 both ways.", -1.0, 1.0, -1.0),
        "even": boolean("Keep the thickness even at corners.", True),
        "apply": APPLY,
    },
    ["name", "thickness"],
)
def solidify(ctx, args):
    obj = get_mesh_object(args["name"])
    if args["thickness"] == 0:
        raise bad_args("thickness must not be zero")
    settings = {"thickness": args["thickness"], "offset": args["offset"], "use_even_offset": args["even"]}
    return add_modifier(ctx, obj, "SOLIDIFY", settings, args["apply"])


@command(
    "decimate",
    "Reduce the face count to a ratio of the current count.",
    {
        "name": OBJECT,
        "ratio": number("Share of faces to keep, above 0 and up to 1.", None, 1.0, exclusive_minimum=0.0),
        "apply": APPLY,
    },
    ["name", "ratio"],
)
def decimate(ctx, args):
    obj = get_mesh_object(args["name"])
    return add_modifier(ctx, obj, "DECIMATE", {"decimate_type": "COLLAPSE", "ratio": args["ratio"]}, args["apply"])
