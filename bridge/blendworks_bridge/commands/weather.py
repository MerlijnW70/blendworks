from .. import cloud_layers, weather_build, weather_continuum
from ..errors import bad_args
from ..registry import command
from ..schema import boolean, integer, length, names, number, string
from .sky import SUN

WEATHER_FIELDS = {
    "preset": string("Named weather: a point of the storm continuum with optional overrides.", list(weather_continuum.PRESETS)),
    "storm": number("0 clear, 0.18 fair cumulus, 0.32 scattered, 0.46 broken, 0.6 overcast, 0.72 light rain, 0.86 heavy rain, 1 thunderstorm.", 0.0, 1.0),
    "time_of_day": string("Sun for a time of day; sun overrides it.", list(weather_continuum.TIMES)),
    "sun": SUN,
    "seed": integer("Seed of the clouds, rain and lightning.", 0, 2_147_483_647, 0),
    "form": string("Cloud form: auto (sheet in previews, volumes in render_final), volume or sheet.", list(cloud_layers.FORMS), "auto"),
    "dust": number("Override the continuum's dust (aerosol density).", 0.0, 10.0),
    "visibility": length("Override the continuum's visibility in metres.", None, 200_000.0),
    "rain": number("Override the rain rate in mm/h (0 none, 2 light, 15 heavy, 40 cloudburst).", 0.0, 100.0),
    "rain_foreground": boolean("Falling streaks in front of the active camera. Default: on in heavy rain and thunderstorms."),
    "wet": number("Override how wet the ground is, 0 to 1: darker base colour, glossier, puddles on flat ground.", 0.0, 1.0),
    "wet_materials": names("Materials to wet. Default: every material with a Principled BSDF on the scene's objects.", 1, 256),
    "lightning": boolean("Override lightning: a bolt and a flash light."),
    "haze": boolean("Add the weather's haze with atmosphere (a box around the scene).", True),
    "exposure": string("auto sets the scene exposure for the weather's light; keep leaves it.", ("auto", "keep"), "auto"),
    "remove": boolean("Remove the weather: clouds, rain, lightning, wet ground and haze; the clear sky stays.", False),
}


@command(
    "weather",
    "Whole weather in one call: presets from clear to thunderstorm or a storm value 0-1, sky, clouds, light, rain, wet ground, lightning, haze.",
    WEATHER_FIELDS,
    slow=True,
    family="weather",
    intents=(
        "make it overcast",
        "rainy day with wet ground",
        "thunderstorm with lightning",
        "golden hour with cumulus clouds",
        "change the weather of an outdoor scene",
    ),
    nearest=(("sky", "for a clear sky only"), ("clouds", "for your own cloud layers")),
)
def weather(ctx, args):
    scene = ctx.scene
    if args["remove"]:
        extra = [key for key in args if key in WEATHER_FIELDS and key not in ("remove", "seed", "form", "haze", "exposure")]
        if extra:
            raise bad_args(f"remove takes no other settings ({', '.join(sorted(extra))})")
        return {"removed": weather_build.remove(ctx)}
    state, source = resolve(args)
    weather_build.clear_extras(scene)
    sky_result = weather_build.sky(ctx, args, state)
    cloud_result = weather_build.clouds(ctx, args, state) if state["layers"] else None
    rain = weather_build.rain(ctx, args, state, cloud_result)
    lightning = weather_build.lightning(ctx, args, state, cloud_result)
    wetted, skipped = weather_build.wet(ctx, args, state)
    haze = weather_build.haze(ctx, args, state, cloud_result)
    exposure = weather_build.exposure(ctx, args, state, cloud_result)
    return {
        "preset": args.get("preset"),
        "source": source,
        "storm": round(state["storm"], 6),
        "sun": sky_result["sun"],
        "lamp": sky_result["lamp"],
        "layers": cloud_result["layers"] if cloud_result else [],
        "cover": cloud_result["cover"] if cloud_result else 0.0,
        "dust": state["dust"],
        "visibility": state["visibility"],
        "rain": rain,
        "lightning": lightning,
        "wet": {"wetness": round(state["wet"], 6), "materials": wetted, "skipped": skipped},
        "haze": haze,
        "exposure": exposure,
        "form": args["form"],
        "cost": cloud_result["cost"] if cloud_result else "no clouds",
        "replaced": sky_result["replaced"],
    }


def resolve(args):
    """The continuum state for the call: the preset's storm and overrides, then the call's own overrides."""
    if "preset" in args and "storm" in args:
        raise bad_args("give preset or storm, not both")
    chosen = weather_continuum.preset(args["preset"]) if "preset" in args else {"storm": args.get("storm", 0.0)}
    state = weather_continuum.state(chosen["storm"], args["seed"])
    source = {"storm": chosen["storm"], "overrides": {}}
    for key in weather_continuum.OVERRIDES:
        if key in chosen:
            state[key] = chosen[key]
            source["overrides"][key] = chosen[key]
        if key in args:
            state[key] = args[key]
            source["overrides"][key] = args[key]
    state["time_of_day"] = args.get("time_of_day", chosen.get("time_of_day", "noon"))
    state["foreground"] = args.get("rain_foreground", state["rain"] >= 10.0)
    if "time_of_day" in chosen and "time_of_day" not in args:
        source["overrides"]["time_of_day"] = chosen["time_of_day"]
    return state, source

