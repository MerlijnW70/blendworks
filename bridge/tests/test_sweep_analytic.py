import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

from harness import close, run
from kit_helpers import euler, is_closed_manifold, vertices, volume

WIDTH, HEIGHT = 0.02, 0.006
PROFILE_AREA = WIDTH * HEIGHT
RING = {"preset": "rectangle", "width": WIDTH, "height": HEIGHT}


def segments(radius, sweep, tolerance, minimum=1):
    return max(minimum, math.ceil(sweep / (2 * math.acos(1 - tolerance / radius)) - 1e-9))


def ring_centres(name, count, size=4):
    points = vertices(name)
    return [sum(points[k * size : (k + 1) * size], Vector()) / size for k in range(count)]


def nearest_other(name):
    points = vertices(name)
    tree = KDTree(len(points))
    for index, point in enumerate(points):
        tree.insert(point, index)
    tree.balance()
    return min(tree.find_n(point, 2)[1][2] for point in points)


def test_circle_sweep_has_the_analytic_length_and_volume(bridge):
    radius, tolerance = 0.1, 0.0002
    count = segments(radius, math.tau, tolerance, 8)
    assert count == 50
    result = bridge.ok("sweep", name="Hoop", **RING, circle={"radius": radius, "tolerance": tolerance})
    polygon = 2 * count * radius * math.sin(math.pi / count)
    close(result["length"], polygon, 1e-6)
    close(volume("Hoop"), PROFILE_AREA * polygon, 1e-9)
    close(result["path"]["analytic_length"], math.tau * radius, 1e-6)
    assert abs(result["length"] / (math.tau * radius) - 1.0) < (math.pi / count) ** 2 / 6 * 1.01
    assert abs(volume("Hoop") / (PROFILE_AREA * math.tau * radius) - 1.0) < (math.pi / count) ** 2 / 6 * 1.01
    assert result["path"]["segments"] == count and result["path"]["chord_error"] <= tolerance
    assert result["closed"] is True and result["manifold"] is True


def test_circle_sweep_closes_without_a_seam(bridge):
    radius = 0.1
    result = bridge.ok("sweep", name="Hoop", **RING, circle={"radius": radius})
    count = result["path"]["segments"]
    assert result["mesh"]["vertices"] == count * 4 and result["mesh"]["faces"] == count * 4
    assert euler("Hoop") == 0 and is_closed_manifold("Hoop")
    assert nearest_other("Hoop") > 1e-3
    centres = ring_centres("Hoop", result["rings"])
    chord = 2 * radius * math.sin(math.pi / count)
    for k in range(count):
        close((centres[k] - centres[k - 1]).length, chord, 1e-6)
        close(centres[k].length, radius, 1e-6)


def test_circle_profile_height_follows_the_axis(bridge):
    bridge.ok("sweep", name="Hoop", **RING, circle={"radius": 0.1})
    close(list(bpy.data.objects["Hoop"].dimensions), [0.22, 0.22, HEIGHT], 1e-3)
    close(bpy.data.objects["Hoop"].dimensions[2], HEIGHT, 1e-6)
    bridge.ok("sweep", name="Standing", **RING, circle={"radius": 0.1, "axis": [1, 0, 0], "centre": [0, 0, 1]})
    close(list(bpy.data.objects["Standing"].dimensions), [HEIGHT, 0.22, 0.22], 1e-3)
    close(bpy.data.objects["Standing"].dimensions[0], HEIGHT, 1e-6)
    centres = ring_centres("Standing", 50)
    assert all(abs(point.x) < 1e-6 and abs((point - Vector((0, 0, 1))).length - 0.1) < 1e-6 for point in centres)


def test_circle_starts_at_start_angle_around_the_reference(bridge):
    result = bridge.ok("sweep", name="Hoop", **RING, circle={"radius": 0.1, "start_angle": 30.0})
    first = ring_centres("Hoop", result["rings"])[0]
    close(list(first), [0.1 * math.cos(math.radians(30)), 0.1 * math.sin(math.radians(30)), 0.0], 1e-6)
    bridge.ok("sweep", name="Turned", **RING, circle={"radius": 0.1, "reference": [0, 1, 0]})
    close(list(ring_centres("Turned", 50)[0]), [0.0, 0.1, 0.0], 1e-6)


