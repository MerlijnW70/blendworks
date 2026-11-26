import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from harness import run
from liquid_helpers import cup, mesh_points, ortho, top_faces
from sky_helpers import luminance, render

from blendworks_bridge import liquid_presets
from blendworks_bridge.liquid_mesh import mesh_volume, object_arrays

RADIUS = 0.04


def liquid_volume(name):
    points, triangles = object_arrays(bpy.data.objects[name])
    return mesh_volume(points, triangles)


def clearance(liquid, container):
    tree = BVHTree.FromObject(bpy.data.objects[container], bpy.context.evaluated_depsgraph_get())
    return min(tree.find_nearest(Vector(point))[3] for point in mesh_points(liquid))


def test_a_cup_takes_the_volume_asked_and_the_surface_never_crosses_the_wall(bridge):
    cup(bridge, "Cup", RADIUS, 0.12, wall=0.002)
    for litres in (0.1, 0.35):
        name = f"Water{int(litres * 1000)}"
        result = bridge.ok("liquid_fill", container="Cup", preset="water_fresh", volume=litres, name=name)
        measured = liquid_volume(name)
        assert abs(measured - litres * 1e-3) < 0.01 * litres * 1e-3, (measured, litres)
        assert abs(result["volume_litres"] - litres) < 0.01 * litres
        points = mesh_points(name)
        assert np.hypot(points[:, 0], points[:, 1]).max() < RADIUS - 0.5 * result["gap"]
        assert points[:, 2].min() > 0.002
        assert clearance(name, "Cup") > 0.6 * result["gap"], clearance(name, "Cup")
        flat = (litres * 1e-3) / (math.pi * RADIUS ** 2) + 0.002
        assert abs(result["level"] - flat) < 0.004, (result["level"], flat)
    capacity = math.pi * RADIUS ** 2 * (0.12 - 0.002)
    assert abs(result["capacity_litres"] * 1e-3 - capacity) < 0.06 * capacity
    message = bridge.refuse("liquid_fill", "bad_args", container="Cup", preset="water_fresh", volume=0.7, name="Flood")
    assert "does not fit" in message


def cap_heights(name):
    mesh = bpy.data.objects[name].data
    flags = top_faces(name)
    corners = {index for polygon, top in zip(mesh.polygons, flags) if top for index in polygon.vertices}
    points = mesh_points(name)[sorted(corners)]
    return points


def test_the_meniscus_rises_by_the_capillary_rise_and_mercury_like_metal_sinks(bridge):
    cup(bridge, "Cup", RADIUS, 0.12, wall=0.002)
    water = bridge.ok("liquid_fill", container="Cup", preset="water_fresh", level=0.06, name="Water")
    entry = liquid_presets.PRESETS["water_fresh"]
    capillary = liquid_presets.capillary_length(entry)
    rise = capillary * math.sqrt(2.0 * (1.0 - math.sin(math.radians(entry["contact_angle"]))))
    cap = cap_heights("Water")
    assert abs((cap[:, 2].max() - cap[:, 2].min()) - rise) < 0.15 * rise, (cap[:, 2].max() - cap[:, 2].min(), rise)
    edge = np.hypot(cap[:, 0], cap[:, 1]) > RADIUS - 0.0005
    assert cap[edge, 2].mean() > cap[~edge, 2].mean()
    assert abs(water["meniscus"] - rise) < 1e-6
    bridge.ok("delete", names=["Water"])
    metal = bridge.ok("liquid_fill", container="Cup", preset="molten_metal", level=0.06, name="Metal")
    assert metal["meniscus"] < 0.0
    cap = cap_heights("Metal")
    edge = np.hypot(cap[:, 0], cap[:, 1]) > RADIUS - 0.0005
    assert cap[edge, 2].mean() < cap[~edge, 2].mean()


