import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy

from harness import close, run, snapshot


def volume(name):
    obj = bpy.data.objects[name]
    bm = bmesh.new()
    bm.from_object(obj, bpy.context.evaluated_depsgraph_get())
    try:
        return bm.calc_volume()
    finally:
        bm.free()


def two_cubes(bridge, offset):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("add_primitive", type="cube", name="Cutter", size=2.0, location=offset)


def test_boolean_difference_cuts_a_corner(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("add_primitive", type="cube", name="Cutter", size=2.0, location=[1.0, 1.0, 1.0])
    result = bridge.ok("boolean", name="Box", cutter="Cutter")
    assert result["applied"] and result["cutter"] == "hide"
    close(volume("Box"), 7.0)
    box = bridge.info("Box")
    assert box["modifiers"] == []
    close(box["bounds"]["size"], [2.0, 2.0, 2.0])
    assert bridge.info("Cutter")["visible"] is False


def test_boolean_union_and_intersect(bridge):
    two_cubes(bridge, [1.0, 0.0, 0.0])
    bridge.ok("boolean", name="Box", cutter="Cutter", operation="union", cutter_action="delete")
    close(volume("Box"), 12.0)
    close(bridge.info("Box")["bounds"]["min"], [-1.0, -1.0, -1.0])
    assert "Cutter" not in bpy.data.objects
    bridge.ok("new_scene")
    two_cubes(bridge, [1.0, 0.0, 0.0])
    bridge.ok("boolean", name="Box", cutter="Cutter", operation="intersect", cutter_action="keep")
    close(volume("Box"), 4.0)
    close(bridge.info("Box")["bounds"]["min"], [0.0, -1.0, -1.0])
    assert bridge.info("Cutter")["visible"] is True


def test_boolean_live_keeps_a_modifier(bridge):
    two_cubes(bridge, [1.0, 0.0, 0.0])
    result = bridge.ok("boolean", name="Box", cutter="Cutter", apply=False)
    assert result["applied"] is False and result["modifier"] == "Boolean"
    assert result["mesh"]["vertices"] == 8
    close(volume("Box"), 4.0)


def test_boolean_refuses_bad_arguments(bridge):
    two_cubes(bridge, [1.0, 0.0, 0.0])
    bridge.refuse("boolean", "bad_args", name="Box", cutter="Box")
    bridge.refuse("boolean", "bad_args", name="Box", cutter="Cutter", apply=False, cutter_action="delete")
    bridge.refuse("boolean", "not_found", name="Box", cutter="Ghost")
    bridge.refuse("boolean", "bad_args", name="Box", cutter="Cutter", operation="xor")


def test_failing_boolean_leaves_the_scene_unchanged(bridge):
    two_cubes(bridge, [5.0, 0.0, 0.0])
    bridge.ok("add_material", name="Paint")
    bridge.ok("assign_material", name="Box", material="Paint")
    before = snapshot()
    message = bridge.refuse("boolean", "failed", name="Box", cutter="Cutter", operation="intersect", cutter_action="delete")
    assert "no faces" in message
    assert snapshot() == before
    bridge.refuse("boolean", "failed", name="Box", cutter="Cutter", operation="intersect", apply=False)
    assert snapshot() == before


def test_mirror_across_the_origin(bridge):
    bridge.ok("add_primitive", type="cube", name="Half", size=1.0)
    bridge.ok("set_origin", name="Half", to="cursor", point=[-1.0, 0.0, 0.0])
    result = bridge.ok("mirror", name="Half")
    assert result["evaluated_mesh"]["vertices"] == 16
    close(bridge.info("Half")["bounds"]["min"], [-2.5, -0.5, -0.5])
    result = bridge.ok("apply_modifier", name="Half", modifier=result["modifier"])
    assert result["mesh"]["vertices"] == 16


def test_mirror_refuses_bad_axes(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("mirror", "bad_args", name="Box", axes=["x", "x"])
    bridge.refuse("mirror", "bad_args", name="Box", axes=["w"])
    bridge.refuse("mirror", "bad_args", name="Box", mirror_object="Box")


def test_array_repeats_by_size_or_metres(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    result = bridge.ok("array", name="Box", count=3)
    assert result["evaluated_mesh"] == {"vertices": 24, "edges": 36, "faces": 18, "triangles": 36}
    close(bridge.info("Box")["bounds"]["size"], [3.0, 1.0, 1.0])
    bridge.ok("new_scene")
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    result = bridge.ok("array", name="Box", count=3, offset=[0.0, 0.0, 2.0], apply=True)
    assert result["mesh"]["vertices"] == 24
    close(bridge.info("Box")["bounds"]["size"], [1.0, 1.0, 5.0])


def test_array_refuses_bad_counts(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("array", "bad_args", name="Box", count=1)
    bridge.ok("add_primitive", type="ico_sphere", name="Ball", subdivisions=7)
    bridge.refuse("array", "failed", name="Ball", count=100)


def test_solidify_thickens_a_plane(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=2.0)
    result = bridge.ok("solidify", name="Sheet", thickness=0.1)
    assert result["evaluated_mesh"]["vertices"] == 8 and result["evaluated_mesh"]["faces"] == 6
    close(bridge.info("Sheet")["bounds"]["min"], [-1.0, -1.0, -0.1])
    close(volume("Sheet"), 0.4)


def test_solidify_refuses_zero(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet")
    bridge.refuse("solidify", "bad_args", name="Sheet", thickness=0.0)


def test_decimate_halves_the_faces(bridge):
    bridge.ok("add_primitive", type="sphere", name="Ball")
    result = bridge.ok("decimate", name="Ball", ratio=0.5, apply=True)
    assert 400 <= result["mesh"]["triangles"] <= 490, result["mesh"]


def test_decimate_refuses_zero_ratio(bridge):
    bridge.ok("add_primitive", type="sphere", name="Ball")
    bridge.refuse("decimate", "bad_args", name="Ball", ratio=0.0)
    bridge.refuse("decimate", "bad_args", name="Ball", ratio=1.5)


def test_apply_modifier_applies_the_whole_stack(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    bridge.ok("array", name="Box", count=2)
    bridge.ok("solidify", name="Box", thickness=0.05)
    result = bridge.ok("apply_modifier", name="Box")
    assert result["applied"] == ["Array", "Solidify"]
    assert bridge.info("Box")["modifiers"] == []


def test_apply_modifier_refuses_missing(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("apply_modifier", "bad_args", name="Box")
    bridge.ok("array", name="Box", count=2)
    bridge.refuse("apply_modifier", "not_found", name="Box", modifier="Bevel")


run(globals())
