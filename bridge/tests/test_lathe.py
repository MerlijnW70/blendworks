import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import euler, is_closed_manifold, open_edge_count, outward_normals, regular_polygon_area, settled_snapshot, uv_is_clean, vertices, volume

CYLINDER = [[0.0, 0.0], [1.0, 0.0], [1.0, 2.0], [0.0, 2.0]]


def test_lathe_cylinder_has_hand_counted_topology_and_volume(bridge):
    result = bridge.ok("lathe", name="Can", profile=CYLINDER, segments=8)
    assert result["mesh"] == {"vertices": 18, "edges": 40, "faces": 24, "triangles": 32}
    assert result["manifold"] is True
    assert euler("Can") == 2
    close(volume("Can"), 2.0 * regular_polygon_area(1.0, 8), 1e-5)
    close(result["volume"], 2.0 * regular_polygon_area(1.0, 8), 1e-5)
    assert is_closed_manifold("Can")
    assert outward_normals("Can") == 1.0


def test_lathe_closes_on_the_axis_with_single_pole_vertices(bridge):
    bridge.ok("lathe", name="Can", profile=CYLINDER, segments=16)
    poles = [vertex for vertex in vertices("Can") if abs(vertex.x) < 1e-9 and abs(vertex.y) < 1e-9]
    assert sorted(round(vertex.z, 6) for vertex in poles) == [0.0, 2.0]
    assert len(vertices("Can")) == 2 + 2 * 16
    assert is_closed_manifold("Can")


def test_lathe_volume_of_solids_of_revolution_within_one_percent(bridge):
    bridge.ok("lathe", name="Can", profile=CYLINDER, segments=128)
    assert abs(volume("Can") / (2.0 * math.pi) - 1.0) < 0.01
    bridge.ok("lathe", name="Frustum", profile=[[0.0, 0.0], [2.0, 0.0], [1.0, 3.0], [0.0, 3.0]], segments=128)
    assert abs(volume("Frustum") / (7.0 * math.pi) - 1.0) < 0.01
    assert is_closed_manifold("Frustum")
    bridge.ok("lathe", name="Cone", profile=[[0.0, 0.0], [1.5, 0.0], [0.0, 2.0]], segments=128)
    assert abs(volume("Cone") / (math.pi * 1.5 * 1.5 * 2.0 / 3.0) - 1.0) < 0.01


def test_lathe_closed_profile_makes_a_torus(bridge):
    ring = [[1.0 + 0.25 * math.cos(math.tau * i / 64), 0.25 * math.sin(math.tau * i / 64)] for i in range(64)]
    result = bridge.ok("lathe", name="Ring", profile=ring, segments=32, closed=True)
    assert result["mesh"]["vertices"] == 64 * 32 and result["mesh"]["faces"] == 64 * 32
    assert euler("Ring") == 0
    assert result["manifold"] is True
    assert abs(volume("Ring") / (2.0 * math.pi ** 2 * 0.25 ** 2) - 1.0) < 0.01


def test_lathe_partial_turn_is_closed_by_wedge_faces(bridge):
    result = bridge.ok("lathe", name="Slice", profile=CYLINDER, segments=8, angle=90.0)
    assert result["mesh"] == {"vertices": 20, "edges": 44, "faces": 26, "triangles": 8 + 8 + 16 + 4}
    assert result["manifold"] is True
    close(volume("Slice"), 8 * 0.5 * math.sin(math.pi / 16) * 2.0, 1e-5)
    bridge.ok("lathe", name="Open", profile=CYLINDER, segments=8, angle=90.0, caps=False)
    assert bridge.ok("lathe", name="Open2", profile=CYLINDER, segments=8, angle=90.0, caps=False)["manifold"] is False


