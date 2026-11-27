import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from liquid_helpers import top_faces

GRAVITY = 9.81
NOTE_13 = "Cited values of the presets (docs/research/liquids.md): coffee 65 mN/m and 1000 kg/m3, fresh water 72.8 mN/m and 998 kg/m3."
LIQUIDS = {"coffee": (0.065, 1000.0), "water_fresh": (0.0728, 998.0)}
OVERLAP = 1e-4
THICKNESS_TOLERANCE = 0.03
PROFILE_TOLERANCE = 0.06
ROUND_AT_MOST = 0.92
AREA_TOLERANCE = 0.01


def capillary_length(liquid):
    tension, density = LIQUIDS[liquid]
    return math.sqrt(tension / (density * GRAVITY))


def thickness(liquid, angle):
    """de Gennes, Brochard-Wyart and Quere (2004): a large puddle is e = 2 l_c sin(theta / 2) thick."""
    return 2.0 * capillary_length(liquid) * math.sin(math.radians(angle) / 2.0)


def exact_profile(liquid, angle, distances):
    """Height at the given distances from the contact line, by stepping the capillary equation from the line: the slope phi of
    the surface follows from the height z as sin(phi / 2) = (e - z) / (2 l_c), dz/dx = tan(phi). This does not use the
    closed form the code does."""
    l_c, e = capillary_length(liquid), thickness(liquid, angle)
    step, x, z = l_c * 2e-4, 0.0, 0.0
    xs, zs = [0.0], [0.0]
    while x < max(distances):
        phi = 2.0 * math.asin(min(1.0, max(0.0, (e - z) / (2.0 * l_c))))
        z += math.tan(phi) * step
        x += step
        xs.append(x)
        zs.append(z)
    return np.interp(distances, xs, zs)


def spill_geometry(name):
    obj = bpy.data.objects[name]
    mesh = obj.data
    points = np.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    points = points.reshape(-1, 3)
    flags = top_faces(name)
    edges = {}
    top = set()
    for polygon in mesh.polygons:
        if not flags[polygon.index]:
            continue
        top.update(polygon.vertices)
        ring = list(polygon.vertices)
        for first, second in zip(ring, ring[1:] + ring[:1]):
            key = (min(first, second), max(first, second))
            edges[key] = edges.get(key, 0) + 1
    boundary = sorted({vertex for key, count in edges.items() if count == 1 for vertex in key})
    centre = points[boundary][:, :2].mean(axis=0)
    angle = np.arctan2(points[boundary][:, 1] - centre[1], points[boundary][:, 0] - centre[0])
    outline = points[boundary][np.argsort(angle)][:, :2]
    return points, sorted(top), outline


def distance_to(outline, planar):
    start, along = outline, np.roll(outline, -1, axis=0) - outline
    result = np.empty(len(planar))
    for index, point in enumerate(planar):
        offset = point - start
        share = np.clip((offset * along).sum(axis=1) / np.maximum((along * along).sum(axis=1), 1e-30), 0.0, 1.0)
        result[index] = np.linalg.norm(offset - share[:, None] * along, axis=1).min()
    return result


def polygon(outline):
    x, y = outline[:, 0], outline[:, 1]
    area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    perimeter = np.linalg.norm(np.roll(outline, -1, axis=0) - outline, axis=1).sum()
    return area, perimeter


def table(bridge):
    bridge.ok("add_primitive", type="plane", name="Table", size=2.0)


def spill(bridge, liquid, area, angle=None, seed=4, name="Spill"):
    table(bridge) if "Table" not in bpy.data.objects else None
    settings = {"point": [0.0, 0.0, 0.0], "area": area, "surface": "Table"}
    if angle is not None:
        settings["contact_angle"] = angle
    return bridge.ok("liquid_fill", preset=liquid, name=name, spill=settings, seed=seed)


def test_a_spill_is_as_thick_as_surface_tension_and_the_contact_angle_make_it(bridge):
    for index, (liquid, angle) in enumerate((("coffee", None), ("coffee", 50.0), ("water_fresh", 30.0))):
        result = spill(bridge, liquid, 0.02, angle, name=f"Spill{index}")["spill"]
        expected = thickness(liquid, 20.0 if angle is None else angle)
        points, top, _ = spill_geometry(result["name"])
        measured = points[top][:, 2].max() + OVERLAP
        assert abs(measured - expected) < THICKNESS_TOLERANCE * expected, (liquid, angle, measured, expected)
        assert abs(result["thickness"] - expected) < THICKNESS_TOLERANCE * expected


def test_a_spill_has_a_thin_meniscus_rim_the_capillary_profile_of_a_wedge(bridge):
    result = spill(bridge, "coffee", 0.02, 35.0)["spill"]
    points, top, outline = spill_geometry(result["name"])
    l_c = capillary_length("coffee")
    e = thickness("coffee", 35.0)
    planar = points[top][:, :2]
    inward = distance_to(outline, planar)
    lift = points[top][:, 2] + OVERLAP
    rim = (inward > 0.05 * l_c) & (inward < 3.0 * l_c)
    assert rim.sum() > 300, "the mesh resolves the rim"
    expected = exact_profile("coffee", 35.0, inward[rim])
    error = np.abs(lift[rim] - expected) / e
    assert np.median(error) < PROFILE_TOLERANCE and np.percentile(error, 90) < 3 * PROFILE_TOLERANCE, (np.median(error), np.percentile(error, 90))
    near = (inward > 0.1 * l_c) & (inward < 0.4 * l_c)
    slope = np.polyfit(inward[near], lift[near], 1)[0]
    steady = np.polyfit(inward[near], exact_profile("coffee", 35.0, inward[near]), 1)[0]
    assert abs(slope - steady) < 0.1 * steady and steady > 0.5 * math.tan(math.radians(35.0)), (slope, steady)
    plateau = lift[inward > 6.0 * l_c]
    assert abs(plateau.mean() - e) < 0.03 * e and plateau.std() < 0.01 * e
    deposit = bpy.data.objects[result["name"]].data.attributes["lq_deposit"]
    values = np.zeros(len(deposit.data), dtype=np.float32)
    deposit.data.foreach_get("value", values)
    assert values[top][inward < 0.1 * l_c].min() > 0.9 and values[top][inward > 4.0 * l_c].max() < 0.05, "a visible rim line at the contact line only"


def test_a_spill_outline_is_irregular_and_holds_the_area(bridge):
    first = spill(bridge, "coffee", 0.02, seed=1, name="One")["spill"]
    second = spill(bridge, "coffee", 0.02, seed=2, name="Two")["spill"]
    shapes = []
    for result in (first, second):
        _, _, outline = spill_geometry(result["name"])
        area, perimeter = polygon(outline)
        assert abs(area - 0.02) < AREA_TOLERANCE * 0.02, area
        assert 4.0 * math.pi * area / perimeter**2 < ROUND_AT_MOST, "not a circle"
        shapes.append(outline)
    centre = [shape.mean(axis=0) for shape in shapes]
    radii = [np.linalg.norm(shape - c, axis=1) for shape, c in zip(shapes, centre)]
    assert radii[0].std() / radii[0].mean() > 0.04 and radii[1].std() / radii[1].mean() > 0.04
    assert abs(radii[0].mean() - radii[1].mean()) < 0.1 * radii[0].mean() and not np.allclose(np.sort(radii[0])[:50], np.sort(radii[1])[:50], atol=1e-4), "other seed, other outline"


run(globals())
