"""Exposure and colour the way a camera makes them.

Units: one scene-linear unit of radiance is liquid_light.scene_unit() cd/m2 (22 755), the value for which Blender's
exposure 0 stands for EV100 15 under the ISO 2720 reflected-light calibration K = 12.5 with 18 % grey; the same factor
turns irradiance units into lux. The procedural sky agrees: its sun outside the air gives 0.9 times the luminous solar
constant (Darula, Kittler and Gueymard 2005, 133.3 klx), within a sixth of a stop.

Metering: the reflected meter reads the scene-referred luminance of a small render through the camera and puts its
weighted log-average (the scene's key, Reinhard et al. 2002, "Photographic tone reproduction for digital images") at
18 % grey, the Zone V of the zone system. Centre-weighted gives 75 % of the weight to a circle half the frame height
across (Nikon's 12 mm circle in the 24 mm frame); spot reads a circle a sixth of the frame height across (4 mm of 24 mm);
average weighs the frame evenly. The incident meter of the sky and weather commands follows ISO 2720 with C = 250 for a
flat receptor.

Colour: the default view is AgX with the look that fits the published sRGB values of the ColorChecker neutral row
(X-Rite, 2014 formulation) best among Blender's looks at metered exposure; the auto white balance divides by the colour
of the light on a horizontal grey card (sun, sky and the light the cloud cover passes on) and reports its correlated
colour temperature by McCamy (1992). The presets are the Kelvin values of camera white-balance presets (Canon EOS)."""
import json
import math

import numpy

from .errors import bad_args
from .liquid_light import METER_CONSTANT, MID_GREY, scene_unit

REFERENCE_EV = 15.0
DEFAULT_VIEW_TRANSFORM = "AgX"
DEFAULT_LOOK = "none"
CAMERA_VIEW_TRANSFORM = "AgX"
CAMERA_LOOK = "high_contrast"
FACTORY_VIEW = ("AgX", "None", 1.0)
VIEW_TRANSFORMS = ("AgX", "Filmic", "Standard", "Khronos PBR Neutral", "ACES 1.3", "ACES 2.0", "Filmic Log", "False Color", "Raw")
LOOKS = (
    "none",
    "punchy",
    "greyscale",
    "very_high_contrast",
    "high_contrast",
    "medium_high_contrast",
    "base_contrast",
    "medium_low_contrast",
    "low_contrast",
    "very_low_contrast",
)
INCIDENT_CONSTANT = 250.0
METERING_MODES = ("centre_weighted", "average", "spot")
DEFAULT_METERING = "centre_weighted"
CENTRE_SHARE = 0.75
CENTRE_DIAMETER = 12.0 / 24.0
SPOT_DIAMETER = 4.0 / 24.0
LOG_FLOOR = 1e-6
EXPOSURE_RANGE = (-16.0, 24.0)
WHITE_BALANCE_PRESETS = {"daylight": 5200.0, "cloudy": 6000.0, "shade": 7000.0, "tungsten": 3200.0, "fluorescent": 4000.0, "flash": 6000.0}
WHITE_BALANCE_MODES = ("auto", "off") + tuple(WHITE_BALANCE_PRESETS)
PLANCKIAN_TINT = 0.0
STATE_PROPERTY = "blendworks_camera"
LUMINANCE = numpy.array([0.2126, 0.7152, 0.0722])
RGB_TO_XYZ = numpy.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
MCCAMY = (449.0, 3525.0, 6823.3, 5520.33)


def ev100(aperture, shutter, iso):
    if aperture <= 0 or shutter <= 0 or iso <= 0:
        raise bad_args("aperture, shutter and iso must be positive")
    return math.log2(aperture * aperture / shutter) - math.log2(iso / 100.0)


def exposure_from_ev(ev, reference=REFERENCE_EV):
    return reference - ev


def luminance_factor(stops):
    return 2.0 ** stops


def ev_of_luminance(candela):
    """EV100 a reflected-light meter (ISO 2720, K = 12.5) gives for a luminance in cd/m2."""
    return math.log2(max(candela, 1e-12) * 100.0 / METER_CONSTANT)


def ev_of_illuminance(lux):
    """EV100 an incident-light meter with a flat receptor (ISO 2720, C = 250) gives for an illuminance in lux."""
    return math.log2(max(lux, 1e-12) * 100.0 / INCIDENT_CONSTANT)


def clamped(exposure):
    return min(max(exposure, EXPOSURE_RANGE[0]), EXPOSURE_RANGE[1])


def incident_exposure(illuminance):
    """Exposure for an illuminance in scene units, as an incident meter held at the subject sets it."""
    return clamped(exposure_from_ev(ev_of_illuminance(illuminance * scene_unit())))


