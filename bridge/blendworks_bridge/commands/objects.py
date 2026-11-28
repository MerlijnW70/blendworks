"""Object commands: add_primitive, duplicate, join, rename and parent."""

import math
import re

import bmesh
import bpy

from ..errors import bad_args
from ..kit_limits import MAX_SEGMENTS
from ..limits import FEWEST_SIDES, ICO_SUBDIVISIONS, MAX_LENGTH, PAIR
from ..operators import only_selected, operator_context
from ..registry import command
from ..schema import CREATES, boolean, integer, length, names, number, ref, string, vector3
from ..util import check_vertex_cap, get_mesh_object, get_object, get_objects, link_object, mesh_counts, place
from ..util import require_free_name, vec

PRIMITIVE_FIELDS = {
    "cube": {"size": 2.0},
    "plane": {"size": 2.0},
    "cylinder": {"radius": 1.0, "depth": 2.0, "segments": 32},
    "cone": {"radius": 1.0, "top_radius": 0.0, "depth": 2.0, "segments": 32},
    "sphere": {"radius": 1.0, "segments": 32, "rings": 16},
    "ico_sphere": {"radius": 1.0, "subdivisions": 2},
    "torus": {"radius": 1.0, "minor_radius": 0.25, "segments": 48, "rings": 12},
}

SUFFIX = re.compile(r"\.\d{3,}$")


def unique_name(state, kind, base):
    """The name Blender gives a new datablock asked for base, in a plan: base when free, else base with the lowest
    free .001-style suffix."""
    taken = state.names[kind]
    if base not in taken:
        return base
    stem = SUFFIX.sub("", base)
    number = 1
    while f"{stem}.{number:03d}" in taken:
        number += 1
    return f"{stem}.{number:03d}"


PRIMITIVE_NAMES = {
    "cube": "Cube",
    "plane": "Plane",
    "cylinder": "Cylinder",
    "cone": "Cone",
    "sphere": "Sphere",
    "ico_sphere": "Icosphere",
    "torus": "Torus",
}


def plan_add_primitive(args, state):
    if "name" not in args:
        state.add("object", unique_name(state, "object", PRIMITIVE_NAMES[args["type"]]))


@command(
    "add_primitive",
    "Add a mesh primitive centred on location, with UVs; sizes in metres, see each field for the types it applies to.",
    {
        "type": string("Primitive type.", list(PRIMITIVE_FIELDS)),
        "name": ref(string("Object name; must be unused. Default: the type's name."), "object", CREATES),
        "location": vector3("Centre in metres.", [0.0, 0.0, 0.0]),
        "rotation": vector3("Euler XYZ rotation in degrees.", [0.0, 0.0, 0.0]),
        "size": length("cube, plane: edge length (default 2)."),
        "radius": length("cylinder, cone (bottom), sphere, ico_sphere, torus (major): radius (default 1)."),
        "top_radius": number("cone: top radius in metres (default 0, a point).", 0.0, MAX_LENGTH),
        "depth": length("cylinder, cone: height along Z (default 2)."),
        "minor_radius": length("torus: tube radius (default 0.25)."),
        "segments": integer("cylinder, cone, sphere, torus: segments around (default 32, torus 48).", FEWEST_SIDES, MAX_SEGMENTS),
        "rings": integer("sphere: rings (default 16); torus: segments around the tube (default 12).", FEWEST_SIDES, MAX_SEGMENTS),
        "subdivisions": integer("ico_sphere: subdivisions (default 2).", 1, ICO_SUBDIVISIONS),
    },
    ["type"],
    family="objects",
    intents=("add a cube, cylinder, cone, sphere, torus or plane", "basic mesh shape to start from", "ground plane"),
    nearest=(("lathe", "for turned profiles"), ("extrude_outline", "for flat plates")),
    plan=plan_add_primitive,
)
def add_primitive(ctx, args):
    kind = args["type"]
    allowed = PRIMITIVE_FIELDS[kind]
    common = {"type", "name", "location", "rotation"}
    stray = sorted(key for key in args if key not in common and key not in allowed)
    if stray:
        raise bad_args(f"{', '.join(stray)} does not apply to {kind}")
    options = {key: args.get(key, default) for key, default in allowed.items()}
    if kind == "torus" and options["minor_radius"] >= options["radius"]:
        raise bad_args("torus: minor_radius must be smaller than radius")
    require_free_name(args.get("name"))
    mesh = bpy.data.meshes.new(args.get("name", PRIMITIVE_NAMES[kind]))
    build_primitive(mesh, kind, options)
    obj = link_object(ctx, args.get("name", PRIMITIVE_NAMES[kind]), mesh)
    place(obj, args["location"], args["rotation"])
    return {"name": obj.name, "mesh": mesh_counts(mesh), "dimensions": vec(obj.dimensions)}


