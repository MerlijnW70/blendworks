"""Gear and sprocket outlines: involute flanks, tooth angles and seats."""

import math

from .errors import bad_args

ADDENDUM = 1.0
DEDENDUM = 1.25
MIN_TEETH = 6
SEAT_CLEARANCE = 1.01


def involute(angle):
    return math.tan(angle) - angle


def polar(radius, angle):
    return (radius * math.cos(angle), radius * math.sin(angle))


def tooth_flank_angles(kind, teeth, pitch_radius, base_radius, root_radius, tip_radius, pressure, samples):
    pitch_half = math.pi / (2 * teeth)
    if kind == "involute":
        start = max(base_radius, root_radius)
        radii = [start + (tip_radius - start) * i / samples for i in range(samples + 1)]

        def half(radius):
            roll = math.acos(min(1.0, base_radius / radius))
            return pitch_half + involute(pressure) - involute(roll)

        flank = [(radius, half(radius)) for radius in radii]
        if root_radius < base_radius:
            flank.insert(0, (root_radius, flank[0][1]))
        return flank
    thickness = pitch_radius * pitch_half

    def half_simple(radius):
        return (thickness - (radius - pitch_radius) * math.tan(pressure)) / radius

    return [(root_radius, half_simple(root_radius)), (tip_radius, half_simple(tip_radius))]


def gear_outline(teeth, module, pressure_degrees, kind, samples):
    if teeth < MIN_TEETH:
        raise bad_args(f"a gear needs at least {MIN_TEETH} teeth")
    pitch_radius = module * teeth / 2.0
    tip_radius = pitch_radius + ADDENDUM * module
    root_radius = pitch_radius - DEDENDUM * module
    pressure = math.radians(pressure_degrees)
    base_radius = pitch_radius * math.cos(pressure)
    if root_radius <= 0:
        raise bad_args("the root circle would be inside the axis; use more teeth")
    flank = tooth_flank_angles(kind, teeth, pitch_radius, base_radius, root_radius, tip_radius, pressure, samples)
    step = math.tau / teeth
    if flank[-1][1] <= 1e-4:
        raise bad_args("the tooth tip is pointed; use more teeth or a smaller pressure_angle")
    if flank[0][1] >= step / 2 - 1e-4:
        raise bad_args("the teeth overlap at the root; use more teeth or a smaller pressure_angle")
    points = []
    for tooth in range(teeth):
        centre = tooth * step
        points.extend(polar(radius, centre - half) for radius, half in flank)
        points.extend(polar(radius, centre + half) for radius, half in reversed(flank))
        gap_start = centre + flank[0][1]
        gap_end = centre + step - flank[0][1]
        for part in (1, 2):
            points.append(polar(root_radius, gap_start + (gap_end - gap_start) * part / 3))
    return points, {"pitch_radius": pitch_radius, "tip_radius": tip_radius, "root_radius": root_radius, "module": module}


def seat_arc(pitch_radius, seat_radius, centre_angle, half_span, samples):
    centre = polar(pitch_radius, centre_angle)
    arc = []
    for step in range(samples + 1):
        gamma = half_span - 2 * half_span * step / samples
        arc.append((centre[0] - seat_radius * math.cos(centre_angle + gamma), centre[1] - seat_radius * math.sin(centre_angle + gamma)))
    return arc


def tip_of_flank(end, seat_centre, seat_radius, tip_radius):
    radial = ((end[0] - seat_centre[0]) / seat_radius, (end[1] - seat_centre[1]) / seat_radius)
    tangent = (radial[1], -radial[0])
    b = end[0] * tangent[0] + end[1] * tangent[1]
    c = end[0] ** 2 + end[1] ** 2 - tip_radius ** 2
    discriminant = b * b - c
    if discriminant <= 0:
        return None
    distance = -b + math.sqrt(discriminant)
    if distance <= 0:
        return None
    return (end[0] + tangent[0] * distance, end[1] + tangent[1] * distance)


def sprocket_outline(teeth, chain_pitch, roller_diameter, samples):
    if teeth < MIN_TEETH:
        raise bad_args(f"a sprocket needs at least {MIN_TEETH} teeth")
    pitch_radius = chain_pitch / (2 * math.sin(math.pi / teeth))
    seat_radius = roller_diameter / 2.0 * SEAT_CLEARANCE
    tip_radius = chain_pitch * (0.6 + 1.0 / math.tan(math.pi / teeth)) / 2.0
    root_radius = pitch_radius - seat_radius
    if roller_diameter >= chain_pitch * 0.95:
        raise bad_args("the roller diameter must be smaller than the chain pitch")
    step = math.tau / teeth
    span = math.radians(62.0)
    while span > math.radians(15.0):
        seat = seat_arc(pitch_radius, seat_radius, 0.0, span, samples)
        tip = tip_of_flank(seat[-1], polar(pitch_radius, 0.0), seat_radius, tip_radius)
        if tip is not None and math.atan2(tip[1], tip[0]) < step / 2 - 0.02 * step:
            break
        span -= math.radians(4.0)
    else:
        raise bad_args("this tooth count and roller size give no usable tooth; use more teeth or a smaller roller")
    tip_angle = math.atan2(tip[1], tip[0])
    tip_radius = math.hypot(*tip)
    points = []
    for index in range(teeth):
        base = index * step
        for x, y in seat_arc(pitch_radius, seat_radius, base, span, samples):
            points.append((x, y))
        points.append(polar(tip_radius, base + tip_angle))
        points.append(polar(tip_radius, base + step - tip_angle))
    return points, {"pitch_radius": pitch_radius, "tip_radius": tip_radius, "root_radius": root_radius, "seat_radius": seat_radius}
