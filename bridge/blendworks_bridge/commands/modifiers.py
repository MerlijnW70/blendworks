import bmesh
import bpy

from ..errors import bad_args, failed, not_found
from ..limits import MAX_MESH_VERTICES
from ..meshdata import MeshData
from ..modifier_specs import SPECS, configure, kind_schemas
from ..registry import command
from ..schema import array, boolean, integer, length, names, number, string, vector3
from ..topology import describe_problems, mesh_report
from ..util import check_vertex_cap, get_mesh_object, get_object, mesh_counts
from .clean import clean_object

OBJECT = string("Mesh object.")
APPLY = boolean("Apply the modifier to the mesh now instead of keeping it live.", False)


def add_modifier(ctx, obj, kind, settings, apply):
    modifier = obj.modifiers.new(name=kind.title(), type=kind)
    for key, value in settings.items():
        setattr(modifier, key, value)
    return finish_modifier(ctx, obj, modifier, kind, apply)


def finish_modifier(ctx, obj, modifier, kind, apply):
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
        replace_geometry(obj, result)
    finally:
        bpy.data.meshes.remove(result)
    for name in names:
        obj.modifiers.remove(obj.modifiers[name])


def replace_geometry(obj, source):
    bm = bmesh.new()
    try:
        bm.from_mesh(source)
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.materials.clear()
    for material in source.materials:
        obj.data.materials.append(material)
    drop_unused_empty_slots(obj.data)
    obj.data.update()


def drop_unused_empty_slots(mesh):
    used = {polygon.material_index for polygon in mesh.polygons}
    while len(mesh.materials) > 0 and mesh.materials[len(mesh.materials) - 1] is None and len(mesh.materials) - 1 not in used:
        mesh.materials.pop(index=len(mesh.materials) - 1)


