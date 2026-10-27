import math

import bmesh
import bpy

from ..errors import bad_args
from ..operators import only_selected, operator_context
from ..registry import command
from ..schema import boolean, integer, length, names, number, string, vector3
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

PRIMITIVE_NAMES = {
    "cube": "Cube",
    "plane": "Plane",
    "cylinder": "Cylinder",
    "cone": "Cone",
    "sphere": "Sphere",
    "ico_sphere": "Icosphere",
    "torus": "Torus",
}


@command(
    "add_primitive",
    "Add a mesh primitive centred on location, with UVs; sizes in metres, see each field for the types it applies to.",
    {
        "type": string("Primitive type.", list(PRIMITIVE_FIELDS)),
        "name": string("Object name; must be unused. Default: the type's name."),
        "location": vector3("Centre in metres.", [0.0, 0.0, 0.0]),
        "rotation": vector3("Euler XYZ rotation in degrees.", [0.0, 0.0, 0.0]),
        "size": length("cube, plane: edge length (default 2)."),
        "radius": length("cylinder, cone (bottom), sphere, ico_sphere, torus (major): radius (default 1)."),
        "top_radius": number("cone: top radius in metres (default 0, a point).", 0.0, 10_000.0),
        "depth": length("cylinder, cone: height along Z (default 2)."),
        "minor_radius": length("torus: tube radius (default 0.25)."),
        "segments": integer("cylinder, cone, sphere, torus: segments around (default 32, torus 48).", 3, 256),
        "rings": integer("sphere: rings (default 16); torus: segments around the tube (default 12).", 3, 128),
        "subdivisions": integer("ico_sphere: subdivisions (default 2).", 1, 7),
    },
    ["type"],
    family="objects",
    intents=("add a cube, cylinder, cone, sphere, torus or plane", "basic mesh shape to start from", "ground plane"),
    nearest=(("lathe", "for turned profiles"), ("extrude_outline", "for flat plates")),
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
            bmesh.ops.create_uvsphere(
                bm, u_segments=options["segments"], v_segments=options["rings"], radius=options["radius"], calc_uvs=True
            )
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


@command(
    "duplicate",
    "Duplicate an object (its own mesh copy unless linked), optionally moved by an offset in metres.",
    {
        "name": string("Object to duplicate."),
        "new_name": string("Name for the copy; must be unused."),
        "linked": boolean("Share the mesh data instead of copying it.", False),
        "offset": vector3("Move the copy by this many metres.", [0.0, 0.0, 0.0]),
    },
    ["name"],
    family="objects",
    intents=("make one copy of an object", "clone an object with an offset"),
    nearest=(("instances", "for many copies on a pattern"), ("array", "for a row of copies inside one mesh")),
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


@command(
    "join",
    "Join mesh objects into one; the result keeps the target's name and origin.",
    {
        "names": names("Mesh objects to join (two or more).", min_items=2),
        "target": string("Object that receives the others. Default: the first name."),
    },
    ["names"],
    family="objects",
    intents=("combine several meshes into one object", "merge separate objects into one mesh object"),
    nearest=(("boolean", "for a watertight union that removes inner faces"),),
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


@command(
    "rename",
    "Rename an object (and its data when only it uses that data).",
    {"name": string("Current name."), "new_name": string("New name; must be unused.")},
    ["name", "new_name"],
    family="objects",
    intents=("change an object's name",),
    nearest=(("collection_create", "to group objects"),),
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
        "name": string("Child object."),
        "parent": string("New parent. Leave out to clear the parent."),
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
