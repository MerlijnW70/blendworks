import math

from . import cloud_forms, cloud_layers, sky_measure, sky_world, weather_continuum, weather_lightning, weather_objects, weather_rain, weather_wet
from .registry import COMMANDS
from .schema import validate

EXTRA_KINDS = ("rain_veil", "rain_streaks", "lightning", "flash")
HAZE_TINT = {"clear": [0.92, 0.96, 1.0], "cloudy": [0.97, 0.98, 1.0]}
HAZE_REACH = 10_000.0
BOLT_DISTANCE = 3000.0
COOL_TINT = (0.8, 0.88, 1.0)
DECK_GENERA = ("nimbostratus", "stratus", "cumulonimbus")


def call(ctx, name, args):
    entry = COMMANDS[name]
    return entry.run(ctx, validate(entry.schema, args))


def clear_extras(scene):
    weather_objects.remove(scene, EXTRA_KINDS)
    weather_wet.dry_scene(scene)


def remove(ctx):
    scene = ctx.scene
    gone = weather_objects.remove(scene, EXTRA_KINDS)
    dried = weather_wet.dry_scene(scene)
    clouds = call(ctx, "clouds", {"remove": True}) if cloud_forms.stored(scene) is not None else None
    haze = call(ctx, "atmosphere", {"remove": True})
    return {"objects": gone, "dried": dried, "clouds": clouds, "haze": haze["removed"]}


def sun_of(args, state):
    if "sun" in args:
        return args["sun"]
    return weather_continuum.sun_for(state["time_of_day"])


def sky(ctx, args, state):
    previous = cloud_forms.stored(ctx.scene)
    if previous is not None:
        call(ctx, "clouds", {"remove": True})
    return call(ctx, "sky", {"sun": sun_of(args, state), "dust": min(state["dust"], 10.0), "exposure": "keep"})


def clouds(ctx, args, state):
    layers = [dict(layer) for layer in state["layers"]]
    for layer in layers:
        if layer["genus"] in DECK_GENERA or state["cool"] > 0.0:
            cool = state["cool"]
            layer["tint"] = [1.0 + cool * (target - 1.0) for target in COOL_TINT]
        if layer["genus"] in DECK_GENERA:
            layer["brightness"] = state["darken"]
    request = {"layers": layers, "form": args["form"], "visibility": min(state["visibility"] * 3.0, 500_000.0)}
    entry = COMMANDS["clouds"]
    cleaned = validate(entry.schema, request)
    if state["rain"] > 0.0:
        cleaned["rain"] = {"rate": state["rain"]}
    return entry.run(ctx, cleaned)


def rain_source(cloud_result):
    if cloud_result is None:
        return None
    settings = cloud_result["layers"]
    for genus in ("cumulonimbus", "nimbostratus", "stratus"):
        for layer in settings:
            if layer["genus"] == genus:
                return layer
    return None


def rain(ctx, args, state, cloud_result):
    rate = state["rain"]
    report = {"rate": rate, "veil": False, "shaft": None, "foreground": None}
    if rate <= 0.0 or cloud_result is None:
        return report
    report["veil"] = True
    storm = next((layer for layer in cloud_result["layers"] if layer["genus"] == "cumulonimbus"), None)
    if storm is not None and args["form"] != "sheet":
        shaft = weather_rain.add_shaft(ctx.scene, storm, max(rate, 20.0), visible=args["form"] == "volume")
        report["shaft"] = shaft.name
    camera = ctx.scene.camera
    if state["foreground"] and camera is not None:
        brightness = ambient(ctx.scene, cloud_result) * 2.2
        streaks, count = weather_rain.add_streaks(ctx.scene, camera, rate, args["seed"], 95.0, brightness)
        report["foreground"] = {"object": streaks.name, "streaks": count, "camera": camera.name}
    return report


def ambient(scene, cloud_result):
    settings = sky_world.stored(scene.world)
    light = sky_world.illuminance(settings, cloud_result["sun_share"], cloud_result["diffuse_share"])
    return light / math.pi


