import math

from .. import camera_exposure, cloud_forms, sky_sun, sky_world, world_background
from . import clouds
from ..limits import (ATMOSPHERE_DENSITY, DATE_LENGTH, HALF_TURN, MAX_WORLD_STRENGTH, QUARTER_TURN, SKY_ALTITUDE,
                      SMALLEST_SUN_SIZE, SUN_INTENSITY, SUN_SIZE, TIME_LENGTH, TURN, TWILIGHT_DEPTH, UTC_OFFSET)
from ..registry import command
from ..schema import ENSURES, number, obj, ref, string

EXPOSURE_MODES = ("auto", "keep")
SUN = obj(
    {
        "elevation": number("Sun height above the horizon in degrees; below 0 is twilight.", -TWILIGHT_DEPTH, QUARTER_TURN),
        "azimuth": number("Compass direction of the sun in degrees, clockwise from north (+Y): 90 is east (+X).", 0.0, TURN),
        "date": string("Date YYYY-MM-DD for a sun from the calendar.", max_length=DATE_LENGTH),
        "time": string("Local clock time HH:MM or HH:MM:SS.", max_length=TIME_LENGTH),
        "latitude": number("Latitude in degrees, north positive.", -QUARTER_TURN, QUARTER_TURN),
        "longitude": number("Longitude in degrees, east positive.", -HALF_TURN, HALF_TURN),
        "utc_offset": number("Hours the local clock is ahead of UTC. Default: longitude / 15, rounded.", -UTC_OFFSET, UTC_OFFSET),
    }
)
SUN["description"] = "Where the sun stands: elevation and azimuth, or date, time, latitude and longitude. Default: 45 degrees high in the south."
SKY_FIELDS = {
    "model": string("Blender's sky model: multiple_scattering (current) or single_scattering (Nishita).", list(sky_world.MODELS), "multiple_scattering"),
    "sun": SUN,
    "altitude": number("Observer altitude in metres.", 0.0, SKY_ALTITUDE, 0.0),
    "air": number("Air (Rayleigh) density; 1 is the standard atmosphere.", 0.0, ATMOSPHERE_DENSITY, 1.0),
    "dust": number("Dust and haze (aerosol) density; 1 is a clear day, 3 to 6 hazy.", 0.0, ATMOSPHERE_DENSITY, 1.0),
    "ozone": number("Ozone density; 1 is standard.", 0.0, ATMOSPHERE_DENSITY, 1.0),
    "sun_size": number("Angular diameter of the sun in degrees.", SMALLEST_SUN_SIZE, SUN_SIZE, 0.545),
    "sun_intensity": number("Brightness of the sun disc; the lamp follows it.", 0.0, SUN_INTENSITY, 1.0),
    "strength": number(f"Sky brightness; 1 lights a clear noon at exposure 0 (the sky's own units times {sky_world.SKY_SCALE:g}).", 0.0, MAX_WORLD_STRENGTH, 1.0),
    "lamp": ref(string("Sun lamp to create or update.", default=sky_world.LAMP_DEFAULT), "object", ENSURES),
    "exposure": string("auto sets the scene exposure for this light; keep leaves it.", EXPOSURE_MODES, "auto"),
}


@command(
    "sky",
    "Procedural physical sky in the world: sun by angles or by date, time and place, air, dust and ozone; a matching sun lamp and exposure.",
    SKY_FIELDS,
    family="weather",
    intents=(
        "procedural sky with a sun",
        "sun position from date, time and location",
        "blue daylight sky without an HDRI",
        "sunset or twilight sky",
    ),
    nearest=(("weather", "for clouds, rain and storms"), ("set_world_hdri", "for an HDRI image"), ("set_world", "for a plain colour")),
)
def sky(ctx, args):
    settings, sun = sky_world.settings_from(args)
    settings.update(sky_world.measured(settings))
    previous = cloud_forms.stored(ctx.scene)
    world, output, replaced = world_background.replace(ctx.scene, keep_weather=True)
    sky_world.build(world, output, settings)
    lamp, created = sky_world.place_lamp(ctx, args["lamp"], settings, settings["sun_rgb"])
    settings["lamp"] = lamp.name
    sky_world.store(world, settings)
    result = report(ctx, settings, sun, lamp, created, replaced, args["exposure"])
    if previous is not None:
        rebuilt = clouds.build(ctx, previous["args"])
        result["clouds"] = {"rebuilt": [layer["genus"] for layer in rebuilt["layers"]]}
    return result


def report(ctx, settings, sun, lamp, created, replaced, exposure_mode, cloud_factor=1.0, diffuse_factor=1.0):
    light = lamp.data
    illuminance = sky_world.illuminance(settings, cloud_factor, diffuse_factor)
    exposure = {"mode": exposure_mode, "recommended": round(sky_world.exposure_for(illuminance), 4)}
    if exposure_mode == "auto":
        camera_exposure.apply_view(ctx.scene.view_settings, exposure=exposure["recommended"])
    exposure["scene"] = round(float(ctx.scene.view_settings.exposure), 6)
    placed = {key: round(value, 6) for key, value in sun.items() if isinstance(value, float)}
    placed.update({key: value for key, value in sun.items() if isinstance(value, str)})
    placed["elevation"] = settings["elevation"]
    placed["azimuth"] = settings["azimuth"]
    placed["direction"] = [round(value, 6) for value in sky_sun.direction(settings["elevation"], settings["azimuth"])]
    placed["below_horizon"] = settings["elevation"] < -settings["sun_size"] / 2.0
    return {
        "world": ctx.scene.world.name,
        "model": settings["model"],
        "sun": placed,
        "lamp": {
            "name": lamp.name,
            "created": created,
            "strength": round(float(light.energy), 6),
            "color": [round(float(value), 6) for value in light.color],
            "angle": round(math.degrees(light.angle), 6),
        },
        "sky": {
            "horizontal_irradiance": settings["sky_irradiance"],
            "mean_radiance": settings["sky_mean"],
            "horizon_radiance": settings["horizon"],
            "sun_irradiance": settings["sun_rgb"],
            "illuminance": round(illuminance, 6),
        },
        "exposure": exposure,
        "replaced": replaced,
    }
