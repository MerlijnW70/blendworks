import math
import os

import bpy
from mathutils import Matrix, Vector

from .. import camera_reach, world_background
from ..errors import bad_args, failed
from ..limits import (HALF_TURN, LEAST_CAMERA_MILLIMETRES, LEAST_SPOT_ANGLE, MAX_FOCAL_LENGTH, MAX_LIGHT_POWER,
                      MAX_WORLD_STRENGTH, PATH_LENGTH, TURN)
from ..registry import command
from ..schema import CREATES, EXISTS, boolean, color, length, number, ref, string, vector3
from ..util import degrees, get_object, link_object, place, require_free_name, vec

LIGHT_NAMES = {"point": "Point", "sun": "Sun", "spot": "Spot", "area": "Area"}


@command(
    "add_light",
    "Add a light; energy is watts (sun: strength in W/m²), rotation in degrees aims its -Z axis.",
    {
        "type": string("Light type.", list(LIGHT_NAMES)),
        "name": ref(string("Object name; must be unused."), "object", CREATES),
        "location": vector3("Location in metres.", [4.0, -4.0, 6.0]),
        "rotation": vector3("Euler XYZ rotation in degrees.", [0.0, 0.0, 0.0]),
        "energy": number("Power in watts, or strength for a sun (default 1000, sun 3).", 0.0, MAX_LIGHT_POWER),
        "color": color("Light colour, RGB from 0 to 1.", [1.0, 1.0, 1.0], allow_alpha=False),
        "size": length("Soft-shadow size in metres (area: edge length; spot and point: radius).", 0.25),
        "spot_angle": number("Spot cone angle in degrees (default 45).", LEAST_SPOT_ANGLE, HALF_TURN),
    },
    ["type"],
    plan=lambda args, state: state.add("object", args.get("name", LIGHT_NAMES[args["type"]])),
    family="lighting",
    intents=("add a sun, point, spot or area light", "lamp with power in watts"),
    nearest=(("set_world", "for background light"),),
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
        "name": ref(string("Object name; must be unused."), "object", CREATES),
        "location": vector3("Location in metres.", [6.0, -6.0, 4.0]),
        "rotation": vector3("Euler XYZ rotation in degrees (ignored with target)."),
        "target": vector3("Aim the camera at this point in metres."),
        "lens": number("Focal length in millimetres (36 mm sensor).", LEAST_CAMERA_MILLIMETRES, MAX_FOCAL_LENGTH, 50.0),
        "orthographic_scale": length("Use an orthographic camera this many metres wide."),
        "active": boolean("Make it the scene's active camera.", True),
    },
    plan=lambda args, state: state.add("object", args.get("name", "Camera")),
    family="lighting",
    intents=("add a camera and make it active", "orthographic or perspective camera"),
    nearest=(("render_preview", "for preview views without a camera"),),
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
    if "orthographic_scale" in args:
        camera.type = "ORTHO"
        camera.ortho_scale = args["orthographic_scale"]
    obj = link_object(ctx, name, camera)
    place(obj, args["location"], args.get("rotation"))
    if "target" in args:
        aim(ctx, obj, Vector(args["target"]))
    camera.clip_end = camera_reach.covering_clip(ctx.scene, ctx.view_layer, obj, camera_reach.LEAST_CLIP)
    if args["active"]:
        ctx.scene.camera = obj
    return {"name": obj.name, "location": vec(obj.location), "rotation": degrees(obj.rotation_euler), "active": args["active"],
            "clip_end": round(camera.clip_end, 3)}


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
        "name": ref(string("Object to turn."), "object", EXISTS),
        "target": ref(string("Object to look at (its origin)."), "object", EXISTS),
        "point": vector3("Point in metres to look at."),
    },
    ["name"],
    family="lighting",
    intents=("aim a camera or light at an object or point", "point something at a target"),
    nearest=(("transform", "for any other rotation"),),
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
    "Set the world background: a uniform colour and strength that also lights the scene; it replaces any image, sky or clouds.",
    {
        "color": color("Background colour, linear RGB from 0 to 1.", allow_alpha=False),
        "strength": number("Background strength.", 0.0, MAX_WORLD_STRENGTH),
    },
    family="lighting",
    intents=("uniform background colour that lights the scene", "black or grey world"),
    nearest=(("set_world_hdri", "for an HDRI image"), ("sky", "for a procedural sky")),
)
def set_world(ctx, args):
    if "color" not in args and "strength" not in args:
        raise bad_args("give color, strength or both")
    previous_color, previous_strength = uniform_values(ctx.scene.world)
    world, output, replaced = world_background.replace(ctx.scene)
    colour = args.get("color", previous_color)
    background = world_background.uniform(world, output, colour, args.get("strength", previous_strength))
    return {
        "world": world.name,
        "color": vec(background.inputs["Color"].default_value[:3]),
        "strength": rounded_strength(background),
        "replaced": replaced,
    }


def uniform_values(world):
    if world is None:
        return list(world_background.DEFAULT_COLOR), 1.0
    colour = list(world.color)
    if world_background.surface_kind(world) == "colour":
        background = next((node for node in world.node_tree.nodes if node.type == "BACKGROUND"), None)
        if background is not None:
            return list(background.inputs["Color"].default_value[:3]), float(background.inputs["Strength"].default_value)
    return colour, 1.0


def rounded_strength(background):
    return round(float(background.inputs["Strength"].default_value), 6)


HDRI_EXTENSIONS = (".hdr", ".exr")


@command(
    "set_world_hdri",
    "Light the scene with an equirectangular .hdr or .exr image from the workspace as the world environment.",
    {
        "path": string("Image path inside the workspace, relative to it.", max_length=PATH_LENGTH),
        "strength": number("Environment strength.", 0.0, MAX_WORLD_STRENGTH, 1.0),
        "rotation": number("Turn the environment about the Z axis, in degrees.", -TURN, TURN, 0.0),
    },
    ["path"],
    slow=True,
    plan=lambda args, state: state.add("image", os.path.basename(args["path"].replace("\\", "/"))),
    family="lighting",
    intents=("environment light from an .hdr or .exr file in the workspace",),
    nearest=(("library_apply", "for a Poly Haven HDRI"), ("set_world", "for a plain colour")),
)
def set_world_hdri(ctx, args):
    path = ctx.workspace.existing(args["path"], HDRI_EXTENSIONS)
    image = bpy.data.images.load(path, check_existing=False)
    image.name = os.path.basename(path)
    width, height = image.size[0], image.size[1]
    if width == 0 or height == 0:
        raise failed(f"{args['path']} is not a readable {os.path.splitext(path)[1]} image")
    world, output_node, replaced = world_background.replace(ctx.scene)
    tree = world.node_tree
    coordinates = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    environment = tree.nodes.new("ShaderNodeTexEnvironment")
    background = tree.nodes.new("ShaderNodeBackground")
    output = output_node
    environment.image = image
    environment.projection = "EQUIRECTANGULAR"
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(args["rotation"]))
    background.inputs["Strength"].default_value = args["strength"]
    tree.links.new(coordinates.outputs["Generated"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], environment.inputs["Vector"])
    tree.links.new(environment.outputs["Color"], background.inputs["Color"])
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    for node, x in ((coordinates, -900), (mapping, -700), (environment, -450), (background, -150), (output, 100)):
        node.location = (x, 0)
    return {
        "world": world.name,
        "image": image.name,
        "path": ctx.workspace.relative(path),
        "width": width,
        "height": height,
        "strength": rounded_strength(background),
        "rotation": args["rotation"],
        "replaced": replaced,
    }