def lightning(ctx, args, state, cloud_result):
    if not state["lightning"]:
        return None
    layers = cloud_result["layers"] if cloud_result else []
    storm = next((layer for layer in layers if layer["genus"] == "cumulonimbus"), None)
    centre = cloud_layers.observer(ctx.scene, None)
    heading = cloud_layers.view_heading(ctx.scene)
    if storm is not None:
        x, y = storm["centre"][0] - heading[1] * 900.0, storm["centre"][1] + heading[0] * 900.0
        base = storm["base"]
    else:
        decks = [layer["base"] for layer in layers if layer["coverage"] >= 0.9]
        lowest = min(decks or [layer["base"] for layer in layers] or [1500.0])
        x, y = centre[0] + heading[0] * BOLT_DISTANCE - heading[1] * 900.0, centre[1] + heading[1] * BOLT_DISTANCE + heading[0] * 900.0
        base = lowest
    settings = sky_world.stored(ctx.scene.world)
    scale = sky_world.SKY_SCALE * settings["strength"]
    bolt, flash = weather_lightning.add(ctx.scene, args["seed"] + 31, (x, y, base), (x + 400.0, y - 300.0, 0.0), 1.0, scale)
    return {"bolt": bolt.name, "flash": flash.name if flash is not None else None, "top": [round(x, 3), round(y, 3), round(base, 3)]}


def wet(ctx, args, state):
    if state["wet"] <= 0.0:
        return [], []
    return weather_wet.wet_scene(ctx.scene, state["wet"], args["seed"], args.get("wet_materials"))


def haze(ctx, args, state, cloud_result):
    if not args["haze"] or state["visibility"] > HAZE_REACH:
        call(ctx, "atmosphere", {"remove": True})
        return None
    if not any(obj.type in ("MESH", "CURVE") and weather_objects.kind_of(obj) is None for obj in ctx.scene.objects):
        return None
    cloudy = state["storm"] >= 0.46
    request = {
        "visibility": min(state["visibility"], HAZE_REACH),
        "height_falloff": 400.0 if state["rain"] <= 0.0 else 1500.0,
        "tint": HAZE_TINT["cloudy" if cloudy else "clear"],
        "anisotropy": 0.25 if cloudy else 0.55,
    }
    if cloud_result is not None and cloud_result["cover"] >= 0.5:
        grey = min(cloud_result["cloud_radiance"] * 0.9, 1.0)
        request.update({"method": "depth", "preview": "depth", "airlight": [round(grey * value, 6) for value in (0.95, 0.98, 1.0)]})
    result = call(ctx, "atmosphere", request)
    return {"visibility": result["visibility"], "object": result["object"], "tint": result["tint"], "method": result["method"]}


def exposure(ctx, args, state, cloud_result):
    settings = sky_world.stored(ctx.scene.world)
    sun = cloud_result["sun_share"] if cloud_result else 1.0
    diffuse = cloud_result["diffuse_share"] if cloud_result else 1.0
    light = sky_world.illuminance(settings, sun, diffuse) + overcast_light(settings, cloud_result)
    value = sky_world.exposure_for(light, state["compensation"])
    if cloud_result is not None:
        clear = sky_measure.luminance(settings["sky_mean"])
        cover = cloud_result["cover"]
        sky_light = clear * (1.0 - cover) + cloud_result["cloud_radiance"] * cover
        if sky_light > 1e-9:
            keyed = math.log2(state["sky_key"] / sky_light)
            value = min(value, keyed) * (1.0 - cover) + keyed * cover
    report = {"mode": args["exposure"], "recommended": round(value, 4), "illuminance": round(light, 6)}
    if args["exposure"] == "auto":
        ctx.scene.view_settings.exposure = value
    report["scene"] = round(float(ctx.scene.view_settings.exposure), 6)
    return report


def overcast_light(settings, cloud_result):
    """Light the cover passes on as diffuse light: the blocked sun times the cover's diffuse transmission."""
    if cloud_result is None:
        return 0.0
    sun = sky_measure.luminance(settings["sun_rgb"]) * max(math.sin(math.radians(settings["elevation"])), 0.0)
    return sun * (1.0 - cloud_result["sun_share"]) * cloud_result["diffuse_share"]
