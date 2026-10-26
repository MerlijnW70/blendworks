import math

import bpy
from mathutils import Matrix, Vector

from ..errors import bad_args
from ..registry import command
from ..schema import boolean, color, length, number, string, vector3
from ..util import degrees, get_object, link_object, place, require_free_name, vec

LIGHT_NAMES = {"point": "Point", "sun": "Sun", "spot": "Spot", "area": "Area"}


@command(
    "add_light",
    "Add a light; energy is watts (sun: strength in W/m²), rotation in degrees aims its -Z axis.",
    {
        "type": string("Light type.", list(LIGHT_NAMES)),
        "name": string("Object name; must be unused."),
        "location": vector3("Location in metres.", [4.0, -4.0, 6.0]),
        "rotation": vector3("Euler XYZ rotation in degrees.", [0.0, 0.0, 0.0]),
        "energy": number("Power in watts, or strength for a sun (default 1000, sun 3).", 0.0, 1_000_000.0),
        "color": color("Light colour, RGB from 0 to 1.", [1.0, 1.0, 1.0], allow_alpha=False),
        "size": length("Soft-shadow size in metres (area: edge length; spot and point: radius).", 0.25, 1000.0),
        "spot_angle": number("Spot cone angle in degrees (default 45).", 1.0, 180.0),
    },
    ["type"],
)
def add_light(ctx, args):
    kind = args["type"]
    if "spot_angle" in args and kind != "spot":
        raise bad_args("spot_angle applies only to spot lights")
    name = args.get("name", LIGHT_NAMES[kind])
    require_free_name(args.get("name"))
    light = bpy.data.lights.new(name, kind.upper())
    light.energy = args.get("energy", 3.0 if kind == "sun" else 1000.0)
    light.color = args["color"]
    if kind == "area":
        light.size = args["size"]
    elif kind == "sun":
        light.angle = math.radians(1.0)
    else:
        light.shadow_soft_size = args["size"]
    if kind == "spot":
        light.spot_size = math.radians(args.get("spot_angle", 45.0))
    obj = link_object(ctx, name, light)
    place(obj, args["location"], args["rotation"])
    return {"name": obj.name, "type": kind, "energy": light.energy, "location": vec(obj.location)}


@command(
    "add_camera",
    "Add a camera, optionally aimed at a point, and make it the scene's active camera.",
    {
        "name": string("Object name; must be unused."),
        "location": vector3("Location in metres.", [6.0, -6.0, 4.0]),
        "rotation": vector3("Euler XYZ rotation in degrees (ignored with target)."),
        "target": vector3("Aim the camera at this point in metres."),
        "lens": number("Focal length in millimetres (36 mm sensor).", 1.0, 5000.0, 50.0),
        "orthographic_scale": length("Use an orthographic camera this many metres wide."),
        "active": boolean("Make it the scene's active camera.", True),
    },
)
def add_camera(ctx, args):
    if "rotation" in args and "target" in args:
        raise bad_args("give rotation or target, not both")
    name = args.get("name", "Camera")
    require_free_name(args.get("name"))
    camera = bpy.data.cameras.new(name)
    camera.lens = args["lens"]
    camera.sensor_width = 36.0
    camera.clip_start = 0.01
    camera.clip_end = 10_000.0
    if "orthographic_scale" in args:
        camera.type = "ORTHO"
        camera.ortho_scale = args["orthographic_scale"]
    obj = link_object(ctx, name, camera)
    place(obj, args["location"], args.get("rotation"))
    if "target" in args:
        aim(ctx, obj, Vector(args["target"]))
    if args["active"]:
        ctx.scene.camera = obj
    return {"name": obj.name, "location": vec(obj.location), "rotation": degrees(obj.rotation_euler), "active": args["active"]}


def aim(ctx, obj, target, up_axis="Y"):
    ctx.view_layer.update()
    direction = target - obj.matrix_world.translation
    if direction.length < 1e-9:
        raise bad_args(f"{obj.name} is already at the target point")
    obj.rotation_mode = "XYZ"
    world_rotation = direction.to_track_quat("-Z", up_axis).to_matrix().to_4x4()
    location = obj.matrix_world.translation.copy()
    scale = obj.matrix_world.to_scale()
    obj.matrix_world = Matrix.Translation(location) @ world_rotation @ Matrix.Diagonal(scale.to_4d())


@command(
    "look_at",
    "Turn an object (usually a camera or light) so its -Z axis points at another object or a point.",
    {
        "name": string("Object to turn."),
        "target": string("Object to look at (its origin)."),
        "point": vector3("Point in metres to look at."),
    },
    ["name"],
)
def look_at(ctx, args):
    obj = get_object(args["name"])
    if ("target" in args) == ("point" in args):
        raise bad_args("give exactly one of target and point")
    if "target" in args:
        other = get_object(args["target"])
        if other == obj:
            raise bad_args("an object cannot look at itself")
        point = other.matrix_world.translation.copy()
    else:
        point = Vector(args["point"])
    aim(ctx, obj, point)
    return {"name": obj.name, "rotation": degrees(obj.rotation_euler), "looking_at": vec(point)}


@command(
    "set_world",
    "Set the world background: a uniform colour and strength that also lights the scene.",
    {
        "color": color("Background colour, linear RGB from 0 to 1.", allow_alpha=False),
        "strength": number("Background strength.", 0.0, 100.0),
    },
)
def set_world(ctx, args):
    if "color" not in args and "strength" not in args:
        raise bad_args("give color, strength or both")
    world = ctx.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        ctx.scene.world = world
    elif world.users > 1:
        world = world.copy()
        ctx.scene.world = world
    else:
        ctx.txn.touch_material(world, snapshot_world(world))
    background = world_background(world)
    if "color" in args:
        background.inputs["Color"].default_value = list(args["color"]) + [1.0]
        world.color = args["color"]
    if "strength" in args:
        background.inputs["Strength"].default_value = args["strength"]
    return {
        "world": world.name,
        "color": vec(background.inputs["Color"].default_value[:3]),
        "strength": rounded_strength(background),
    }


def rounded_strength(background):
    return round(float(background.inputs["Strength"].default_value), 6)


def world_background(world):
    tree = world.node_tree
    if tree is None:
        raise bad_args(f"world {world.name} has no node tree")
    for node in tree.nodes:
        if node.type == "BACKGROUND":
            return node
    background = tree.nodes.new("ShaderNodeBackground")
    output = next((node for node in tree.nodes if node.type == "OUTPUT_WORLD"), None)
    if output is None:
        output = tree.nodes.new("ShaderNodeOutputWorld")
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    return background


def snapshot_world(world):
    tree_values = None
    background = next((node for node in world.node_tree.nodes if node.type == "BACKGROUND"), None) if world.node_tree else None
    if background is not None:
        tree_values = (list(background.inputs["Color"].default_value), background.inputs["Strength"].default_value)
    color_value = list(world.color)

    def restore(target):
        target.color = color_value
        if tree_values is not None:
            node = next(node for node in target.node_tree.nodes if node.type == "BACKGROUND")
            node.inputs["Color"].default_value = tree_values[0]
            node.inputs["Strength"].default_value = tree_values[1]

    return restore
