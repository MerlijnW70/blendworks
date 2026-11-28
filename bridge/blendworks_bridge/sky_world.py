"""Sky world nodes: build, store and place the sun lamp."""

import json
import math

import bpy
import numpy

from . import camera_exposure, sky_measure, sky_sun, weather_objects, world_background
from .errors import bad_args

MODELS = {"multiple_scattering": "MULTIPLE_SCATTERING", "single_scattering": "SINGLE_SCATTERING"}
SKY_SCALE = 1.0 / 32.0
LAMP_DEFAULT = "Sun"
DISC_NODE = "Sky Sun Disc"
CLEAR_NODE = "Sky Clear"
DISC_TERM = "Sky Disc Term"
BACKGROUND = "Sky Background"
CAMERA_RAY = "Sky Camera Ray"
COMPOSITE_INPUT = "Sky Composite Input"
CLOUD_GREY = 1.6


def node_settings(sky, settings):
    sky.sky_type = MODELS[settings["model"]]
    sky.sun_elevation = math.radians(settings["elevation"])
    sky.sun_rotation = math.radians(settings["azimuth"])
    sky.altitude = settings["altitude"]
    sky.air_density = settings["air"]
    sky.aerosol_density = settings["dust"]
    sky.ozone_density = settings["ozone"]
    sky.sun_size = math.radians(settings["sun_size"])
    sky.sun_intensity = settings["sun_intensity"]


def build(world, output, settings):
    """Sky nodes: the clear sky without its disc lights the scene; camera rays add the disc, dimmed by any cloud sheet."""
    tree = world.node_tree
    clear = tree.nodes.new("ShaderNodeTexSky")
    clear.name = CLEAR_NODE
    node_settings(clear, settings)
    clear.sun_disc = False
    clear.location = (-1400, 300)
    disc = tree.nodes.new("ShaderNodeTexSky")
    disc.name = DISC_NODE
    node_settings(disc, settings)
    disc.sun_disc = True
    disc.location = (-1400, 0)
    only_disc = tree.nodes.new("ShaderNodeMix")
    only_disc.data_type = "RGBA"
    only_disc.blend_type = "SUBTRACT"
    only_disc.inputs["Factor"].default_value = 1.0
    only_disc.location = (-1150, 100)
    tree.links.new(disc.outputs["Color"], only_disc.inputs[6])
    tree.links.new(clear.outputs["Color"], only_disc.inputs[7])
    path = tree.nodes.new("ShaderNodeLightPath")
    path.name = CAMERA_RAY
    path.location = (-1150, -200)
    term = tree.nodes.new("ShaderNodeMix")
    term.name = DISC_TERM
    term.data_type = "RGBA"
    term.blend_type = "MIX"
    term.location = (-900, 0)
    tree.links.new(path.outputs["Is Camera Ray"], term.inputs["Factor"])
    term.inputs[6].default_value = (0.0, 0.0, 0.0, 1.0)
    tree.links.new(only_disc.outputs[2], term.inputs[7])
    composite = tree.nodes.new("ShaderNodeMix")
    composite.name = COMPOSITE_INPUT
    composite.data_type = "RGBA"
    composite.blend_type = "ADD"
    composite.inputs["Factor"].default_value = 1.0
    composite.location = (-300, 100)
    tree.links.new(clear.outputs["Color"], composite.inputs[6])
    tree.links.new(term.outputs[2], composite.inputs[7])
    background = tree.nodes.new("ShaderNodeBackground")
    background.name = BACKGROUND
    background.location = (0, 0)
    background.inputs["Strength"].default_value = SKY_SCALE * settings["strength"]
    tree.links.new(composite.outputs[2], background.inputs["Color"])
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    return clear


def named_nodes(world):
    tree = world.node_tree
    return {name: tree.nodes.get(name) for name in (CLEAR_NODE, DISC_NODE, DISC_TERM, BACKGROUND, COMPOSITE_INPUT)}


def stored(world):
    if world is None or world.get(world_background.SKY_PROPERTY) is None:
        return None
    return json.loads(world[world_background.SKY_PROPERTY])


def store(world, settings):
    world[world_background.SKY_PROPERTY] = json.dumps(settings, sort_keys=True)


def lamp_rotation(vector):
    from mathutils import Vector

    return Vector(vector).to_track_quat("Z", "Y").to_euler()


def place_lamp(ctx, name, settings, irradiance):
    obj = bpy.data.objects.get(name)
    created = obj is None
    if obj is None:
        light = bpy.data.lights.new(name, "SUN")
        obj = bpy.data.objects.new(name, light)
        weather_objects.link(ctx.scene, obj, "sun", hidden=False)
        obj.hide_select = False
    elif obj.type != "LIGHT" or obj.data.type != "SUN":
        raise bad_args(f"{name} exists and is not a sun lamp; give another lamp name")
    elif weather_objects.kind_of(obj) is None:
        weather_objects.tag(obj, "sun")
    colour, peak = sky_measure.lamp_colour(irradiance)
    light = obj.data
    light.color = colour
    light.energy = peak
    light.angle = math.radians(settings["sun_size"])
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = lamp_rotation(sky_sun.direction(settings["elevation"], settings["azimuth"]))
    obj.location = (0.0, 0.0, 10.0) if created else obj.location
    return obj, created


