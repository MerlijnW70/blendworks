"""Flower geometry for ground cover: stems, heads, petals and centres."""

import math

import numpy

from .cover_blades import add_blade
from .cover_litter import CARD_LIFT
from .cover_mesh import ElementMesh, rotate_about, unit
from .phyllotaxis import GOLDEN_DEGREES

STEM_SLOT = 0
PETAL_SLOT = 1
CENTRE_SLOT = 2
FLOWER_PLANS = ((4, 3, 10, 2), (3, 3, 8, 2), (3, 2, 8, 1), (2, 2, 6, 1), (2, 1, 5, 0), (1, 1, 4, 0))
LEAF_BLADE = {"spread": 0.01, "lean": 50.0, "curvature": 0.6, "twist": 30.0, "taper": 0.6, "fold": 0.0, "dry_tips": 0.0, "dry_length": [0.2, 0.3]}


def flower_frame(p, rng):
    height = rng.uniform(p["height"][0], p["height"][1])
    azimuth = rng.uniform(0.0, 2.0 * math.pi)
    lean = math.radians(rng.uniform(0.0, 12.0))
    tilt = math.radians(p["head_tilt"]) * rng.uniform(0.5, 1.2)
    top = numpy.array([math.sin(lean) * math.cos(azimuth) * height, math.sin(lean) * math.sin(azimuth) * height, math.cos(lean) * height])
    facing = numpy.array([math.sin(lean + tilt) * math.cos(azimuth), math.sin(lean + tilt) * math.sin(azimuth), math.cos(lean + tilt)])
    return height, azimuth, lean, top, unit(facing)


def stem_points(top, lean, azimuth, segments):
    points = []
    for index in range(segments + 1):
        fraction = index / segments
        bow = math.sin(math.pi * fraction) * 0.04 * float(numpy.linalg.norm(top))
        side = numpy.array([-math.sin(azimuth), math.cos(azimuth), 0.0])
        points.append(top * fraction + side * bow)
    return points


def add_stem(mesh, p, points, phase, sides):
    height = float(points[-1][2]) or 1.0
    rings = []
    for index, point in enumerate(points):
        tangent = unit(points[min(index + 1, len(points) - 1)] - points[max(index - 1, 0)])
        first = unit(numpy.cross(tangent, [1.0, 0.0, 0.0] if abs(tangent[0]) < 0.9 else [0.0, 1.0, 0.0]))
        second = numpy.cross(tangent, first)
        fraction = float(point[2]) / height
        wind = (0.0, phase, fraction * fraction, fraction)
        radius = 0.5 * p["stem_width"] * (1.0 - 0.3 * fraction)
        rings.append([mesh.vertex(point + radius * (math.cos(2 * math.pi * k / sides) * first + math.sin(2 * math.pi * k / sides) * second), wind, phase) for k in range(sides)])
    for index in range(len(rings) - 1):
        for k in range(sides):
            following = (k + 1) % sides
            vs = (index / (len(rings) - 1), (index + 1) / (len(rings) - 1))
            mesh.face((rings[index][k], rings[index][following], rings[index + 1][following], rings[index + 1][k]), ((0.4, vs[0]), (0.6, vs[0]), (0.6, vs[1]), (0.4, vs[1])), STEM_SLOT)


def head_axes(facing):
    reference = numpy.array([1.0, 0.0, 0.0]) if abs(facing[0]) < 0.9 else numpy.array([0.0, 1.0, 0.0])
    first = unit(reference - facing * numpy.dot(reference, facing))
    return first, numpy.cross(facing, first)


def add_petal(mesh, p, centre, facing, outward, rows, phase, cup):
    length = p["petal_length"]
    width = p["petal_width"]
    across = unit(numpy.cross(facing, outward))
    direction = unit(rotate_about(outward, across, -cup))
    left, right, fractions = [], [], []
    for row in range(rows + 1):
        fraction = row / rows
        droop = rotate_about(direction, across, 0.35 * cup * fraction)
        point = centre + droop * length * fraction
        half = 0.5 * width * math.sin(math.pi * (0.15 + 0.85 * fraction) ** 0.6) if row < rows else 0.0
        wind = (fraction, phase, 1.0, 1.0)
        if row == rows:
            tip = mesh.vertex(point, wind, phase)
            left.append(tip)
            right.append(tip)
        else:
            left.append(mesh.vertex(point - across * half, wind, phase))
            right.append(mesh.vertex(point + across * half, wind, phase))
        fractions.append(fraction)
    mesh.quad_strip(left, right, (0.1, 0.9), fractions, PETAL_SLOT)


