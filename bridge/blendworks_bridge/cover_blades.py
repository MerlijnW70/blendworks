"""Grass blade geometry for ground cover: triangles, widths, shapes and clumps."""

import math

import numpy

from .cover_mesh import NEVER_DRY, ElementMesh, rotate_about, segments_for, unit

MAX_BLADE_SEGMENTS = 8
BASE_ROUNDING = 0.08
BEND_POWER = 1.7


def blade_triangles(segments, folded):
    return 4 * segments - 2 if folded else 2 * segments - 1


def blade_plan(p, budget):
    folded = p["fold"] > 0.0
    blades = p["blades"]
    segments = segments_for(budget, blades, lambda count: blade_triangles(count, folded), 1, MAX_BLADE_SEGMENTS)
    if segments is None and folded:
        folded = False
        segments = segments_for(budget, blades, lambda count: blade_triangles(count, False), 1, MAX_BLADE_SEGMENTS)
    if segments is None:
        segments = 1
        blades = max(1, budget // blade_triangles(1, folded))
    return blades, segments, folded


TAPER_POWER = 1.15


def blade_width(p, fraction):
    rounding = min(1.0, 0.55 + fraction / BASE_ROUNDING * 0.45)
    return p["width"] * (1.0 - p["taper"] * fraction**TAPER_POWER) * rounding


def blade_shape(p, rng):
    radius = p["spread"] * math.sqrt(rng.uniform())
    angle = rng.uniform(0.0, 2.0 * math.pi)
    root = numpy.array([radius * math.cos(angle), radius * math.sin(angle), 0.0])
    outward = radius / p["spread"] if p["spread"] > 0 else rng.uniform()
    heading = angle + rng.normal(0.0, 0.5)
    lean = math.radians(p["lean"]) * (0.25 + 0.75 * outward) * rng.uniform(0.6, 1.2)
    height = rng.uniform(p["height"][0], p["height"][1])
    bend = p["curvature"] * 0.5 * math.pi * rng.uniform(0.5, 1.3) * (0.6 + 0.6 * height / p["height"][1])
    twist = math.radians(p["twist"]) * rng.uniform(-1.0, 1.0)
    phase = rng.uniform()
    dry = 1.0 - rng.uniform(p["dry_length"][0], p["dry_length"][1]) if rng.uniform() < p["dry_tips"] else NEVER_DRY
    return root, heading, lean, bend, height, twist, phase, dry


def centreline(root, heading, lean, bend, height, segments):
    points = [root]
    tangents = []
    step = height / segments
    for index in range(segments):
        middle = (index + 0.5) / segments
        theta = min(lean + bend * middle**BEND_POWER, 0.47 * math.pi)
        direction = numpy.array([math.sin(theta) * math.cos(heading), math.sin(theta) * math.sin(heading), math.cos(theta)])
        tangents.append(direction)
        points.append(points[-1] + step * direction)
    node_tangents = [tangents[0]] + [unit(tangents[index - 1] + tangents[index]) for index in range(1, segments)] + [tangents[-1]]
    return points, node_tangents


def add_blade(mesh, p, rng, segments, folded):
    root, heading, lean, bend, height, twist, phase, dry = blade_shape(p, rng)
    points, tangents = centreline(root, heading, lean, bend, height, segments)
    across = numpy.array([-math.sin(heading), math.cos(heading), 0.0])
    left, middle, right, fractions = [], [], [], []
    for index, (point, tangent) in enumerate(zip(points, tangents)):
        fraction = index / segments
        fractions.append(fraction)
        wind_middle = (0.0, phase, fraction * fraction, fraction)
        if index == segments:
            tip = mesh.vertex(point, wind_middle, phase, dry)
            left.append(tip)
            right.append(tip)
            middle.append(tip)
            continue
        side = rotate_about(across, tangent, twist * fraction)
        side = unit(side - tangent * numpy.dot(side, tangent))
        face_normal = unit(numpy.cross(side, tangent))
        half = 0.5 * blade_width(p, fraction)
        wind_edge = (fraction, phase, fraction * fraction, fraction)
        left.append(mesh.vertex(point - side * half, wind_edge, phase, dry))
        right.append(mesh.vertex(point + side * half, wind_edge, phase, dry))
        if folded:
            middle.append(mesh.vertex(point - face_normal * half * p["fold"], wind_middle, phase, dry))
    if folded:
        mesh.quad_strip(left, middle, (0.0, 0.5), fractions)
        mesh.quad_strip(middle, right, (0.5, 1.0), fractions)
    else:
        mesh.quad_strip(left, right, (0.0, 1.0), fractions)


def blade_clump(p, rng, budget):
    blades, segments, folded = blade_plan(p, budget)
    mesh = ElementMesh()
    for _ in range(blades):
        add_blade(mesh, p, rng, segments, folded)
    return mesh, {"blades": blades, "segments": segments, "folded": folded}


def card_plan(budget):
    for planes, rows in ((3, 3), (3, 2), (2, 2), (2, 1), (1, 1)):
        if planes * rows * 2 <= budget:
            return planes, rows
    return 1, 1


def blade_cards(p, rng, budget):
    planes, rows = card_plan(budget)
    tallest = p["height"][1]
    reach = math.sin(min(math.radians(p["lean"]) + p["curvature"] * 0.5 * math.pi * 0.6, 0.5 * math.pi))
    width = max(2.0 * p["spread"] + 1.2 * tallest * reach, 0.45 * tallest)
    mesh = ElementMesh()
    start = rng.uniform(0.0, math.pi)
    for plane in range(planes):
        angle = start + plane * math.pi / planes
        along = numpy.array([math.cos(angle), math.sin(angle), 0.0])
        facing = numpy.array([-math.sin(angle), math.cos(angle), 0.0])
        phase = rng.uniform()
        sway = rng.choice([-1.0, 1.0]) * p["curvature"] * 0.12 * tallest
        left, right, fractions = [], [], []
        for row in range(rows + 1):
            fraction = row / rows
            centre = facing * sway * fraction * fraction + numpy.array([0.0, 0.0, tallest * fraction * (1.0 - 0.08 * p["curvature"] * fraction)])
            wind = (0.0, phase, fraction * fraction, fraction)
            left.append(mesh.vertex(centre - along * 0.5 * width, wind, phase))
            right.append(mesh.vertex(centre + along * 0.5 * width, wind, phase))
            fractions.append(fraction)
        mesh.quad_strip(left, right, (0.0, 1.0), fractions)
    return mesh, {"planes": planes, "rows": rows, "card_width": round(width, 6)}