def test_arc_sweep_covers_exactly_the_requested_angles(bridge):
    radius, tolerance = 0.5, 0.001
    count = segments(radius, math.pi / 2, tolerance)
    result = bridge.ok("sweep", name="Bow", **RING, arc={"radius": radius, "start_angle": 0.0, "end_angle": 90.0, "tolerance": tolerance})
    assert result["path"]["segments"] == count and result["rings"] == count + 1 and result["closed"] is False
    centres = ring_centres("Bow", result["rings"])
    close(list(centres[0]), [radius, 0, 0], 1e-6)
    close(list(centres[-1]), [0, radius, 0], 1e-6)
    polygon = 2 * count * radius * math.sin(math.pi / 4 / count)
    close(result["length"], polygon, 1e-6)
    close(result["path"]["analytic_length"], radius * math.pi / 2, 1e-6)
    close(volume("Bow"), PROFILE_AREA * polygon, 1e-9)
    assert result["manifold"] is True and result["mesh"]["faces"] == count * 4 + 2


def test_arc_turns_the_other_way_when_the_end_is_below_the_start(bridge):
    result = bridge.ok("sweep", name="Bow", **RING, arc={"radius": 0.5, "start_angle": 0.0, "end_angle": -90.0})
    centres = ring_centres("Bow", result["rings"])
    close(list(centres[-1]), [0, -0.5, 0], 1e-6)


def test_helix_rises_by_the_pitch_each_turn(bridge):
    radius, pitch, turns, tolerance = 0.05, 0.02, 2.5, 0.0002
    count = segments(radius, math.tau * turns, tolerance)
    result = bridge.ok("sweep", name="Spring", **RING, helix={"radius": radius, "pitch": pitch, "turns": turns, "tolerance": tolerance})
    centres = ring_centres("Spring", result["rings"])
    assert result["path"]["segments"] == count and len(centres) == count + 1
    close(list(centres[0]), [radius, 0, 0], 1e-6)
    close(list(centres[-1]), [-radius, 0, pitch * turns], 1e-6)
    step = math.hypot(2 * radius * math.sin(math.tau * turns / count / 2), pitch * turns / count)
    close(result["length"], count * step, 1e-6)
    close(result["path"]["analytic_length"], math.hypot(math.tau * radius, pitch) * turns, 1e-6)
    assert abs(result["length"] / result["path"]["analytic_length"] - 1.0) < (math.tau * turns / count) ** 2 / 24 * 1.05
    assert result["manifold"] is True


def test_helix_handedness_decides_the_turning_direction(bridge):
    right = bridge.ok("sweep", name="Right", **RING, helix={"radius": 0.05, "pitch": 0.02, "turns": 0.75})
    left = bridge.ok("sweep", name="Left", **RING, helix={"radius": 0.05, "pitch": 0.02, "turns": 0.75, "handed": "left"})
    close(list(ring_centres("Right", right["rings"])[-1]), [0, -0.05, 0.015], 1e-6)
    close(list(ring_centres("Left", left["rings"])[-1]), [0, 0.05, 0.015], 1e-6)


def test_analytic_sweeps_refuse_what_does_not_fit(bridge):
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 0.1}, arc={"radius": 0.1, "end_angle": 90.0})
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 0.1}, waypoints=[[0, 0, 0], [1, 0, 0]])
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 0.1}, closed=False)
    bridge.refuse("sweep", "bad_args", name="A", **RING, helix={"radius": 0.1, "pitch": 0.02, "turns": 1.0}, closed=True)
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 0.1}, fillet_radius=0.01)
    bridge.refuse("sweep", "bad_args", name="A", **RING, arc={"radius": 0.1, "end_angle": 360.0})
    bridge.refuse("sweep", "bad_args", name="A", **RING, arc={"radius": 0.1, "start_angle": 20.0, "end_angle": 20.0})
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 0.1, "axis": [0, 0, 0]})
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 0.1, "reference": [0, 0, 5]})
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 1.0, "tolerance": 1e-9})
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 0.1, "colour": 1})
    bridge.refuse("sweep", "bad_args", name="A", **RING, circle={})
    bridge.refuse("sweep", "bad_args", name="A", **RING, helix={"radius": 0.1, "turns": 1.0})
    message = bridge.refuse("sweep", "bad_args", name="A", **RING, circle={"radius": 1.0, "tolerance": 1e-9})
    assert "raise the tolerance" in message


run(globals())
