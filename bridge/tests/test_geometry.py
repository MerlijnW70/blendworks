import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run

PYRAMID_VERTICES = [[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0], [1.0, 1.0, 0.0], [-1.0, 1.0, 0.0], [0.0, 0.0, 2.0]]
PYRAMID_FACES = [[3, 2, 1, 0], [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]


def test_mesh_from_data_builds_a_pyramid(bridge):
    result = bridge.ok("mesh_from_data", name="Pyramid", vertices=PYRAMID_VERTICES, faces=PYRAMID_FACES, location=[0.0, 0.0, 1.0])
    assert result["mesh"] == {"vertices": 5, "edges": 8, "faces": 5, "triangles": 6}
    assert result["corrected"] is False
    close(result["dimensions"], [2.0, 2.0, 2.0])
    close(bridge.info("Pyramid")["bounds"]["max"], [1.0, 1.0, 3.0])


def test_mesh_from_data_refuses_bad_indices_and_the_size_cap(bridge):
    bridge.refuse("mesh_from_data", "bad_args", vertices=PYRAMID_VERTICES, faces=[[0, 1, 5]])
    bridge.refuse("mesh_from_data", "bad_args", vertices=PYRAMID_VERTICES, faces=[[0, 1, 1]])
    bridge.refuse("mesh_from_data", "bad_args", vertices=PYRAMID_VERTICES, faces=[[0, 1]])
    bridge.refuse("mesh_from_data", "bad_args", vertices=PYRAMID_VERTICES)
    bridge.refuse("mesh_from_data", "bad_args", vertices=[[0.0, 0.0]], faces=[])
    too_many = [[float(index % 100), float(index // 100), 0.0] for index in range(100_001)]
    message = bridge.refuse("mesh_from_data", "bad_args", vertices=too_many, faces=[[0, 1, 2]])
    assert "100000" in message
    assert len(bpy.data.meshes) == 0


def test_mesh_from_data_accepts_the_cap(bridge):
    exactly = [[float(index % 100), float(index // 100), 0.0] for index in range(100_000)]
    result = bridge.ok("mesh_from_data", name="Grid", vertices=exactly, faces=[[0, 1, 101, 100]])
    assert result["mesh"]["vertices"] == 100_000


def test_curve_from_points_with_thickness(bridge):
    result = bridge.ok("curve_from_points", name="Rail", points=[[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]], bevel_depth=0.1)
    assert result["points"] == 2
    close(bridge.info("Rail")["bounds"]["size"], [4.0, 0.2, 0.2], 1e-3)
    bridge.ok("curve_from_points", name="Loop", points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], kind="bezier", closed=True)
    assert bpy.data.objects["Loop"].data.splines[0].use_cyclic_u
    bridge.ok("curve_from_points", name="Smooth", points=[[0.0, 0.0, 0.0], [1.0, 1.0, 0.0], [2.0, 0.0, 0.0]], kind="nurbs")
    assert bpy.data.objects["Smooth"].data.splines[0].type == "NURBS"


def test_curve_from_points_refuses_one_point(bridge):
    bridge.refuse("curve_from_points", "bad_args", points=[[0.0, 0.0, 0.0]])
    bridge.refuse("curve_from_points", "bad_args", points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], kind="spline")


def test_text_object_has_letter_height(bridge):
    result = bridge.ok("text_object", text="HI", name="Sign", size=0.5, extrude=0.05, align="centre")
    assert result["name"] == "Sign" and result["characters"] == 2
    dimensions = bridge.info("Sign")["dimensions"]
    assert 0.25 < dimensions[1] <= 0.5, dimensions
    close(dimensions[2], 0.1, 1e-3)
    assert bpy.data.objects["Sign"].data.align_x == "CENTER"


def test_text_object_refuses_empty_text(bridge):
    bridge.refuse("text_object", "bad_args", text="")
    bridge.refuse("text_object", "bad_args", text="x" * 2001)


run(globals())
