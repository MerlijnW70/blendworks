import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import settled_snapshot, triangle_total, vertices

BOLT_TRIANGLES = 8 * 2 + 2 * 6
BOLT_VERTICES = 16


def bolt(bridge):
    bridge.ok("add_primitive", type="cylinder", name="Bolt", radius=0.01, depth=0.02, segments=8)


def copies(name):
    return sorted((obj for obj in bpy.data.objects if obj.name.startswith(f"{name}_")), key=lambda obj: obj.name)


def location(obj):
    return list(obj.matrix_world.translation)


def axis(obj, column):
    return list(obj.matrix_world.to_3x3().col[column].normalized())


def test_count_along_a_curve_at_a_spacing(bridge):
    bolt(bridge)
    bridge.ok("curve_from_points", name="Rail", points=[[0, 0, 0], [3, 0, 0]])
    result = bridge.ok("instances", source="Bolt", name="Row", curve="Rail", spacing=0.5)
    assert result["count"] == 7 and result["realized"] is False and result["shared_mesh"] == "Bolt"
    row = copies("Row")
    assert len(row) == 7
    for index, obj in enumerate(row):
        close(location(obj), [0.5 * index, 0.0, 0.0], 1e-6)
        assert obj.data is bpy.data.objects["Bolt"].data and obj.parent.name == "Row"
    assert bpy.data.objects["Bolt"].data.users == 8
    short = bridge.ok("instances", source="Bolt", name="Short", curve="Rail", spacing=0.7)
    assert short["count"] == 5
    close(location(copies("Short")[-1]), [2.8, 0.0, 0.0], 1e-6)
    start = bridge.ok("instances", source="Bolt", name="Late", curve="Rail", spacing=0.7, offset=0.5)
    assert start["count"] == 4


