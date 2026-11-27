import math

from .errors import bad_args
from .kit_limits import MAX_PROFILE_POINTS
from .limits import FEWEST_SIDES, MAX_LENGTH, PROFILE_SEGMENTS
from .outlines import circle_points, counter_clockwise, drop_repeats, signed_area
from .schema import integer, length, number, points2, string

PRESETS = ("circle", "rectangle", "rounded_rectangle")


def profile_fields():
    return {
        "profile": points2(
            "Closed cross-section as [u, v] points in metres in the section plane; any winding, the last point joins the first.",
            FEWEST_SIDES,
            MAX_PROFILE_POINTS,
        ),
        "preset": string("A named cross-section instead of profile.", PRESETS),
        "radius": length("preset circle: radius in metres."),
        "width": length("preset rectangle, rounded_rectangle: size along u in metres."),
        "height": length("preset rectangle, rounded_rectangle: size along v in metres."),
        "corner_radius": number("preset rounded_rectangle: corner radius in metres; 0 gives a plain rectangle.", 0.0, MAX_LENGTH),
        "segments": integer("preset circle: points around (default 16); rounded_rectangle: segments per corner (default 4).", 1, PROFILE_SEGMENTS),
    }


def rounded_rectangle(width, height, corner, segments):
    half_w, half_h = width / 2.0, height / 2.0
    if corner > min(half_w, half_h) + 1e-12:
        raise bad_args("corner_radius must be at most half of the smaller side")
    centres = [(half_w - corner, half_h - corner), (-half_w + corner, half_h - corner), (-half_w + corner, -half_h + corner), (half_w - corner, -half_h + corner)]
    points = []
    for quarter, (cx, cy) in enumerate(centres):
        for step in range(segments + 1):
            angle = math.pi / 2 * (quarter + step / segments)
            points.append((cx + corner * math.cos(angle), cy + corner * math.sin(angle)))
    return points


def preset_points(args):
    kind = args["preset"]
    allowed = {"circle": {"radius", "segments"}, "rectangle": {"width", "height"}, "rounded_rectangle": {"width", "height", "corner_radius", "segments"}}[kind]
    stray = sorted(key for key in ("radius", "width", "height", "corner_radius", "segments") if key in args and key not in allowed)
    if stray:
        raise bad_args(f"{', '.join(stray)} does not apply to the {kind} preset")
    if kind == "circle":
        if "radius" not in args:
            raise bad_args("the circle preset needs radius")
        return circle_points(args["radius"], args.get("segments", 16))
    for key in ("width", "height"):
        if key not in args:
            raise bad_args(f"the {kind} preset needs {key}")
    w, h = args["width"], args["height"]
    if kind == "rectangle":
        return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    if args.get("corner_radius", 0.0) <= 0:
        return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return rounded_rectangle(w, h, args["corner_radius"], args.get("segments", 4))


def resolve_profile(args, what="the profile"):
    if ("profile" in args) == ("preset" in args):
        raise bad_args(f"give {what} as exactly one of profile or preset")
    raw = args["profile"] if "profile" in args else preset_points(args)
    points = drop_repeats(raw, what)
    if abs(signed_area(points)) < 1e-14:
        raise bad_args(f"{what} encloses no area")
    return counter_clockwise(points)
