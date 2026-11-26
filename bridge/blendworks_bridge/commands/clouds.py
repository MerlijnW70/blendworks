import json
import math

import bpy

from .. import cloud_forms, cloud_genera, cloud_layers, cloud_sheet, cloud_volume, sky_world, weather_objects, world_background
from ..errors import bad_args
from ..registry import command
from ..schema import array, boolean, color, integer, length, number, obj, point2, string

MAX_LAYERS = 6
DEFAULT_BOUNCES = 24
RAIN_SHADE = 0.6
LAYER = obj(
    {
        "genus": string("Cloud genus.", list(cloud_genera.GENERA)),
        "coverage": number("Share of the layer (and of the sky overhead) covered, 0 to 1. Default: the genus's.", 0.0, 1.0),
        "base": length("Cloud base height above the ground in metres. Default: the genus's.", None, 20_000.0),
        "thickness": length("Thickness from base to top in metres. Default: the genus's.", None, 16_000.0),
        "density": number("Multiplies the genus's extinction per metre.", 0.01, 20.0, 1.0),
        "cell": length("Horizontal size of the cloud cells in metres. Default: the genus's.", None, 50_000.0),
        "seed": integer("Pattern seed. Default: the layer index.", 0, 2_147_483_647),
        "wind_direction": number("Compass direction the clouds drift towards, in degrees; they stretch along it.", 0.0, 360.0, 90.0),
        "drift": number("How far the pattern has drifted along the wind, in metres.", -1_000_000.0, 1_000_000.0, 0.0),
        "centre": point2("Cumulonimbus only: [x, y] of the storm cell in metres. Default: 14 km ahead of the active camera."),
        "brightness": number("Multiplies the sheet form's cloud radiance.", 0.0, 10.0, 1.0),
        "tint": color("Multiplies the sheet form's cloud colour, for cool storm light.", [1.0, 1.0, 1.0], allow_alpha=False),
    },
    ["genus"],
)
CLOUD_FIELDS = {
    "layers": array(LAYER, "Cloud layers, each one genus.", 1, MAX_LAYERS),
    "form": string("auto: sheet in previews and EEVEE, volumes in render_final; volume: volumes everywhere; sheet: no volumes.", list(cloud_layers.FORMS), "auto"),
    "radius": length("Radius in metres of the volume region around the centre; sheets continue to the horizon.", cloud_layers.DEFAULT_RADIUS, 60_000.0),
    "centre": point2("Observer [x, y] in metres the sheet is seen from. Default: the active camera, else the origin."),
    "visibility": length("Visibility in metres used to fade distant clouds into the horizon.", cloud_layers.SKY_VISIBILITY, 500_000.0),
    "bounces": integer("Volume bounces for the volume form (render setting).", 1, 128, DEFAULT_BOUNCES),
    "remove": boolean("Remove the clouds instead.", False),
}
KINDS = ("cloud_volume", "cloud_shadow")


@command(
    "clouds",
    "Clouds in the procedural sky by genus: cumulus to cumulonimbus, coverage, base, thickness, density, wind and seed; shadows on the ground.",
    CLOUD_FIELDS,
    slow=True,
    family="weather",
    intents=("add cumulus clouds to the sky", "overcast cloud layer", "cirrus streaks high up", "thunderstorm cloud with an anvil", "cloud shadows on the ground"),
    nearest=(("weather", "for whole weather presets with rain and light"), ("sky", "for the sky and sun first")),
)
def clouds(ctx, args):
    scene = ctx.scene
    if args["remove"]:
        if "layers" in args:
            raise bad_args("remove takes no layers")
        return {"removed": remove(scene)}
    if "layers" not in args:
        raise bad_args("layers is required")
    return build(ctx, args)


def remove(scene):
    world = scene.world
    sky = sky_world.stored(world)
    gone = weather_objects.remove(scene, KINDS)
    if sky is not None and world.get(world_background.CLOUDS_PROPERTY) is not None:
        rebuild_clear(scene, sky)
        return {"objects": gone, "layers": True}
    return {"objects": gone, "layers": False}


def rebuild_clear(scene, sky):
    world = scene.world
    output = world_background.clear_surface(world)
    sky_world.build(world, output, sky)
    sky_world.store(world, sky)


