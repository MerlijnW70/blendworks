import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Vector

from harness import close, run


def forward(name):
    obj = bpy.data.objects[name]
    return (obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


def test_add_light_of_each_type(bridge):
    for kind in ("point", "sun", "spot", "area"):
        result = bridge.ok("add_light", type=kind, name=kind.title(), energy=50.0, color=[1.0, 0.9, 0.8])
        assert result["type"] == kind and result["energy"] == 50.0
        assert bpy.data.objects[kind.title()].data.type == kind.upper()
    bridge.ok("add_light", type="spot", name="Narrow", spot_angle=30.0)
    close(math.degrees(bpy.data.objects["Narrow"].data.spot_size), 30.0)


def test_add_light_refuses_bad_arguments(bridge):
    bridge.refuse("add_light", "bad_args", type="laser")
    bridge.refuse("add_light", "bad_args", type="point", spot_angle=30.0)
    bridge.refuse("add_light", "bad_args", type="point", energy=-1.0)


def test_add_camera_aims_and_becomes_active(bridge):
    result = bridge.ok("add_camera", name="Cam", location=[0.0, -10.0, 0.0], target=[0.0, 0.0, 0.0])
    assert result["active"] is True
    assert bpy.context.scene.camera.name == "Cam"
    close(list(forward("Cam")), [0.0, 1.0, 0.0])
    bridge.ok("add_camera", name="Ortho", orthographic_scale=4.0, active=False)
    assert bpy.data.objects["Ortho"].data.type == "ORTHO"
    assert bpy.context.scene.camera.name == "Cam"


def test_add_camera_refuses_rotation_with_target(bridge):
    bridge.refuse("add_camera", "bad_args", rotation=[0.0, 0.0, 0.0], target=[0.0, 0.0, 0.0])
    bridge.refuse("add_camera", "bad_args", lens=0.5)


def test_look_at_points_minus_z_at_the_target(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", location=[0.0, 0.0, 1.0])
    bridge.ok("add_light", type="spot", name="Spot", location=[3.0, 0.0, 1.0])
    bridge.ok("look_at", name="Spot", target="Box")
    close(list(forward("Spot")), [-1.0, 0.0, 0.0])
    result = bridge.ok("look_at", name="Spot", point=[3.0, 0.0, -5.0])
    close(list(forward("Spot")), [0.0, 0.0, -1.0])
    close(result["looking_at"], [3.0, 0.0, -5.0])


def test_look_at_refuses_ambiguous_targets(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("look_at", "bad_args", name="Box")
    bridge.refuse("look_at", "bad_args", name="Box", target="Box")
    bridge.refuse("look_at", "bad_args", name="Box", target="Box", point=[1.0, 0.0, 0.0])
    bridge.refuse("look_at", "bad_args", name="Box", point=[0.0, 0.0, 0.0])


def test_set_world_colour_and_strength(bridge):
    result = bridge.ok("set_world", color=[0.1, 0.2, 0.3], strength=0.5)
    close(result["color"], [0.1, 0.2, 0.3])
    assert result["strength"] == 0.5
    result = bridge.ok("set_world", strength=2.0)
    close(result["color"], [0.1, 0.2, 0.3])


def test_set_world_refuses_nothing_to_set(bridge):
    bridge.refuse("set_world", "bad_args")
    bridge.refuse("set_world", "bad_args", strength=-1.0)


run(globals())