def build_primitive(mesh, kind, options):
    bm = bmesh.new()
    try:
        uv = bm.loops.layers.uv.new("UVMap")
        if kind == "cube":
            bmesh.ops.create_cube(bm, size=options["size"], calc_uvs=True)
        elif kind == "plane":
            bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=options["size"] / 2, calc_uvs=True)
        elif kind in ("cylinder", "cone"):
            bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=options["segments"],
                radius1=options["radius"],
                radius2=options.get("top_radius", options["radius"]),
                depth=options["depth"],
                calc_uvs=True,
            )
        elif kind == "sphere":
            build_uv_sphere(bm, uv, options)
        elif kind == "ico_sphere":
            bmesh.ops.create_icosphere(bm, subdivisions=options["subdivisions"], radius=options["radius"], calc_uvs=True)
        else:
            build_torus(bm, uv, options)
        if kind == "cone" and options["top_radius"] == 0:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
        check_vertex_cap(len(bm.verts))
        bm.to_mesh(mesh)
    finally:
        bm.free()


def build_uv_sphere(bm, uv, options):
    radius, around, rings = options["radius"], options["segments"], options["rings"]
    top = bm.verts.new((0.0, 0.0, radius))
    grid = []
    for ring in range(1, rings):
        theta = math.pi * ring / rings
        grid.append([bm.verts.new((radius * math.sin(theta) * math.cos(2 * math.pi * i / around), radius * math.sin(theta) * math.sin(2 * math.pi * i / around), radius * math.cos(theta))) for i in range(around)])
    bottom = bm.verts.new((0.0, 0.0, -radius))

    def face(corners, coords):
        made = bm.faces.new(corners)
        for loop, (u, v) in zip(made.loops, coords):
            loop[uv].uv = (u / around, 1.0 - v / rings)

    for i in range(around):
        following = (i + 1) % around
        face([top, grid[0][i], grid[0][following]], [(i + 0.5, 0), (i, 1), (i + 1, 1)])
        for ring in range(rings - 2):
            face([grid[ring][i], grid[ring + 1][i], grid[ring + 1][following], grid[ring][following]], [(i, ring + 1), (i, ring + 2), (i + 1, ring + 2), (i + 1, ring + 1)])
        face([bottom, grid[-1][following], grid[-1][i]], [(i + 0.5, rings), (i + 1, rings - 1), (i, rings - 1)])
    bm.normal_update()


def build_torus(bm, uv, options):
    major, minor = options["radius"], options["minor_radius"]
    around, tube = options["segments"], options["rings"]
    grid = []
    for i in range(around):
        theta = 2 * math.pi * i / around
        ring = []
        for j in range(tube):
            phi = 2 * math.pi * j / tube
            distance = major + minor * math.cos(phi)
            ring.append(bm.verts.new((distance * math.cos(theta), distance * math.sin(theta), minor * math.sin(phi))))
        grid.append(ring)
    for i in range(around):
        for j in range(tube):
            corners = [(i, j), ((i + 1) % around, j), ((i + 1) % around, (j + 1) % tube), (i, (j + 1) % tube)]
            face = bm.faces.new([grid[a][b] for a, b in corners])
            coords = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            for loop, (u, v) in zip(face.loops, coords):
                loop[uv].uv = (u / around, v / tube)
    bm.normal_update()


def plan_duplicate(args, state):
    if "new_name" not in args:
        state.add("object", unique_name(state, "object", args["name"]))


