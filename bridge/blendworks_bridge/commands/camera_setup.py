"""The camera_setup command: lens, sensor, depth of field, clip range and exposure of a camera."""

import math

from mathutils import Vector

from .. import camera_exposure, camera_reach, sky_world
from ..errors import bad_args
from ..limits import (HALF_TURN, LEAST_APERTURE_RATIO, LEAST_CAMERA_MILLIMETRES, LEAST_DISPLAY_GAMMA,
                      LEAST_EXPOSURE_VALUE, LEAST_F_NUMBER, LEAST_ISO, LEAST_SHUTTER, MAX_APERTURE_BLADES,
                      MAX_APERTURE_RATIO, MAX_CAMERA_SHIFT, MAX_DISPLAY_GAMMA, MAX_EXPOSURE_STOPS, MAX_EXPOSURE_VALUE,
                      MAX_F_NUMBER, MAX_FOCAL_LENGTH, MAX_ISO, MAX_SENSOR_SIZE, MAX_SHUTTER)
from ..registry import command
from ..schema import EXISTS, boolean, integer, length, number, obj, ref, string
from ..util import get_object, rounded

SENSOR_FITS = {"auto": "AUTO", "horizontal": "HORIZONTAL", "vertical": "VERTICAL"}
CIRCLE_OF_CONFUSION_DIVISOR = 1500.0
PHYSICAL = obj(
    {
        "shutter": number("Shutter time in seconds, for example 0.004 for 1/250 s.", LEAST_SHUTTER, MAX_SHUTTER),
        "iso": number("Sensor sensitivity (ISO).", LEAST_ISO, MAX_ISO, 100.0),
        "aperture": number("f-number for the exposure. Default: the camera's fstop, also when depth of field is off.", LEAST_F_NUMBER, MAX_F_NUMBER),
        "reference_ev": number(
            "EV100 that Blender's exposure 0 stands for. Default 15: a scene that looks right at exposure 0 counts as "
            "sunlit daylight (sunny 16 at ISO 100).",
            LEAST_EXPOSURE_VALUE,
            MAX_EXPOSURE_VALUE,
            camera_exposure.REFERENCE_EV,
        ),
    },
    ["shutter"],
)
PHYSICAL["description"] = "Exposure from a real camera: EV100 = log2(N^2 / t) - log2(ISO / 100), exposure = reference_ev - EV100."


