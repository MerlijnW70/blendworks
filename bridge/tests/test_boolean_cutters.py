import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import euler, is_closed_manifold, regular_polygon_area, settled_snapshot, volume


def box(bridge, name="Box", size=2.0, location=(0.0, 0.0, 0.0), scale=None):
    bridge.ok("add_primitive", type="cube", name=name, size=size, location=list(location))
    if scale is not None:
        bridge.ok("transform", name=name, scale=list(scale))


def cross_cutters(bridge):
    box(bridge, "BarX", 1.0, scale=[4.0, 1.0, 0.5])
    box(bridge, "BarY", 1.0, scale=[1.0, 4.0, 0.5])


def test_cylinders_cut_out_of_a_box_match_the_analytic_volume(bridge):
    box(bridge)
    names = []
    for ix in (-0.6, 0.0, 0.6):
        for iy in (-0.6, 0.0, 0.6):
            name = f"Cut{len(names)}"
            bridge.ok("add_primitive", type="cylinder", name=name, radius=0.2, depth=4.0, segments=16, location=[ix, iy, 0.0])
            names.append(name)
    result = bridge.ok("boolean", name="Box", cutters=names, manifold=True)
    expected = 8.0 - 9 * regular_polygon_area(0.2, 16) * 2.0
    close(volume("Box"), expected, 1e-4)
    close(result["volume"], expected, 1e-4)
    assert result["cutters"] == 9 and result["manifold"] is True and result["applied"] is True
    assert euler("Box") == 2 - 2 * 9
    assert is_closed_manifold("Box")
    assert all(bpy.data.objects[name].hide_render for name in names)


def test_overlapping_cutters_are_unioned_before_the_cut(bridge):
    box(bridge)
    cross_cutters(bridge)
    bridge.ok("boolean", name="Box", cutters=["BarX", "BarY"], manifold=True)
    close(volume("Box"), 8.0 - 1.5, 1e-5)
    assert is_closed_manifold("Box")


def test_cutters_work_for_union_and_intersect_too(bridge):
    box(bridge)
    cross_cutters(bridge)
    bridge.ok("boolean", name="Box", cutters=["BarX", "BarY"], operation="intersect", cutter_action="keep", manifold=True)
    close(volume("Box"), 1.5, 1e-5)
    assert not bpy.data.objects["BarX"].hide_get()
    bridge.ok("new_scene")
    box(bridge)
    cross_cutters(bridge)
    bridge.ok("boolean", name="Box", cutters=["BarX", "BarY"], operation="union", cutter_action="delete", manifold=True)
    close(volume("Box"), 10.0, 1e-5)
    assert "BarX" not in bpy.data.objects and "BarY" not in bpy.data.objects


def test_no_stand_in_object_or_mesh_is_left_behind(bridge):
    box(bridge)
    cross_cutters(bridge)
    bridge.ok("boolean", name="Box", cutters=["BarX", "BarY"])
    assert "Cutters" not in bpy.data.objects and "Cutters" not in bpy.data.meshes
    bridge.ok("new_scene")
    box(bridge)
    box(bridge, "B", location=(2.0, 2.0, 0.0))
    bridge.refuse("boolean", "failed", name="Box", cutters=["B"], operation="union", manifold=True)
    assert "Cutters" not in bpy.data.objects and "Cutters" not in bpy.data.meshes


def test_a_non_manifold_result_is_refused_when_manifold_is_asked_for(bridge):
    box(bridge)
    box(bridge, "B", location=(2.0, 2.0, 0.0))
    before = settled_snapshot()
    message = bridge.refuse("boolean", "failed", name="Box", cutters=["B"], operation="union", manifold=True)
    assert "not manifold" in message and "edge" in message
    assert settled_snapshot() == before
    allowed = bridge.ok("boolean", name="Box", cutters=["B"], operation="union")
    assert allowed["manifold"] is False and allowed["volume"] is None


def test_single_cutter_can_also_demand_a_manifold_result(bridge):
    box(bridge)
    box(bridge, "B", location=(2.0, 2.0, 0.0))
    before = settled_snapshot()
    bridge.refuse("boolean", "failed", name="Box", cutter="B", operation="union", manifold=True)
    assert settled_snapshot() == before
    box(bridge, "C", location=(1.0, 0.0, 0.0))
    result = bridge.ok("boolean", name="Box", cutter="C", operation="union", manifold=True)
    assert result["manifold"] is True
    close(result["volume"], 12.0, 1e-5)


def test_live_boolean_reports_manifoldness_of_the_evaluated_mesh(bridge):
    box(bridge)
    box(bridge, "C", location=(1.0, 0.0, 0.0))
    result = bridge.ok("boolean", name="Box", cutter="C", apply=False, operation="union", manifold=True)
    assert result["applied"] is False and result["manifold"] is True
    close(result["volume"], 12.0, 1e-5)


def test_boolean_cutters_refuse_bad_arguments(bridge):
    box(bridge)
    cross_cutters(bridge)
    bridge.ok("curve_from_points", name="Rail", points=[[0, 0, 0], [1, 0, 0]])
    bridge.refuse("boolean", "bad_args", name="Box")
    bridge.refuse("boolean", "bad_args", name="Box", cutter="BarX", cutters=["BarY"])
    bridge.refuse("boolean", "bad_args", name="Box", cutters=["BarX", "BarX"])
    bridge.refuse("boolean", "bad_args", name="Box", cutters=["BarX", "Box"])
    bridge.refuse("boolean", "bad_args", name="Box", cutters=["BarX", "BarY"], solver="float")
    bridge.refuse("boolean", "bad_args", name="Box", cutters=["BarX", "BarY"], apply=False)
    bridge.refuse("boolean", "not_found", name="Box", cutters=["BarX", "Ghost"])
    bridge.refuse("boolean", "bad_args", name="Box", cutters=["BarX", "Rail"])
    bridge.refuse("boolean", "bad_args", name="Box", cutters=[])
    bridge.refuse("boolean", "bad_args", name="Box", cutter="BarX", merge_distance=0.0)


def test_failed_multi_cutter_boolean_leaves_the_scene_unchanged(bridge):
    box(bridge)
    cross_cutters(bridge)
    before = settled_snapshot()
    bridge.refuse("boolean", "not_found", name="Box", cutters=["BarX", "Ghost"])
    bridge.refuse("boolean", "bad_args", name="Box", cutters=["BarX", "BarY"], apply=False)
    assert settled_snapshot() == before


run(globals())
