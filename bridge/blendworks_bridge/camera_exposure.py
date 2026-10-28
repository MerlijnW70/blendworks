import math

from .errors import bad_args

REFERENCE_EV = 15.0
DEFAULT_VIEW_TRANSFORM = "AgX"
DEFAULT_LOOK = "none"
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


def ev100(aperture, shutter, iso):
    if aperture <= 0 or shutter <= 0 or iso <= 0:
        raise bad_args("aperture, shutter and iso must be positive")
    return math.log2(aperture * aperture / shutter) - math.log2(iso / 100.0)


def exposure_from_ev(ev, reference=REFERENCE_EV):
    return reference - ev


def luminance_factor(stops):
    return 2.0 ** stops


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
    return {
        "view_transform": view_settings.view_transform,
        "look": view_settings.look,
        "exposure": round(float(view_settings.exposure), 6),
        "gamma": round(float(view_settings.gamma), 6),
    }
