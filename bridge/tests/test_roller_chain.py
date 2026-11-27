import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import is_closed_manifold, settled_snapshot, vertices

from blendworks_bridge import chain

PITCH = 0.0127
FRAME = [[0.0, 0.0, 0.0], [0.2, 0.0, 0.0], [0.2, 0.1, 0.0], [0.0, 0.1, 0.0]]


def test_closed_chain_uses_an_even_number_of_links(bridge):
    result = bridge.ok("roller_chain", name="Chain", pitch=PITCH, waypoints=FRAME, closed=True)
    assert result["links"] == 48 and result["pins"] == 48 and result["closed"] is True
    close(result["path_length"], 0.6, 1e-9)
    close(result["pitch_actual"], 0.6 / 48, 1e-9)
    assert result["manifold"] is True and is_closed_manifold("Chain")


def test_chain_dimensions_follow_the_pitch(bridge):
    bridge.ok("roller_chain", name="Chain", pitch=PITCH, waypoints=FRAME, closed=True)
    inner = 0.625 * PITCH / 2.0
    outer_face = inner + 0.1 * PITCH + 0.02 * PITCH
    half = outer_face + 0.1 * PITCH + 0.31 * PITCH * 0.2
    close(bpy.data.objects["Chain"].dimensions[2], 2 * half, 1e-6)
    xs = [v.x for v in vertices("Chain")]
    assert min(xs) < -0.5 * 0.8 * PITCH + 1e-6 and max(xs) > 0.2


def test_open_chain_keeps_the_nominal_pitch(bridge):
    result = bridge.ok("roller_chain", name="Run", pitch=PITCH, waypoints=[[0, 0, 1], [0.1, 0, 1]])
    assert result["links"] == 7 and result["pins"] == 8 and result["closed"] is False
    close(result["pitch_actual"], PITCH, 1e-9)
    assert result["manifold"] is True


def test_chain_wraps_around_wheels(bridge):
    wheels = [{"centre": [0.0, 0.0, 0.0], "radius": 0.04}, {"centre": [0.2, 0.0, 0.0], "radius": 0.04}]
    result = bridge.ok("roller_chain", name="Belt", pitch=PITCH, wheels=wheels)
    close(result["path_length"], 0.4 + math.tau * 0.04, 0.003)
    assert result["closed"] is True and result["links"] % 2 == 0 and result["links"] == 52
    assert result["manifold"] is True
    xs = [v.x for v in vertices("Belt")]
    assert min(xs) < -0.04 and max(xs) > 0.24


def test_chain_follows_a_curve_and_a_plane_normal(bridge):
    bridge.ok("curve_from_points", name="Track", points=[[0, 0, 0], [0.2, 0, 0], [0.2, 0.1, 0], [0, 0.1, 0]], closed=True)
    result = bridge.ok("roller_chain", name="Chain", pitch=PITCH, curve="Track")
    assert result["closed"] is True and result["links"] == 48
    bridge.ok("roller_chain", name="Upright", pitch=PITCH, waypoints=[[0, 0, 0], [0, 0.1, 0]], plane_normal=[1.0, 0.0, 0.0])
    dims = bpy.data.objects["Upright"].dimensions
    assert dims[0] > dims[2]


def test_chain_refuses_bad_arguments(bridge):
    wheels = [{"centre": [0.0, 0.0, 0.0], "radius": 0.04}, {"centre": [0.2, 0.0, 0.0], "radius": 0.04}]
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH)
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, wheels=wheels, waypoints=FRAME)
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, wheels=wheels, closed=False)
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, wheels=[wheels[0], {"centre": [0.2, 0.0, 0.5], "radius": 0.04}])
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, waypoints=[[0, 0, 0], [0.005, 0, 0]])
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, waypoints=[[0, 0, 0], [0.1, 0, 0]], plane_normal=[1, 0, 0])
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, waypoints=FRAME, closed=True, pin_diameter=0.01)
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=0.0005, waypoints=[[0, 0, 0], [3, 0, 0]])
    bridge.refuse("roller_chain", "not_found", name="A", pitch=PITCH, curve="Ghost")
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, waypoints=FRAME, plane_normal=[0, 0, 0])


def test_chain_counts_its_links_before_placing_any_pin(bridge):
    placed = []
    original = chain.point_along

    def refuse_to_place(points, closed, distance):
        placed.append(distance)
        raise AssertionError("a pin was placed before the link count was checked")

    wheels = [{"centre": [0.0, 0.0, 0.0], "radius": 100_000.0}, {"centre": [200_000.0, 0.0, 0.0], "radius": 100_000.0}]
    chain.point_along = refuse_to_place
    try:
        message = bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, wheels=wheels)
    finally:
        chain.point_along = original
    assert placed == []
    assert "pitch 0.0127" in message and "chain_links limit is 2000" in message and "Raise pitch" in message, message
    assert "A" not in bpy.data.objects


def test_failed_chain_leaves_the_scene_unchanged(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    before = settled_snapshot()
    bridge.refuse("roller_chain", "bad_args", name="A", pitch=PITCH, waypoints=[[0, 0, 0], [0.005, 0, 0]])
    assert settled_snapshot() == before


run(globals())