def test_lathe_caps_close_an_open_profile_and_axis_x_works(bridge):
    side = [[1.0, 0.0], [1.0, 2.0]]
    assert bridge.ok("lathe", name="Tube", profile=side, segments=12, caps=False)["manifold"] is False
    capped = bridge.ok("lathe", name="Drum", profile=side, segments=12)
    assert capped["manifold"] is True and capped["mesh"]["faces"] == 12 + 2
    bridge.ok("lathe", name="Rod", profile=[[0.0, 0.0], [0.0, 1.0], [2.0, 1.0], [2.0, 0.0]], axis="x", segments=16)
    xs = [vertex.x for vertex in vertices("Rod")]
    assert min(xs) == 0.0 and max(xs) == 2.0
    assert is_closed_manifold("Rod")
    close(volume("Rod"), 2.0 * regular_polygon_area(1.0, 16), 1e-5)


def test_lathe_seam_merge_shares_or_duplicates_the_seam(bridge):
    merged = bridge.ok("lathe", name="Merged", profile=CYLINDER, segments=8)
    split = bridge.ok("lathe", name="Split", profile=CYLINDER, segments=8, seam_merge=False)
    assert merged["mesh"]["vertices"] == 18 and merged["manifold"] is True
    assert split["mesh"]["vertices"] == 2 + 2 * 9 and split["manifold"] is False
    assert open_edge_count("Split") == 6


def test_lathe_uvs_unwrap_along_the_length_without_overlap(bridge):
    bridge.ok("lathe", name="Can", profile=CYLINDER, segments=32)
    uv_is_clean(bridge, "Can")
    mesh = bpy.data.objects["Can"].data
    side = [polygon for polygon in mesh.polygons if len(polygon.vertices) == 4]
    layer = mesh.uv_layers.active.data
    first = [layer[index].uv for index in side[0].loop_indices]
    height = abs(first[3][1] - first[0][1])
    width = abs(first[1][0] - first[0][0])
    close(height / width, 2.0 / (math.tau / 32), 1e-4)


def test_lathe_shading_follows_the_angle(bridge):
    bridge.ok("lathe", name="Smooth", profile=CYLINDER, segments=32, shading="smooth")
    assert all(polygon.use_smooth for polygon in bpy.data.objects["Smooth"].data.polygons)
    bridge.ok("lathe", name="Flat", profile=CYLINDER, segments=32, shading="flat")
    assert not any(polygon.use_smooth for polygon in bpy.data.objects["Flat"].data.polygons)
    bridge.ok("lathe", name="Auto", profile=CYLINDER, segments=32, smooth_angle=40.0)
    mesh = bpy.data.objects["Auto"].data
    sharp = sum(1 for edge in mesh.edges if edge.use_edge_sharp)
    assert sharp == 64


def test_lathe_refuses_bad_profiles_and_arguments(bridge):
    bridge.refuse("lathe", "bad_args", name="A", profile=[[-1.0, 0.0], [1.0, 1.0]])
    bridge.refuse("lathe", "bad_args", name="B", profile=[[0.0, 0.0], [0.0, 1.0], [1.0, 2.0]])
    bridge.refuse("lathe", "bad_args", name="C", profile=[[0.0, 0.0], [1.0, 1.0], [0.0, 2.0], [0.5, 3.0]])
    bridge.refuse("lathe", "bad_args", name="D", profile=[[0.0, 0.0], [1.0, 1.0], [0.0, 2.0]], closed=True)
    bridge.refuse("lathe", "bad_args", name="E", profile=CYLINDER, segments=2)
    bridge.refuse("lathe", "bad_args", name="F", profile=CYLINDER, angle=0.0)
    bridge.refuse("lathe", "bad_args", name="G", profile=CYLINDER, angle=361.0)
    bridge.refuse("lathe", "bad_args", name="H", profile=[[1.0, 1.0], [1.0, 1.0]])
    bridge.refuse("lathe", "bad_args", name="I", profile=[[1.0, 0.0]])
    bridge.ok("lathe", name="Taken", profile=CYLINDER)
    bridge.refuse("lathe", "bad_args", name="Taken", profile=CYLINDER)


def test_failed_lathe_leaves_the_scene_unchanged(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    before = settled_snapshot()
    bridge.refuse("lathe", "bad_args", name="Bad", profile=[[-1.0, 0.0], [1.0, 1.0]])
    assert settled_snapshot() == before


run(globals())