def metering_weights(height, width, mode):
    """Per-pixel weights summing to 1 for a metering mode, the circles centred on the frame."""
    if mode not in METERING_MODES:
        raise bad_args(f"unknown metering {mode}; choose one of {', '.join(METERING_MODES)}")
    if mode == "average":
        return numpy.full((height, width), 1.0 / (height * width))
    rows = (numpy.arange(height) + 0.5 - height / 2.0) / height
    columns = (numpy.arange(width) + 0.5 - width / 2.0) / height
    radius = numpy.hypot(*numpy.meshgrid(columns, rows))
    diameter = CENTRE_DIAMETER if mode == "centre_weighted" else SPOT_DIAMETER
    inside = radius <= diameter / 2.0
    if not inside.any():
        inside[height // 2, width // 2] = True
    weights = numpy.zeros((height, width))
    if mode == "spot" or inside.all():
        weights[inside] = 1.0 / inside.sum()
        return weights
    weights[inside] = CENTRE_SHARE / inside.sum()
    weights[~inside] = (1.0 - CENTRE_SHARE) / (~inside).sum()
    return weights


def meter(rgb, mode=DEFAULT_METERING, coverage=None):
    """Weighted log-average luminance of a scene-linear image, in scene units; with a coverage (alpha) only what covers
    the frame counts."""
    luminance = numpy.maximum(numpy.asarray(rgb, dtype=numpy.float64)[..., :3] @ LUMINANCE, 0.0)
    weights = metering_weights(luminance.shape[0], luminance.shape[1], mode)
    if coverage is not None:
        covered = weights * numpy.clip(numpy.asarray(coverage, dtype=numpy.float64), 0.0, 1.0)
        if covered.sum() > 0.0:
            weights = covered / covered.sum()
    return float(numpy.exp(numpy.sum(weights * numpy.log(LOG_FLOOR + luminance))))


def metered(key, mode, compensation=0.0):
    """Exposure and EV100 that put a metered key (scene units) at 18 % grey, plus any compensation in stops."""
    candela = key * scene_unit()
    ev = ev_of_luminance(candela)
    exposure = clamped(exposure_from_ev(ev) + compensation)
    return {
        "mode": "auto",
        "metering": mode,
        "key_luminance": round(candela, 6),
        "ev100": round(ev - compensation, 4),
        "compensation": compensation,
        "exposure": round(exposure, 6),
        "middle_grey": MID_GREY,
    }


def manual_report(exposure):
    return {"mode": "manual", "metering": None, "ev100": round(REFERENCE_EV - exposure, 4), "exposure": round(exposure, 6)}


def look_name(transform, look):
    if look == "none":
        return "None"
    title = " ".join(word.capitalize() for word in look.split("_"))
    return f"{transform} - {title}"


def physical_exposure(physical, aperture):
    chosen = physical.get("aperture", aperture)
    if chosen is None:
        raise bad_args("physical exposure needs an aperture: give physical.aperture or the camera's fstop")
    ev = ev100(chosen, physical["shutter"], physical["iso"])
    reference = physical["reference_ev"]
    return {
        "aperture": round(chosen, 6),
        "shutter": physical["shutter"],
        "iso": physical["iso"],
        "ev100": round(ev, 6),
        "reference_ev": reference,
        "exposure": round(exposure_from_ev(ev, reference), 6),
    }


def apply_view(view_settings, transform=None, look=None, exposure=None, gamma=None):
    if transform is not None:
        try:
            view_settings.view_transform = transform
        except TypeError as error:
            raise bad_args(f"view transform {transform} is not available in this Blender: {error}") from error
    if look is not None:
        name = look_name(view_settings.view_transform, look)
        try:
            view_settings.look = name
        except TypeError as error:
            raise bad_args(f"look {look} ({name}) does not exist for the view transform {view_settings.view_transform}") from error
    if exposure is not None:
        view_settings.exposure = exposure
    if gamma is not None:
        view_settings.gamma = gamma


def view_report(view_settings):
    report = {
        "view_transform": view_settings.view_transform,
        "look": view_settings.look,
        "exposure": round(float(view_settings.exposure), 6),
        "gamma": round(float(view_settings.gamma), 6),
    }
    if view_settings.use_white_balance:
        report["white_balance"] = {"temperature": round(float(view_settings.white_balance_temperature), 1),
                                   "tint": round(float(view_settings.white_balance_tint), 3)}
    return report


def correlated_temperature(rgb):
    """Correlated colour temperature in kelvin of a linear Rec.709 colour, by McCamy's cubic in the CIE 1931 xy."""
    xyz = RGB_TO_XYZ @ numpy.asarray(rgb, dtype=numpy.float64)
    total = float(xyz.sum())
    if total <= 0.0:
        return None
    x, y = xyz[0] / total, xyz[1] / total
    n = (x - 0.3320) / (0.1858 - y)
    a, b, c, d = MCCAMY
    return float(a * n ** 3 + b * n ** 2 + c * n + d)


def state(scene):
    saved = scene.get(STATE_PROPERTY)
    found = json.loads(saved) if saved else {}
    found.setdefault("exposure", {"mode": "manual"})
    found.setdefault("colour", {"mode": "camera"})
    found.setdefault("white_balance", {"mode": "auto"})
    return found


def store(scene, found):
    scene[STATE_PROPERTY] = json.dumps(found, sort_keys=True)


def colour_signature(view):
    return [view.view_transform, view.look, round(float(view.gamma), 6)]


def white_signature(view):
    if not view.use_white_balance:
        return None
    return [round(float(value), 4) for value in view.white_balance_whitepoint]


def set_exposure_mode(scene, mode, applied=None, metering=None, compensation=None):
    found = state(scene)
    entry = dict(found["exposure"], mode=mode)
    if metering is not None:
        entry["metering"] = metering
    if compensation is not None:
        entry["compensation"] = compensation
    entry["applied"] = None if applied is None else round(float(applied), 6)
    found["exposure"] = entry
    store(scene, found)


def set_explicit(scene, colour=False, white_balance=None):
    found = state(scene)
    if colour:
        found["colour"] = {"mode": "explicit"}
    if white_balance is not None:
        found["white_balance"] = white_balance
    store(scene, found)


def exposure_is_auto(scene):
    """Auto when the sky, weather or camera_setup's metering asked for it and nobody has set the exposure since."""
    entry = state(scene)["exposure"]
    if entry.get("mode") != "auto":
        return False
    applied = entry.get("applied")
    return applied is None or abs(float(scene.view_settings.exposure) - applied) < 1e-5


def auto_metering(scene):
    entry = state(scene)["exposure"]
    return entry.get("metering", DEFAULT_METERING), float(entry.get("compensation", 0.0))


def apply_camera_colour(scene):
    """The camera's view and look, unless they were chosen: given to camera_setup or changed since they were applied."""
    view = scene.view_settings
    found = state(scene)
    entry = found["colour"]
    current = colour_signature(view)
    untouched = current == list(FACTORY_VIEW) or current == entry.get("applied")
    if entry.get("mode") != "camera" or not untouched:
        return {"mode": "explicit" if entry.get("mode") != "camera" else "kept", "view_transform": view.view_transform, "look": view.look}
    apply_view(view, CAMERA_VIEW_TRANSFORM, CAMERA_LOOK)
    found["colour"] = {"mode": "camera", "applied": colour_signature(view)}
    store(scene, found)
    return {"mode": "camera", "view_transform": view.view_transform, "look": view.look}


def set_white_point(view, rgb):
    rgb = numpy.asarray(rgb, dtype=numpy.float64)
    grey = float(rgb @ LUMINANCE)
    view.use_white_balance = True
    view.white_balance_whitepoint = [float(value) for value in rgb / grey]


def apply_white_balance(scene, illuminant):
    """White balance by the mode camera_setup chose: auto divides by the illuminant colour, a preset sets the
    temperature on the Planckian locus, off turns it off. Auto keeps a balance set by hand since it was last applied."""
    view = scene.view_settings
    found = state(scene)
    entry = found["white_balance"]
    mode = entry.get("mode", "auto")
    if mode == "off":
        view.use_white_balance = False
        return {"mode": "off"}
    if mode != "auto":
        view.use_white_balance = True
        view.white_balance_temperature = WHITE_BALANCE_PRESETS[mode]
        view.white_balance_tint = PLANCKIAN_TINT
        return {"mode": mode, "temperature": round(float(view.white_balance_temperature), 1), "tint": PLANCKIAN_TINT}
    applied = entry.get("applied")
    if white_signature(view) is not None and white_signature(view) != applied:
        return {"mode": "kept", "temperature": round(float(view.white_balance_temperature), 1), "tint": round(float(view.white_balance_tint), 3)}
    if illuminant is None or float(numpy.asarray(illuminant["rgb"]) @ LUMINANCE) <= 0.0:
        view.use_white_balance = False
        found["white_balance"] = {"mode": "auto", "applied": None}
        store(scene, found)
        return {"mode": "auto", "illuminant": None}
    set_white_point(view, illuminant["rgb"])
    found["white_balance"] = {"mode": "auto", "applied": white_signature(view)}
    store(scene, found)
    cct = correlated_temperature(illuminant["rgb"])
    return {
        "mode": "auto",
        "illuminant": illuminant["source"],
        "cct": round(cct, 1) if cct is not None else None,
        "temperature": round(float(view.white_balance_temperature), 1),
        "tint": round(float(view.white_balance_tint), 3),
    }