def add_centre(mesh, p, top, facing, ring, phase):
    first, second = head_axes(facing)
    radius = p["centre_radius"]
    wind = (0.0, phase, 1.0, 1.0)
    apex = mesh.vertex(top + facing * radius * 0.45, wind, phase)
    outline = [mesh.vertex(top + radius * (math.cos(2 * math.pi * k / ring) * first + math.sin(2 * math.pi * k / ring) * second), wind, phase) for k in range(ring)]
    for k in range(ring):
        following = (k + 1) % ring
        angles = (2 * math.pi * k / ring, 2 * math.pi * following / ring)
        mesh.face((outline[k], outline[following], apex), ((0.5 + 0.5 * math.cos(angles[0]), 0.5 + 0.5 * math.sin(angles[0])), (0.5 + 0.5 * math.cos(angles[1]), 0.5 + 0.5 * math.sin(angles[1])), (0.5, 0.5)), CENTRE_SLOT)


def flower_cost(petals, plan, leaves):
    stem, petal_rows, ring, leaf_segments = plan
    return 6 * stem + petals * (2 * petal_rows - 1) + ring + leaves * max(0, 2 * leaf_segments - 1)


def flower_geometry(p, rng, budget):
    petals = p["petals"]
    leaves = p["leaves"]
    plan = next((plan for plan in FLOWER_PLANS if flower_cost(petals, plan, leaves) <= budget), None)
    while plan is None and petals > 3:
        petals -= 1
        plan = next((plan for plan in FLOWER_PLANS if flower_cost(petals, plan, leaves) <= budget), None)
    plan = plan or FLOWER_PLANS[-1]
    stem_segments, petal_rows, ring, leaf_segments = plan
    height, azimuth, lean, top, facing = flower_frame(p, rng)
    phase = rng.uniform()
    mesh = ElementMesh()
    add_stem(mesh, p, stem_points(top, lean, azimuth, stem_segments), phase, 3)
    first, second = head_axes(facing)
    golden = math.radians(GOLDEN_DEGREES)
    for index in range(petals):
        angle = index * golden
        outward = math.cos(angle) * first + math.sin(angle) * second
        base = top + outward * p["centre_radius"] * 0.8
        add_petal(mesh, p, base, facing, outward, petal_rows, phase, math.radians(p["cup"]) * rng.uniform(0.7, 1.3))
    add_centre(mesh, p, top, facing, ring, phase)
    if leaf_segments:
        leaf = dict(LEAF_BLADE, height=[0.25 * height, 0.45 * height], width=p["leaf_width"])
        for _ in range(leaves):
            add_blade(mesh, leaf, rng, leaf_segments, False)
    return mesh, {"petals": petals, "stem_segments": stem_segments, "petal_rows": petal_rows, "height": round(height, 6)}


def flower_cards(p, rng, budget):
    petals = max(3, min(p["petals"], (budget - 6) // 2))
    height, azimuth, lean, top, facing = flower_frame(p, rng)
    phase = rng.uniform()
    mesh = ElementMesh()
    for plane in range(2):
        angle = azimuth + plane * 0.5 * math.pi
        along = numpy.array([math.cos(angle), math.sin(angle), 0.0]) * p["stem_width"] * 0.5
        rows = [(0.0, numpy.zeros(3)), (1.0, top)]
        indices = []
        for fraction, point in rows:
            wind = (0.0, phase, fraction * fraction, fraction)
            indices.append((mesh.vertex(point - along, wind, phase), mesh.vertex(point + along, wind, phase)))
        mesh.face((indices[0][0], indices[0][1], indices[1][1], indices[1][0]), ((0.4, 0.0), (0.6, 0.0), (0.6, 1.0), (0.4, 1.0)), STEM_SLOT)
    first, second = head_axes(facing)
    golden = math.radians(GOLDEN_DEGREES)
    for index in range(petals):
        angle = index * golden
        outward = math.cos(angle) * first + math.sin(angle) * second
        across = numpy.cross(facing, outward)
        lift = facing * (CARD_LIFT + 0.0002 * index)
        base, tip = top + lift, top + lift + outward * (p["petal_length"] + p["centre_radius"])
        half = across * p["petal_width"] * 0.6
        wind = (1.0, phase, 1.0, 1.0)
        corners = [mesh.vertex(point, wind, phase) for point in (base - half, base + half, tip + half, tip - half)]
        mesh.face(corners, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), PETAL_SLOT, False)
    half_one, half_two = first * p["centre_radius"], second * p["centre_radius"]
    centre = top + facing * (CARD_LIFT * 4.0)
    wind = (0.0, phase, 1.0, 1.0)
    corners = [mesh.vertex(point, wind, phase) for point in (centre - half_one - half_two, centre + half_one - half_two, centre + half_one + half_two, centre - half_one + half_two)]
    mesh.face(corners, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), CENTRE_SLOT, False)
    return mesh, {"petals": petals, "height": round(height, 6)}