@command(
    "camera_setup",
    "Set a camera's lens, sensor, depth of field (f-stop, focus distance or object), shift, exposure or metering, view, look and white balance.",
    {
        "name": ref(string("Camera object to set up."), "object", EXISTS),
        "focal_length": number("Focal length in millimetres.", LEAST_CAMERA_MILLIMETRES, MAX_FOCAL_LENGTH),
        "sensor_width": number("Sensor width in millimetres (36 is full frame).", LEAST_CAMERA_MILLIMETRES, MAX_SENSOR_SIZE),
        "sensor_height": number("Sensor height in millimetres (24 is full frame). Only the side the sensor fit uses matters.", LEAST_CAMERA_MILLIMETRES, MAX_SENSOR_SIZE),
        "sensor_fit": string("Which side the sensor width spans; auto: the larger side.", list(SENSOR_FITS)),
        "fstop": number("Aperture f-number; turns depth of field on. Smaller is blurrier.", LEAST_F_NUMBER, MAX_F_NUMBER),
        "depth_of_field": boolean("Turn depth of field on or off. Default: on when fstop or a focus is given."),
        "focus_distance": length("Focus distance in metres, along the view axis."),
        "focus_object": ref(string("Object whose origin stays in focus, also when it moves."), "object", EXISTS),
        "aperture_blades": integer("Aperture blades for polygonal bokeh; 0 is round.", 0, MAX_APERTURE_BLADES),
        "aperture_rotation": number("Rotation of the blades in degrees.", -HALF_TURN, HALF_TURN),
        "aperture_ratio": number("Anamorphic bokeh: width over height of the aperture.", LEAST_APERTURE_RATIO, MAX_APERTURE_RATIO),
        "shift_x": number("Horizontal lens shift, in frame widths.", -MAX_CAMERA_SHIFT, MAX_CAMERA_SHIFT),
        "shift_y": number("Vertical lens shift, in frame widths.", -MAX_CAMERA_SHIFT, MAX_CAMERA_SHIFT),
        "clip_start": length("Near clipping distance in metres."),
        "clip_end": length("Far clipping distance in metres; kept as given, also when the scene grows."),
        "clip_to_scene": boolean("Set the far clip to reach the farthest visible object, and keep covering the scene as it grows."),
        "exposure": number("Scene exposure in stops (Blender's exposure); each stop doubles the brightness.", -MAX_EXPOSURE_STOPS, MAX_EXPOSURE_STOPS),
        "physical": PHYSICAL,
        "view_transform": string(
            f"Scene view transform. Blender's default and ours: {camera_exposure.DEFAULT_VIEW_TRANSFORM}.",
            camera_exposure.VIEW_TRANSFORMS,
        ),
        "look": string(
            "Look of the view transform (AgX looks such as punchy or high_contrast). Default: none.",
            camera_exposure.LOOKS,
        ),
        "gamma": number("Display gamma; 1 is neutral.", LEAST_DISPLAY_GAMMA, MAX_DISPLAY_GAMMA),
        "metering": string(
            "Automatic exposure: render_final meters each frame with this pattern and puts the scene's key at 18 % grey "
            "(centre_weighted: 75 % of the weight in the central circle; average; spot). The sky and weather commands turn "
            "it on with centre_weighted; exposure or physical turn it off.",
            camera_exposure.METERING_MODES,
        ),
        "exposure_compensation": number("Stops added to the metered exposure, as a camera's exposure compensation; turns metering on.",
                                        -MAX_EXPOSURE_STOPS, MAX_EXPOSURE_STOPS),
        "white_balance": string(
            "auto: neutral under the sky's light (sun, sky or overcast) by its colour temperature; a preset sets the temperature "
            f"({', '.join(f'{name} {kelvin:g} K' for name, kelvin in camera_exposure.WHITE_BALANCE_PRESETS.items())}); off.",
            camera_exposure.WHITE_BALANCE_MODES,
        ),
    },
    ["name"],
    family="photography",
    intents=(
        "depth of field with an f-stop and focus distance",
        "set exposure from shutter speed, ISO and aperture",
        "AgX look and view transform for the render",
        "focal length and sensor size of a camera",
    ),
    nearest=(("add_camera", "to create the camera first"), ("render_final", "to render from it")),
)
def camera_setup(ctx, args):
    camera = get_object(args["name"])
    if camera.type != "CAMERA":
        raise bad_args(f"{camera.name} is not a camera")
    check_arguments(args)
    data = camera.data
    set_lens(data, args)
    set_far_clip(ctx, camera, args)
    set_depth_of_field(data, args)
    exposure = choose_exposure(args, data)
    look = args.get("look")
    if look is None and "view_transform" in args and camera_exposure.state(ctx.scene)["colour"].get("mode") == "camera":
        look = "none"
    camera_exposure.apply_view(ctx.scene.view_settings, args.get("view_transform"), look, exposure, args.get("gamma"))
    modes = record_modes(ctx.scene, args)
    ctx.view_layer.update()
    result = camera_report(camera)
    result["view"] = camera_exposure.view_report(ctx.scene.view_settings)
    result.update(modes)
    if "physical" in args:
        result["physical"] = camera_exposure.physical_exposure(args["physical"], data.dof.aperture_fstop)
    return result


def check_arguments(args):
    if len(args) == 1:
        raise bad_args("give at least one setting besides name")
    if "focus_distance" in args and "focus_object" in args:
        raise bad_args("give focus_distance or focus_object, not both")
    if "exposure" in args and "physical" in args:
        raise bad_args("give exposure or physical, not both")
    if ("exposure" in args or "physical" in args) and ("metering" in args or "exposure_compensation" in args):
        raise bad_args("a fixed exposure or physical exposure cannot meter; give one or the other")
    if args.get("depth_of_field") is False and any(key in args for key in ("fstop", "focus_distance", "focus_object")):
        raise bad_args("depth_of_field false cannot take fstop or a focus")
    if "clip_end" in args and args.get("clip_to_scene"):
        raise bad_args("give clip_end or clip_to_scene, not both")
    if "clip_start" in args and "clip_end" in args and args["clip_start"] >= args["clip_end"]:
        raise bad_args("clip_start must be below clip_end")
    if "focus_object" in args:
        get_object(args["focus_object"])


def set_lens(data, args):
    if "focal_length" in args:
        if data.type != "PERSP":
            raise bad_args("focal_length needs a perspective camera")
        data.lens = args["focal_length"]
    if "sensor_width" in args:
        data.sensor_width = args["sensor_width"]
    if "sensor_height" in args:
        data.sensor_height = args["sensor_height"]
    if "sensor_fit" in args:
        data.sensor_fit = SENSOR_FITS[args["sensor_fit"]]
    for name in ("shift_x", "shift_y", "clip_start", "clip_end"):
        if name in args:
            setattr(data, name, args[name])
    if data.clip_start >= data.clip_end:
        raise bad_args("clip_start must stay below clip_end")