def exposure_for(illuminance):
    """The incident meter's exposure for the light on a horizontal card, in the sky's scene units."""
    return camera_exposure.incident_exposure(illuminance)


def illuminance(settings, cloud_factor=1.0, diffuse_factor=1.0):
    sun = sky_measure.luminance(settings["sun_rgb"]) * max(math.sin(math.radians(settings["elevation"])), 0.0)
    return sun * cloud_factor + sky_measure.luminance(settings["sky_irradiance"]) * diffuse_factor


def light_rgb(settings, cloud_settings=None):
    """Colour and parts of the light on a horizontal grey card: the direct sun through the cloud cover, the sky through it
    and the sun light the cover passes on as diffuse light."""
    sun_share = 1.0 if cloud_settings is None else cloud_settings["sun_share"]
    diffuse_share = 1.0 if cloud_settings is None else cloud_settings["diffuse_share"]
    sun = numpy.asarray(settings["sun_rgb"], dtype=numpy.float64) * max(math.sin(math.radians(settings["elevation"])), 0.0)
    sky = numpy.asarray(settings["sky_irradiance"], dtype=numpy.float64)
    parts = {"sun": sun * sun_share, "sky": sky * diffuse_share, "overcast": sun * (1.0 - sun_share) * diffuse_share}
    return sum(parts.values()), {key: sky_measure.luminance(value) for key, value in parts.items()}


def illuminant(scene):
    """The light that dominates the scene for the camera's white balance, or None without a procedural sky."""
    settings = stored(scene.world)
    if settings is None or "sun_rgb" not in settings:
        return None
    clouds = scene.world.get(world_background.CLOUDS_PROPERTY)
    rgb, parts = light_rgb(settings, json.loads(clouds) if clouds else None)
    return {"rgb": [float(value) for value in rgb], "source": max(parts, key=parts.get), "illuminance": sky_measure.luminance(rgb)}


def measured(settings):
    probe_world = bpy.data.worlds.new("blendworks sky settings")
    try:
        sky = probe_world.node_tree.nodes.new("ShaderNodeTexSky")
        node_settings(sky, settings)
        found = sky_measure.measure(sky, sky_sun.direction(settings["elevation"], settings["azimuth"]))
    finally:
        bpy.data.worlds.remove(probe_world)
    scale = SKY_SCALE * settings["strength"]
    result = {key: [round(float(value) * scale, 6) for value in found[key]] for key in found}
    result["dome_rows"] = sky_measure.PANORAMA_HEIGHT // 2
    return result


def settings_from(args):
    sun = sky_sun.resolve(args.get("sun", {}))
    if not -20.0 <= sun["elevation"] <= 90.0:
        raise bad_args(f"the sun is {sun['elevation']:.1f} degrees high; the sky covers -20 to 90")
    settings = {
        "model": args["model"],
        "elevation": round(sun["elevation"], 6),
        "azimuth": round(sun["azimuth"] % 360.0, 6),
        "altitude": args["altitude"],
        "air": args["air"],
        "dust": args["dust"],
        "ozone": args["ozone"],
        "sun_size": args["sun_size"],
        "sun_intensity": args["sun_intensity"],
        "strength": args["strength"],
    }
    return settings, sun


def directional_airlight(world, settings, directions):
    """Light the haze adds along each ray. Haze deep enough to hide what lies behind it shows the sky's own colour in
    that direction, the horizon's for rays below it, as aerial perspective does: distant land fades into the sky behind
    it and the sky itself is left as the sky model made it. A given airlight, a sky without a stored dome or another
    background keep the one colour."""
    constant = numpy.asarray(settings["airlight"], dtype=numpy.float32)
    if settings.get("airlight_source") != "sky" or world is None or not isinstance(world.get(world_background.SKY_PROPERTY), str):
        return constant
    sky = json.loads(world[world_background.SKY_PROPERTY])
    if "dome" not in sky:
        return constant
    colour = sky_measure.dome_radiance(sky["dome"], sky["dome_rows"], directions)
    clouds = world.get(world_background.CLOUDS_PROPERTY)
    if isinstance(clouds, str):
        colour = clouded(colour, float(json.loads(clouds).get("cover", 0.0)))
    return colour.astype(numpy.float32)


def clouded(colour, cover):
    """A sky colour greyed by its cloud cover, as cloud bases seen from below are grey."""
    grey = (colour @ numpy.array([0.2126, 0.7152, 0.0722]))[..., None] * CLOUD_GREY
    return colour * (1.0 - cover) + grey * cover