@command(
    "apply_modifier",
    "Apply one modifier (or, without modifier, the whole stack in order) to the mesh.",
    {"name": OBJECT, "modifier": string("Modifier name, as listed by scene_info.")},
    ["name"],
    slow=True,
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


def evaluated_report(ctx, obj):
    evaluated = obj.evaluated_get(ctx.depsgraph())
    mesh = bpy.data.meshes.new_from_object(evaluated)
    try:
        return mesh_report(mesh)
    finally:
        bpy.data.meshes.remove(mesh)


def union_of_cutters(ctx, cutters):
    merged = MeshData()
    for cutter in cutters:
        mesh = bpy.data.meshes.new_from_object(cutter.evaluated_get(ctx.depsgraph()))
        try:
            merged.append(MeshData.from_mesh(mesh), cutter.matrix_world)
        finally:
            bpy.data.meshes.remove(mesh)
    mesh = bpy.data.meshes.new("Cutters")
    merged.to_mesh(mesh)
    stand_in = bpy.data.objects.new("Cutters", mesh)
    ctx.scene.collection.objects.link(stand_in)
    return stand_in


def remove_stand_in(stand_in):
    mesh = stand_in.data
    bpy.data.objects.remove(stand_in)
    bpy.data.meshes.remove(mesh)


def dispose_cutters(ctx, cutters, action):
    for cutter in cutters:
        if action == "hide":
            cutter.hide_set(True, view_layer=ctx.view_layer)
            cutter.hide_render = True
        elif action == "delete":
            data = cutter.data
            bpy.data.objects.remove(cutter)
            if data.users == 0:
                bpy.data.meshes.remove(data)


@command(
    "boolean",
    "Combine a mesh with one cutter or a list of cutters (unioned first, one exact operation): union, difference or intersect; cleans the result like clean_mesh, and can refuse a non-manifold result.",
    {
        "name": OBJECT,
        "cutter": string("The other mesh object."),
        "cutters": names("Several other mesh objects, joined by union first and applied in one operation with the exact solver.", 1, 1000),
        "operation": string("Boolean operation.", ["union", "difference", "intersect"], "difference"),
        "solver": string("exact is robust, float is fast, manifold needs closed meshes; cutters always use exact.", ["exact", "float", "manifold"], "exact"),
        "cutter_action": string("What to do with the cutters: hide them, keep them shown, or delete them (needs apply).", ["hide", "keep", "delete"], "hide"),
        "apply": boolean("Apply the boolean to the mesh now instead of keeping it live.", True),
        "manifold": boolean("Refuse and roll back when the result is not a closed manifold.", False),
        "clean": boolean("After applying, run clean_mesh: merge close vertices, dissolve degenerate faces, retriangulate slivers, drop collinear vertices, fix normals.", True),
        "merge_distance": length("Clean merge distance in metres.", 0.00001, 1.0),
    },
    ["name"],
    slow=True,
    destructive_when="cutter_action is delete",
)
def boolean_command(ctx, args):
    obj = get_mesh_object(args["name"])
    if ("cutter" in args) == ("cutters" in args):
        raise bad_args("give the cutters as exactly one of cutter or cutters")
    cutters = [get_mesh_object(name) for name in (args["cutters"] if "cutters" in args else [args["cutter"]])]
    if len({cutter.name for cutter in cutters}) != len(cutters):
        raise bad_args("a cutter is listed twice")
    if obj in cutters:
        raise bad_args("an object cannot cut itself")
    if args["cutter_action"] == "delete" and not args["apply"]:
        raise bad_args("cutter_action delete needs apply=true; a live boolean needs its cutter")
    multiple = "cutters" in args
    if multiple and (args["solver"] != "exact" or not args["apply"]):
        raise bad_args("cutters use the exact solver and need apply=true")
    settings = {"operation": args["operation"].upper(), "solver": args["solver"].upper()}
    stand_in = union_of_cutters(ctx, cutters) if multiple else None
    try:
        settings["object"] = stand_in if multiple else cutters[0]
        if multiple:
            settings["use_self"] = True
        result = add_modifier(ctx, obj, "BOOLEAN", settings, args["apply"])
    finally:
        if stand_in is not None:
            remove_stand_in(stand_in)
    cleaned = clean_object(obj, merge_distance=args["merge_distance"]) if args["apply"] and args["clean"] else None
    report = mesh_report(obj.data) if args["apply"] else evaluated_report(ctx, obj)
    if args["manifold"] and not report["manifold"]:
        raise failed(f"the boolean result is not manifold: {describe_problems(report)}")
    dispose_cutters(ctx, cutters, args["cutter_action"])
    result.update({"cutter": args["cutter_action"], "cutters": len(cutters), "manifold": report["manifold"], "volume": round(report["volume"], 9) if report["volume"] is not None else None})
    if args["apply"]:
        result["mesh"] = mesh_counts(obj.data)
    if cleaned is not None:
        result["cleaned"] = {key: value for key, value in cleaned.items() if key not in ("mesh", "manifold", "volume")}
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
    slow=True,
)
def decimate(ctx, args):
    obj = get_mesh_object(args["name"])
    return add_modifier(ctx, obj, "DECIMATE", {"decimate_type": "COLLAPSE", "ratio": args["ratio"]}, args["apply"])


KIND_PROPERTIES = kind_schemas()


@command(
    "add_modifier",
    "Add one typed modifier (displace, weld, screw, curve, simple_deform, wireframe, lattice, shrinkwrap, triangulate, weighted_normal, bevel, solidify): fill in exactly one of those fields.",
    {
        "name": OBJECT,
        "modifier_name": string("Name for the modifier; default the kind's name."),
        "apply": APPLY,
        **KIND_PROPERTIES,
    },
    ["name"],
)
def add_modifier_command(ctx, args):
    obj = get_mesh_object(args["name"])
    given = [kind for kind in SPECS if kind in args]
    if len(given) != 1:
        raise bad_args(f"give exactly one modifier field out of: {', '.join(SPECS)}")
    kind = given[0]
    modifier = obj.modifiers.new(name=args.get("modifier_name", kind.title()), type=SPECS[kind]["blender"])
    configure(obj, kind, args[kind], modifier)
    result = finish_modifier(ctx, obj, modifier, kind, args["apply"])
    result["kind"] = kind
    return result