def set_far_clip(ctx, camera, args):
    if "clip_end" in args:
        camera_reach.mark_explicit(camera.data, True)
    if "clip_to_scene" in args:
        camera_reach.mark_explicit(camera.data, False)
        if args["clip_to_scene"]:
            camera.data.clip_end = max(camera_reach.covering_clip(ctx.scene, ctx.view_layer, camera), camera.data.clip_start * 2.0)


def set_depth_of_field(data, args):
    dof = data.dof
    turned_on = args.get("depth_of_field")
    if turned_on is None and any(key in args for key in ("fstop", "focus_distance", "focus_object")):
        turned_on = True
    if turned_on is not None:
        dof.use_dof = turned_on
    if "fstop" in args:
        dof.aperture_fstop = args["fstop"]
    if "focus_distance" in args:
        dof.focus_object = None
        dof.focus_distance = args["focus_distance"]
    if "focus_object" in args:
        dof.focus_object = get_object(args["focus_object"])
    if "aperture_blades" in args:
        if args["aperture_blades"] in (1, 2):
            raise bad_args("aperture_blades is 0 (round) or at least 3")
        dof.aperture_blades = args["aperture_blades"]
    if "aperture_rotation" in args:
        dof.aperture_rotation = math.radians(args["aperture_rotation"])
    if "aperture_ratio" in args:
        dof.aperture_ratio = args["aperture_ratio"]


def record_modes(scene, args):
    """What the call chose stays chosen: an exposure turns metering off, metering turns it on, a view, look or gamma
    keeps the camera's colour away and a white balance replaces the automatic one."""
    report = {}
    if "exposure" in args or "physical" in args:
        camera_exposure.set_exposure_mode(scene, "manual")
    elif "metering" in args or "exposure_compensation" in args:
        mode, compensation = camera_exposure.auto_metering(scene)
        camera_exposure.set_exposure_mode(scene, "auto", metering=args.get("metering", mode),
                                          compensation=args.get("exposure_compensation", compensation))
    if any(key in args for key in ("view_transform", "look", "gamma")):
        camera_exposure.set_explicit(scene, colour=True)
    if "white_balance" in args:
        camera_exposure.set_explicit(scene, white_balance={"mode": args["white_balance"]})
        report["white_balance"] = camera_exposure.apply_white_balance(scene, sky_world.illuminant(scene))
    entry = camera_exposure.state(scene)["exposure"]
    report["exposure_mode"] = {key: entry.get(key) for key in ("mode", "metering", "compensation") if key in entry}
    return report


def choose_exposure(args, data):
    if "exposure" in args:
        return args["exposure"]
    if "physical" in args:
        return camera_exposure.physical_exposure(args["physical"], data.dof.aperture_fstop)["exposure"]
    return None


def focus_distance_of(camera):
    dof = camera.data.dof
    if dof.focus_object is None:
        return dof.focus_distance
    forward = camera.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
    offset = dof.focus_object.matrix_world.translation - camera.matrix_world.translation
    return max(offset.dot(forward.normalized()), 0.0)


def depth_of_field_limits(data, distance):
    focal = data.lens / 1000.0
    circle = data.sensor_width / CIRCLE_OF_CONFUSION_DIVISOR / 1000.0
    hyperfocal = focal * focal / (data.dof.aperture_fstop * circle) + focal
    if distance <= focal:
        return {"near": rounded(distance), "far": rounded(distance), "hyperfocal": rounded(hyperfocal)}
    near = distance * (hyperfocal - focal) / (hyperfocal + distance - 2.0 * focal)
    far = distance * (hyperfocal - focal) / (hyperfocal - distance) if distance < hyperfocal else None
    return {"near": rounded(near), "far": rounded(far) if far is not None else None, "hyperfocal": rounded(hyperfocal)}


def camera_report(camera):
    data = camera.data
    dof = data.dof
    report = {
        "name": camera.name,
        "type": data.type.lower(),
        "focal_length": rounded(data.lens),
        "sensor_width": rounded(data.sensor_width),
        "sensor_height": rounded(data.sensor_height),
        "sensor_fit": data.sensor_fit.lower(),
        "field_of_view": rounded(math.degrees(data.angle)),
        "shift": [rounded(data.shift_x), rounded(data.shift_y)],
        "clip": [rounded(data.clip_start), rounded(data.clip_end)],
        "depth_of_field": {"use": dof.use_dof},
    }
    if dof.use_dof:
        distance = focus_distance_of(camera)
        report["depth_of_field"].update(
            {
                "fstop": rounded(dof.aperture_fstop),
                "focus_distance": rounded(distance),
                "focus_object": dof.focus_object.name if dof.focus_object is not None else None,
                "blades": dof.aperture_blades,
                "sharp_range": depth_of_field_limits(data, distance) if data.type == "PERSP" else None,
            }
        )
    return report