def test_closed_curve_spaces_instances_without_a_duplicate_at_the_seam(bridge):
    bolt(bridge)
    bridge.ok("curve_from_points", name="Frame", points=[[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], closed=True)
    assert bridge.ok("instances", source="Bolt", name="Ring", curve="Frame", spacing=0.5)["count"] == 8
    by_count = bridge.ok("instances", source="Bolt", name="Four", curve="Frame", count=4)
    assert by_count["count"] == 4
    close(location(copies("Four")[1]), [1.0, 0.0, 0.0], 1e-6)
    close(location(copies("Four")[2]), [1.0, 1.0, 0.0], 1e-6)


def test_count_spreads_over_an_open_path_including_both_ends(bridge):
    bolt(bridge)
    bridge.ok("instances", source="Bolt", name="Spread", waypoints=[[0, 0, 0], [3, 0, 0]], count=4)
    xs = [location(obj)[0] for obj in copies("Spread")]
    close(xs, [0.0, 1.0, 2.0, 3.0], 1e-6)


def test_realised_copies_sum_the_triangles_and_vertices(bridge):
    bolt(bridge)
    result = bridge.ok("instances", source="Bolt", name="Merged", waypoints=[[0, 0, 0], [3, 0, 0]], spacing=0.5, realize=True)
    assert result["realized"] is True and result["count"] == 7
    assert triangle_total("Merged") == 7 * BOLT_TRIANGLES
    assert result["mesh"]["vertices"] == 7 * BOLT_VERTICES
    assert copies("Merged") == []
    xs = [vertex.x for vertex in vertices("Merged")]
    close([min(xs), max(xs)], [-0.01, 3.01], 1e-5)


def test_realised_copies_keep_materials_and_uvs(bridge):
    bolt(bridge)
    bridge.ok("add_material", name="Steel")
    bridge.ok("assign_material", name="Bolt", material="Steel")
    bridge.ok("instances", source="Bolt", name="Merged", points=[[0, 0, 0], [1, 0, 0]], realize=True)
    mesh = bpy.data.objects["Merged"].data
    assert [material.name for material in mesh.materials] == ["Steel"]
    assert len(mesh.uv_layers) == 1 and len(mesh.polygons) == 2 * 10
    assert bridge.ok("uv_info", name="Merged")["has_uv"] is True


def test_circle_places_instances_with_radial_alignment(bridge):
    bolt(bridge)
    result = bridge.ok("instances", source="Bolt", name="Ring", circle={"centre": [0, 0, 1], "radius": 0.5, "count": 8}, align="radial")
    assert result["count"] == 8
    for index, obj in enumerate(copies("Ring")):
        angle = math.tau * index / 8
        close(location(obj), [0.5 * math.cos(angle), 0.5 * math.sin(angle), 1.0], 1e-6)
        close(axis(obj, 0), [math.cos(angle), math.sin(angle), 0.0], 1e-6)
        close(axis(obj, 2), [0.0, 0.0, 1.0], 1e-6)
    bridge.ok("instances", source="Bolt", name="Wheel", circle={"centre": [0, 0, 0], "radius": 1.0, "count": 4, "normal": [1, 0, 0], "start_angle": 90.0, "sweep": 180.0})
    wheel = copies("Wheel")
    assert len(wheel) == 4
    close(location(wheel[0]), [0.0, 0.0, 1.0], 1e-6)
    close(location(wheel[-1]), [0.0, 0.0, -1.0], 1e-6)
    tangent = bridge.ok("instances", source="Bolt", name="Spin", circle={"centre": [0, 0, 0], "radius": 1.0, "count": 4}, align="frame")
    close(axis(copies("Spin")[0], 0), [0.0, 1.0, 0.0], 1e-6)


def test_points_with_normals_scale_and_rotation(bridge):
    bolt(bridge)
    bridge.ok(
        "instances",
        source="Bolt",
        name="Studs",
        points=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
        normals=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        scales=[1.0, 2.0, 3.0],
    )
    studs = copies("Studs")
    close(axis(studs[0], 2), [1.0, 0.0, 0.0], 1e-6)
    close(axis(studs[1], 2), [0.0, 1.0, 0.0], 1e-6)
    close([list(obj.matrix_world.to_scale())[0] for obj in studs], [1.0, 2.0, 3.0], 1e-6)
    bridge.ok("instances", source="Bolt", name="Turned", points=[[0, 0, 0], [1, 0, 0]], rotation=[0, 0, 90.0], scale=2.0)
    turned = copies("Turned")
    close(axis(turned[0], 0), [0.0, 1.0, 0.0], 1e-6)
    close(list(turned[0].matrix_world.to_scale())[0], 2.0, 1e-6)
    bridge.ok("instances", source="Bolt", name="Varied", points=[[0, 0, 0], [1, 0, 0]], rotations=[[0, 0, 90.0], [0, 0, 180.0]])
    close(axis(copies("Varied")[1], 0), [-1.0, 0.0, 0.0], 1e-6)


def test_edge_loop_places_instances_around_a_mesh_outline(bridge):
    bolt(bridge)
    bridge.ok("mesh_from_data", name="Outline", vertices=[[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], edges=[[0, 1], [1, 2], [2, 3], [3, 0]])
    assert bridge.ok("instances", source="Bolt", name="Loop", edges="Outline", spacing=0.5)["count"] == 8
    bridge.ok("mesh_from_data", name="Path", vertices=[[0, 0, 0], [1, 0, 0], [1, 1, 0]], edges=[[0, 1], [1, 2]])
    assert bridge.ok("instances", source="Bolt", name="Chain", edges="Path", spacing=0.5)["count"] == 5
    bridge.ok("mesh_from_data", name="Star", vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0], [-1, 0, 0]], edges=[[0, 1], [0, 2], [0, 3]])
    bridge.refuse("instances", "bad_args", source="Bolt", name="Bad", edges="Star", spacing=0.5)