@command(
    "duplicate",
    "Duplicate an object (its own mesh copy unless linked), optionally moved by an offset in metres.",
    {
        "name": ref(string("Object to duplicate."), "object"),
        "new_name": ref(string("Name for the copy; must be unused."), "object", CREATES),
        "linked": boolean("Share the mesh data instead of copying it.", False),
        "offset": vector3("Move the copy by this many metres.", [0.0, 0.0, 0.0]),
    },
    ["name"],
    family="objects",
    intents=("make one copy of an object", "clone an object with an offset"),
    nearest=(("instances", "for many copies on a pattern"), ("array", "for a row of copies inside one mesh")),
    plan=plan_duplicate,
)
def duplicate(ctx, args):
    source = get_object(args["name"])
    require_free_name(args.get("new_name"))
    copy = source.copy()
    if source.data is not None and not args["linked"]:
        copy.data = source.data.copy()
    for collection in source.users_collection:
        collection.objects.link(copy)
    if "new_name" in args:
        copy.name = args["new_name"]
    copy.location = source.location + type(source.location)(args["offset"])
    return {"name": copy.name}


def plan_join(args, state):
    target = args.get("target", args["names"][0])
    if target not in args["names"]:
        return [{"argument": "args.target", "value": target, "message": "args.target must be one of names",
                 "instead": "add the target to names, or leave target out to use the first name"}]
    for name in args["names"]:
        if name != target:
            state.remove("object", name)


@command(
    "join",
    "Join mesh objects into one; the result keeps the target's name and origin.",
    {
        "names": ref(names("Mesh objects to join (two or more).", min_items=PAIR), "object"),
        "target": ref(string("Object that receives the others. Default: the first name."), "object"),
    },
    ["names"],
    family="objects",
    intents=("combine several meshes into one object", "merge separate objects into one mesh object"),
    nearest=(("boolean", "for a watertight union that removes inner faces"),),
    plan=plan_join,
)
def join(ctx, args):
    get_objects(args["names"])
    objects = [get_mesh_object(name) for name in args["names"]]
    target = get_mesh_object(args.get("target", args["names"][0]))
    if target.name not in args["names"]:
        raise bad_args("target must be one of names")
    check_vertex_cap(sum(len(obj.data.vertices) for obj in objects))
    with only_selected(ctx.view_layer, target, objects):
        with bpy.context.temp_override(**operator_context(target, objects)):
            bpy.ops.object.join()
    return {"name": target.name, "mesh": mesh_counts(target.data)}


def plan_rename(args, state):
    """new_name must be unused unless it is the object's own name, which leaves it as it is."""
    old, new = args["name"], args["new_name"]
    if new != old and new in state.names["object"]:
        return [{"argument": "args.new_name", "value": new,
                 "message": f"args.new_name must be an unused object name, but {new} exists already or an earlier call "
                            "makes it; choose another name or delete it first",
                 "instead": "another name, or delete first"}]
    state.rename("object", old, new)
    return []


@command(
    "rename",
    "Rename an object (and its data when only it uses that data).",
    {"name": ref(string("Current name."), "object"), "new_name": string("New name; must be unused, or the current name (which changes nothing).")},
    ["name", "new_name"],
    family="objects",
    intents=("change an object's name",),
    nearest=(("collection_create", "to group objects"),),
    plan=plan_rename,
)
def rename(ctx, args):
    obj = get_object(args["name"])
    if args["new_name"] != obj.name:
        require_free_name(args["new_name"])
    obj.name = args["new_name"]
    if obj.data is not None and obj.data.users == 1:
        obj.data.name = args["new_name"]
    return {"name": obj.name}


@command(
    "parent",
    "Parent an object to another, or clear its parent when parent is left out.",
    {
        "name": ref(string("Child object."), "object"),
        "parent": ref(string("New parent. Leave out to clear the parent."), "object"),
        "keep_transform": boolean("Keep the child where it is in the world.", True),
    },
    ["name"],
    family="hierarchy",
    intents=("make an object the child of another", "clear an object's parent", "attach parts so they move together"),
    nearest=(("add_empty", "for a new grouping node"),),
)
def parent(ctx, args):
    child = get_object(args["name"])
    new_parent = get_object(args["parent"]) if "parent" in args else None
    if new_parent is not None:
        ancestor = new_parent
        while ancestor is not None:
            if ancestor == child:
                raise bad_args(f"{new_parent.name} is {child.name} or one of its children")
            ancestor = ancestor.parent
    world = child.matrix_world.copy()
    child.parent = new_parent
    child.matrix_parent_inverse.identity()
    if args["keep_transform"]:
        child.matrix_world = world
    return {"name": child.name, "parent": new_parent.name if new_parent else None, "location": vec(child.location)}