def build(ctx, args):
    scene = ctx.scene
    sky = cloud_layers.native_sky(scene.world)
    remove(scene)
    centre = cloud_layers.observer(scene, args.get("centre"))
    radius = args["radius"]
    layers = [cloud_layers.resolve(entry, index, scene, centre, radius) for index, entry in enumerate(args["layers"])]
    form = args["form"]
    for layer in layers:
        layer["volume"] = form != "sheet" and layer["volume"] and not under_deck(layer, layers)
    cloud_layers.add_light(layers, sky)
    sky["overcast_air"] = cloud_layers.overcast_air(layers, sky)
    cover = cloud_layers.cover_of(layers)
    world = scene.world
    rain = rain_spec(args.get("rain"), layers, sky)
    cloud_sheet.build(world, layers, sky, centre, cover, args["visibility"], form == "volume", rain)
    objects = add_objects(scene, layers, sky, centre, radius, form)
    world.cycles.sampling_method = "NONE"
    volumes = [layer for layer in layers if layer["volume"]]
    settings = {
        "form": form,
        "centre": centre,
        "radius": radius,
        "visibility": args["visibility"],
        "bounces": args["bounces"],
        "cover": round(cover, 6),
        "sun_share": round(cloud_layers.sun_share(layers), 6),
        "diffuse_share": round(cloud_layers.diffuse_share(layers), 6),
        "layers": [public(layer) for layer in layers],
        "objects": objects,
        "args": {key: value for key, value in args.items() if key != "remove"},
    }
    world[world_background.CLOUDS_PROPERTY] = json.dumps(settings, sort_keys=True)
    sky_world.store(world, {key: value for key, value in sky.items() if key != "overcast_air"})
    report = {key: value for key, value in settings.items() if key != "args"}
    report["cameras"] = raise_clip(scene, objects) if volumes else {}
    if volumes and form == "volume":
        report["render"] = cloud_forms.use_volumes(scene, args["bounces"])
    report["cost"] = cost(form, volumes)
    scale = sky_world.SKY_SCALE * sky["strength"]
    report["cloud_radiance"] = round(cloud_layers.base_radiance(layers, sky) * scale, 6)
    return report


def under_deck(layer, layers):
    """A closed sheet deck hides what is above it and leaves only diffuse light below it: such clouds render as sheets too."""
    for other in layers:
        if other is layer or other["volume"] or other["coverage"] < 0.9:
            continue
        if other["base"] < layer["base"]:
            return True
        if other["base"] > layer["base"] and layer["genus"] != "cumulonimbus":
            return True
    return False


def rain_spec(rain, layers, sky):
    if not rain:
        return None
    source = next((layer for genus in ("cumulonimbus", "nimbostratus", "stratus") for layer in layers if layer["genus"] == genus), None)
    if source is None:
        source = max(layers, key=lambda layer: layer["coverage"] * layer["thickness"])
    grey = cloud_layers.base_radiance(layers, sky) * RAIN_SHADE
    colour = [grey * value for value in (0.95, 0.98, 1.03)]
    return {"rate": rain["rate"], "source": source, "colour": colour}


def add_objects(scene, layers, sky, centre, radius, form):
    names = {"volumes": [], "shadows": []}
    for index, layer in enumerate(layers):
        name = f"Cloud {index} {layer['genus']}"
        if layer["volume"]:
            domain = cloud_volume.add_domain(scene, name, layer, centre, radius, visible=form == "volume")
            names["volumes"].append(domain.name)
            if layer["genus"] == "cumulonimbus":
                continue
            beyond = (centre, radius, 1.0 if form == "volume" else 0.0)
        else:
            beyond = None
        size = cloud_sheet.shadow_size(layer, sky["elevation"], radius)
        plane = cloud_sheet.shadow_plane(scene, name + " shadow", layer, centre, size, beyond)
        names["shadows"].append(plane.name)
    return names


def public(layer):
    keys = ("genus", "coverage", "base", "thickness", "density", "cell", "seed", "wind_direction", "drift", "extinction", "volume", "threshold")
    entry = {key: (round(layer[key], 6) if isinstance(layer[key], float) else layer[key]) for key in keys}
    if layer["genus"] == "cumulonimbus":
        entry["centre"] = [round(value, 3) for value in layer["centre"]]
        entry["anvil_radius"] = round(layer["anvil_radius"], 3)
        entry["tower_radius"] = round(layer["tower_radius"], 3)
    entry["optical_depth"] = round(layer["extinction"] * layer["density"] * layer["thickness"] * 0.75, 4)
    return entry


def raise_clip(scene, objects):
    reach = 0.0
    for name in objects["volumes"]:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        for corner in obj.bound_box:
            reach = max(reach, math.sqrt(sum(value * value for value in corner)))
    changed = {}
    for camera in (item for item in scene.objects if item.type == "CAMERA"):
        needed = reach + camera.matrix_world.translation.length
        if camera.data.clip_end < needed:
            camera.data.clip_end = needed
            changed[camera.name] = round(needed, 3)
    return changed


def cost(form, volumes):
    if not volumes or form == "sheet":
        return "sheet: clouds are part of the world shader and cast shadows through shadow-only planes; adds almost nothing to a render and works in EEVEE"
    text = "volume: path-traced cloud volumes with multiple scattering; several times slower than the sheet"
    if form == "auto":
        return text + "; only render_final uses them, previews and EEVEE see the sheet"
    return text