def test_rivet_line_is_a_row_of_instances_with_a_built_in_head(bridge):
    result = bridge.ok("rivet_line", name="Rivets", start=[0, 0, 0], end=[1, 0, 0], count=5)
    assert result["count"] == 5 and result["shared_mesh"] == "Rivets_rivet" and result["length"] == 1.0
    close([location(obj)[0] for obj in copies("Rivets")], [0.0, 0.25, 0.5, 0.75, 1.0], 1e-6)
    bolt(bridge)
    bridge.ok("rivet_line", name="Studs", start=[0, 1, 0], end=[1, 1, 0], spacing=0.25, source="Bolt", normal=[0, 1, 0])
    assert len(copies("Studs")) == 5
    close(axis(copies("Studs")[0], 2), [0.0, 1.0, 0.0], 1e-6)
    merged = bridge.ok("rivet_line", name="Fused", start=[0, 2, 0], end=[1, 2, 0], count=3, realize=True, head_radius=0.01, head_height=0.01)
    assert merged["realized"] is True and merged["mesh"]["vertices"] == 3 * 38
    assert "Fused_rivet" not in bpy.data.meshes


def test_instances_refuse_bad_arguments(bridge):
    bolt(bridge)
    bridge.ok("curve_from_points", name="Rail", points=[[0, 0, 0], [3, 0, 0]])
    bridge.ok("add_primitive", type="cube", name="Box")
    straight = [[0, 0, 0], [3, 0, 0]]
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", waypoints=straight)
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", waypoints=straight, spacing=0.5, count=3)
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", waypoints=straight, count=3, offset=0.2)
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", spacing=0.5)
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", waypoints=straight, curve="Rail", spacing=0.5)
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", points=[[0, 0, 0]], spacing=0.5)
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", points=[[0, 0, 0]], align="radial")
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", waypoints=straight, count=3, normals=[[0, 0, 1]])
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", points=[[0, 0, 0], [1, 0, 0]], normals=[[0, 0, 1]])
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", points=[[0, 0, 0], [1, 0, 0]], scales=[1.0])
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", points=[[0, 0, 0], [1, 0, 0]], rotations=[[0, 0, 0]])
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", waypoints=straight, spacing=0.00001)
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", waypoints=straight, spacing=5.0, offset=4.0)
    bridge.refuse("instances", "bad_args", source="Bolt", name="Box", points=[[0, 0, 0]])
    bridge.refuse("instances", "not_found", source="Ghost", name="A", points=[[0, 0, 0]])
    bridge.refuse("instances", "bad_args", source="Rail", name="A", points=[[0, 0, 0]])
    bridge.ok("instances", source="Bolt", name="Dup", points=[[0, 0, 0]])
    bridge.refuse("instances", "bad_args", source="Bolt", name="Dup", points=[[0, 0, 0]])
    bridge.refuse("instances", "bad_args", source="Bolt", name="Other", points=[[0, 0, 0]], realize=True, group=False, circle={"centre": [0, 0, 0], "radius": 1.0, "count": 2})
    bridge.refuse("rivet_line", "bad_args", name="R", start=[0, 0, 0], end=[0, 0, 0], count=2)
    bridge.refuse("rivet_line", "bad_args", name="R", start=[0, 0, 0], end=[1, 0, 0])
    bridge.refuse("rivet_line", "bad_args", name="R", start=[0, 0, 0], end=[1, 0, 0], count=3, normal=[0, 0, 0])


def test_failed_instances_leave_the_scene_unchanged(bridge):
    bolt(bridge)
    before = settled_snapshot()
    bridge.refuse("instances", "bad_args", source="Bolt", name="A", waypoints=[[0, 0, 0], [3, 0, 0]], spacing=0.5, count=3)
    bridge.refuse("rivet_line", "bad_args", name="R", start=[0, 0, 0], end=[1, 0, 0])
    assert settled_snapshot() == before


run(globals())