def test_a_tilted_surface_leans_by_its_angle(bridge):
    cup(bridge, "Cup", RADIUS, 0.12, wall=0.002)
    bridge.ok("liquid_fill", container="Cup", preset="wine", volume=0.25, name="Wine", tilt={"angle": 15.0, "direction": 90.0}, meniscus=False)
    cap = cap_heights("Wine")
    slope, _ = np.polyfit(cap[:, 0], cap[:, 2], 1)
    assert abs(math.degrees(math.atan(slope)) - 15.0) < 1.0, math.degrees(math.atan(slope))
    assert abs(liquid_volume("Wine") - 0.25e-3) < 0.01 * 0.25e-3


def test_a_bottle_fills_below_its_shoulder(bridge):
    profile = [[0.0, 0.0], [0.035, 0.0], [0.035, 0.18], [0.013, 0.23], [0.013, 0.28], [0.01, 0.28], [0.01, 0.232], [0.032, 0.18], [0.032, 0.003], [0.0, 0.003]]
    bridge.ok("lathe", name="Bottle", profile=profile, segments=48)
    result = bridge.ok("liquid_fill", container="Bottle", preset="oil", fill=0.5, name="Oil")
    assert abs(result["volume_litres"] - 0.5 * result["capacity_litres"]) < 0.01 * result["capacity_litres"]
    assert result["capacity_litres"] > math.pi * 0.032 ** 2 * 0.177 * 1e3
    assert clearance("Oil", "Bottle") > 0.6 * result["gap"]


def test_beer_gets_a_foam_head_and_bubbles_and_glass_gets_clear_shadows(bridge):
    cup(bridge, "Glass", RADIUS, 0.14, wall=0.002)
    result = bridge.ok("liquid_fill", container="Glass", preset="beer", volume=0.4, name="Beer", glass=True)
    foam = mesh_points(result["foam"])
    beer = mesh_points("Beer")
    assert foam[:, 2].max() - beer[:, 2].max() > 0.6 * liquid_presets.PRESETS["beer"]["foam"]["height"]
    assert result["bubbles"]["count"] > 50
    bubbles = mesh_points(result["bubbles"]["object"])
    assert bubbles[:, 2].max() < beer[:, 2].max() and np.hypot(bubbles[:, 0], bubbles[:, 1]).max() < RADIUS
    material = bpy.data.objects["Glass"].data.materials[0]
    assert material.get("blendworks_liquid") == "glass"
    assert any(node.type == "LIGHT_PATH" for node in material.node_tree.nodes)


def test_drips_a_pour_stream_and_a_spill_of_a_given_area(bridge):
    cup(bridge, "Cup", RADIUS, 0.1, wall=0.002)
    bridge.ok("add_primitive", type="plane", name="Table", size=2.0)
    result = bridge.ok("liquid_fill", container="Cup", preset="honey", volume=0.2, name="Honey", drips={"count": 4}, pour={"start": [0.0, 0.0, 0.3], "velocity": [0.0, 0.0, -0.2], "radius": 0.005})
    assert result["drips"]["count"] == 4
    drips = mesh_points(result["drips"]["object"])
    assert np.hypot(drips[:, 0], drips[:, 1]).min() > RADIUS
    pour = result["pour"]
    assert pour["landed"] and pour["end"][2] < 0.1
    assert pour["radius_end"] < pour["radius_start"]
    fall = 0.3 - pour["end"][2]
    wanted = math.sqrt(0.04 + 2.0 * 9.81 * fall)
    assert abs(pour["fall_speed"] - wanted) < 0.05 * wanted, (pour["fall_speed"], wanted)
    assert abs(pour["radius_end"] - 0.005 * math.sqrt(0.2 / pour["fall_speed"])) < 1e-4
    spill = bridge.ok("liquid_fill", preset="coffee", name="Spill", spill={"point": [0.3, 0.0, 0.0], "area": 0.015, "contact_angle": 60.0})["spill"]
    assert abs(spill["area"] - 0.015) < 1e-9
    entry = liquid_presets.PRESETS["coffee"]
    wanted = 2.0 * liquid_presets.capillary_length(entry) * math.sin(math.radians(30.0))
    assert abs(spill["thickness"] - wanted) < 1e-6
    points = mesh_points("Spill")
    assert points[:, 2].max() < wanted + 1e-4 and points[:, 2].max() > 0.5 * wanted



