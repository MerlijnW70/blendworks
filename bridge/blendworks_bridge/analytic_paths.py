"""Exact circle, arc and helix paths for sweeps, with segment counts from a chord tolerance."""

import math

from mathutils import Vector

from .errors import bad_args
from .kit_limits import MAX_PATH_POINTS
from .limits import MAX_HELIX_TURNS, WINDING
from .schema import length, number, obj, string, vector3

DEFAULT_TOLERANCE = 0.0002
MIN_CIRCLE_SEGMENTS = 8
MAX_TURNS = MAX_HELIX_TURNS
ANGLE_LIMIT = WINDING


def path_fields():
    placement = {
        "centre": vector3("Centre [x, y, z] in metres.", [0.0, 0.0, 0.0]),
        "axis": vector3("Axis the path turns around; the profile v direction follows it unless up is given.", [0.0, 0.0, 1.0]),
        "radius": length("Radius in metres."),
        "reference": vector3("Direction of angle 0, made perpendicular to the axis. Default: +X, or +Y when the axis is along X."),
        "tolerance": length("Largest distance in metres between a chord of the path and the true circle; sets the segment count.", DEFAULT_TOLERANCE),
    }
    start = number("Angle in degrees of the first point.", -ANGLE_LIMIT, ANGLE_LIMIT, 0.0)
    end = number("Angle in degrees of the last point; below the start it turns the other way, and it stays under one full turn from the start.", -ANGLE_LIMIT, ANGLE_LIMIT)
    circle = obj({**placement, "start_angle": start}, ["radius"])
    arc = obj({**placement, "start_angle": start, "end_angle": end}, ["radius", "end_angle"])
    helix = obj(
        {
            **placement,
            "pitch": length("Rise along the axis per full turn in metres."),
            "turns": length("Number of turns, fractions allowed.", maximum=MAX_TURNS),
            "start_angle": start,
            "handed": string("right: the angle grows as the helix rises; left: it shrinks.", ["right", "left"], "right"),
        },
        ["radius", "pitch", "turns"],
    )
    circle["description"] = "A closed circle."
    arc["description"] = "An open arc."
    helix["description"] = "An open helix."
    return {"circle": circle, "arc": arc, "helix": helix}


def unit_axis(spec):
    axis = Vector(spec["axis"])
    if axis.length == 0:
        raise bad_args("axis must not be zero")
    return axis.normalized()


def plane_basis(axis, reference):
    if reference is None:
        reference = Vector((0, 1, 0)) if abs(axis.x) > 0.9 else Vector((1, 0, 0))
    reference = Vector(reference)
    first = reference - axis * reference.dot(axis)
    if first.length < 1e-9:
        raise bad_args("reference must not be parallel to the axis")
    first.normalize()
    return first, axis.cross(first)


def angle_step(radius, tolerance):
    return 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - tolerance / radius)))


def segment_count(radius, sweep, tolerance, minimum):
    count = max(minimum, math.ceil(sweep / angle_step(radius, tolerance) - 1e-9))
    if count + 1 > MAX_PATH_POINTS:
        raise bad_args(f"a tolerance of {tolerance} on radius {radius} needs {count} segments; the cap is {MAX_PATH_POINTS - 1}, so raise the tolerance")
    return count


def point_on(centre, first, second, radius, angle):
    return centre + (first * math.cos(angle) + second * math.sin(angle)) * radius


def circle_path(spec):
    axis = unit_axis(spec)
    first, second = plane_basis(axis, spec.get("reference"))
    centre, radius = Vector(spec["centre"]), spec["radius"]
    count = segment_count(radius, math.tau, spec["tolerance"], MIN_CIRCLE_SEGMENTS)
    start = math.radians(spec["start_angle"])
    points = [point_on(centre, first, second, radius, start + math.tau * index / count) for index in range(count)]
    return points, True, {"segments": count, "chord_error": radius * (1.0 - math.cos(math.pi / count)), "analytic_length": math.tau * radius, "axis": axis}


def arc_path(spec):
    axis = unit_axis(spec)
    first, second = plane_basis(axis, spec.get("reference"))
    centre, radius = Vector(spec["centre"]), spec["radius"]
    sweep = math.radians(spec["end_angle"] - spec["start_angle"])
    if abs(sweep) < 1e-9:
        raise bad_args("end_angle must differ from start_angle")
    if abs(sweep) >= math.tau - 1e-9:
        raise bad_args("an arc turns less than a full circle; use circle for a ring")
    count = segment_count(radius, abs(sweep), spec["tolerance"], 1)
    start = math.radians(spec["start_angle"])
    points = [point_on(centre, first, second, radius, start + sweep * index / count) for index in range(count + 1)]
    return points, False, {"segments": count, "chord_error": radius * (1.0 - math.cos(abs(sweep) / count / 2.0)), "analytic_length": radius * abs(sweep), "axis": axis}


def helix_path(spec):
    axis = unit_axis(spec)
    first, second = plane_basis(axis, spec.get("reference"))
    centre, radius = Vector(spec["centre"]), spec["radius"]
    sweep = math.tau * spec["turns"]
    count = segment_count(radius, sweep, spec["tolerance"], 1)
    start = math.radians(spec["start_angle"])
    direction = 1.0 if spec["handed"] == "right" else -1.0
    rise = spec["pitch"] * spec["turns"]
    points = [
        point_on(centre, first, second, radius, start + direction * sweep * index / count) + axis * (rise * index / count)
        for index in range(count + 1)
    ]
    return points, False, {
        "segments": count,
        "chord_error": radius * (1.0 - math.cos(sweep / count / 2.0)),
        "analytic_length": math.hypot(math.tau * radius, spec["pitch"]) * spec["turns"],
        "axis": axis,
    }


ANALYTIC_PATHS = {"circle": circle_path, "arc": arc_path, "helix": helix_path}
