import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run, snapshot


def test_add_material_creates_and_updates(bridge):
    result = bridge.ok("add_material", name="Steel", base_color=[0.5, 0.5, 0.55], metallic=1.0, roughness=0.3)
    assert result["created"] is True
    close(result["base_color"], [0.5, 0.5, 0.55, 1.0])
    close([result["metallic"], result["roughness"], result["alpha"]], [1.0, 0.3, 1.0])
    result = bridge.ok("add_material", name="Steel", roughness=0.8, emission_color=[1.0, 0.5, 0.0], emission_strength=2.0, alpha=0.5)
    assert result["created"] is False
    close([result["metallic"], result["roughness"], result["alpha"], result["emission_strength"]], [1.0, 0.8, 0.5, 2.0])
    close(result["emission_color"], [1.0, 0.5, 0.0, 1.0])


def test_add_material_refuses_out_of_range(bridge):
    bridge.refuse("add_material", "bad_args", name="Bad", metallic=2.0)
    bridge.refuse("add_material", "bad_args", name="Bad", base_color=[1.0, 0.0])
    bridge.refuse("add_material", "bad_args", name="Bad", base_color=[1.0, 0.0, 0.0, 1.0, 1.0])
    assert "Bad" not in bpy.data.materials


def test_assign_material_to_object_and_faces(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.ok("add_material", name="Wood")
    bridge.ok("add_material", name="Metal")
    assert bridge.ok("assign_material", name="Box", material="Wood")["faces"] == 6
    result = bridge.ok("assign_material", name="Box", material="Metal", facing="up")
    assert result == {"name": "Box", "material": "Metal", "slot": 1, "faces": 1}
    mesh = bpy.data.objects["Box"].data
    assert sorted(polygon.material_index for polygon in mesh.polygons) == [0, 0, 0, 0, 0, 1]
    assert bridge.info("Box")["materials"] == ["Wood", "Metal"]


def test_assign_material_refuses_unknown_material(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("assign_material", "not_found", name="Box", material="Gold")
    bridge.ok("add_material", name="Gold")
    before = snapshot()
    bridge.refuse("assign_material", "bad_args", name="Box", material="Gold", faces=[99])
    assert snapshot() == before


def test_vertex_colors_paint_faces(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    result = bridge.ok("vertex_colors", name="Box", color=[1.0, 0.0, 0.0], facing="up")
    assert result["faces"] == 1 and result["layer"] == "Color"
    mesh = bpy.data.objects["Box"].data
    attribute = mesh.color_attributes["Color"]
    red = [index for index, item in enumerate(attribute.data) if item.color[1] < 0.5]
    assert len(red) == 4
    assert mesh.color_attributes.active_color.name == "Color"


def test_vertex_colors_refuse_non_meshes(bridge):
    bridge.ok("add_light", type="point", name="Lamp")
    bridge.refuse("vertex_colors", "bad_args", name="Lamp", color=[1.0, 0.0, 0.0])
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("vertex_colors", "bad_args", name="Box", color=[2.0, 0.0, 0.0])


def test_uv_smart_project_covers_the_square_without_overlap(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bpy.data.objects["Box"].data.uv_layers.remove(bpy.data.objects["Box"].data.uv_layers[0])
    result = bridge.ok("uv_smart_project", name="Box")
    assert result["has_uv"] and result["layer"] == "UVMap"
    assert result["overlap"] == 0.0
    assert result["coverage"] > 0.3 and result["outside"] is False


def test_uv_smart_project_refuses_empty_meshes(bridge):
    bridge.ok("mesh_from_data", name="Wire", vertices=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], edges=[[0, 1]])
    bridge.refuse("uv_smart_project", "bad_args", name="Wire")
    bridge.refuse("uv_smart_project", "not_found", name="Ghost")


def test_uv_unwrap_with_seams(bridge):
    bridge.ok("add_primitive", type="cylinder", name="Can", segments=16)
    result = bridge.ok("uv_unwrap", name="Can", seam_angle=60.0)
    assert result["seams"] == 32
    assert result["overlap"] < 0.01 and result["coverage"] > 0.2


def test_uv_unwrap_refuses_bad_method(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("uv_unwrap", "bad_args", name="Box", method="magic")


def test_uv_info_measures_coverage_and_overlap(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet")
    result = bridge.ok("uv_info", name="Sheet")
    close([result["coverage"], result["overlap"]], [1.0, 0.0])
    bridge.ok("add_primitive", type="plane", name="Other")
    bridge.ok("join", names=["Sheet", "Other"])
    result = bridge.ok("uv_info", name="Sheet")
    close([result["coverage"], result["overlap"]], [1.0, 1.0])
    bridge.ok("mesh_from_data", name="Bare", vertices=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], faces=[[0, 1, 2]])
    assert bridge.ok("uv_info", name="Bare") == {"name": "Bare", "has_uv": False, "layers": []}


def test_uv_info_refuses_unknown_layer(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet")
    bridge.refuse("uv_info", "not_found", name="Sheet", layer="Second")


run(globals())