def top_sheet(name):
    obj = bpy.data.objects[name]
    points = mesh_points(name)
    top = top_faces(name)
    triangles = np.array([list(polygon.vertices) for polygon in obj.data.polygons])[top]
    return points, triangles


def test_a_coffee_spill_is_a_thin_film_without_holes_and_with_a_darker_rim(bridge):
    """A spill is one flat disc of film 1-3 mm thick: no holes, no folds, thinner at the contact line, a darker coffee ring at it."""
    bridge.ok("add_primitive", type="plane", name="Table", size=1.0)
    bridge.ok("add_material", name="White", base_color=[0.8, 0.8, 0.8], roughness=0.9)
    bridge.ok("assign_material", name="Table", material="White")
    result = bridge.ok("liquid_fill", preset="coffee", name="Spill", spill={"point": [0.0, 0.0, 0.0], "area": 0.03, "contact_angle": 35.0}, seed=4)
    spill = result["spill"]
    assert 0.001 <= spill["thickness"] <= 0.003, spill
    points, triangles = top_sheet("Spill")
    corners = points[triangles]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    assert np.all(cross[:, 2] > 0.0), "every face of the film faces up: no folds"
    projected = 0.5 * cross[:, 2].sum()
    assert abs(projected - spill["area"]) < 1e-3 * spill["area"], (projected, spill["area"])
    edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    used = np.unique(triangles)
    assert len(used) - len(unique) + len(triangles) == 1, "the film is a disc: Euler characteristic 1, so no holes"
    border = unique[counts == 1]
    following = {}
    for a, b in border.tolist():
        following.setdefault(a, []).append(b)
        following.setdefault(b, []).append(a)
    start = int(border[0, 0])
    loop, previous, current = 1, None, start
    while True:
        step = [vertex for vertex in following[current] if vertex != previous][0]
        previous, current = current, step
        if current == start:
            break
        loop += 1
    assert loop == len(border), "the film has a single outline"
    height = points[used, 2]
    assert height.max() <= spill["thickness"] + 1e-6 and height.max() >= 0.95 * spill["thickness"] - 1e-4
    rim = np.unique(border)
    assert height[np.searchsorted(used, rim)].max() < 0.05 * spill["thickness"], "the film thins to nothing at its contact line"
    radius = np.hypot(points[rim, 0], points[rim, 1])
    assert radius.max() / radius.min() > 1.25, "the outline is irregular, not a circle"
    bridge.ok("add_light", type="sun", name="Sun", rotation=[40.0, 0.0, 20.0], energy=3.0)
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)
    ortho(bridge, "Top", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 0.26)
    pixels = luminance(render(bridge, "spill_film", 512, 32, "Top"))
    bare = np.median(pixels[:12].ravel())
    film = pixels < 0.85 * bare
    middle = np.median(pixels[eroded(film, 16)])
    assert 0.03 * bare < middle < 0.5 * bare, ("translucent brown film, not black and not clear", middle / bare)
    rim = pixels[eroded(film, 1) & ~eroded(film, 3)].mean()
    inside = pixels[eroded(film, 3) & ~eroded(film, 8)].mean()
    assert rim < 0.9 * inside, ("a darker coffee ring at the contact line than the thin film just inside it", rim / inside)


def eroded(mask, steps):
    """The mask shrunk by steps pixels (4-neighbour erosion)."""
    for _ in range(steps):
        inner = mask.copy()
        inner[1:, :] &= mask[:-1, :]
        inner[:-1, :] &= mask[1:, :]
        inner[:, 1:] &= mask[:, :-1]
        inner[:, :-1] &= mask[:, 1:]
        mask = inner
    return mask


run(globals())
