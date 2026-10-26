import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run

PRIMITIVES = {
    "cube": ({"size": 2.0}, {"vertices": 8, "edges": 12, "faces": 6, "triangles": 12}, [2.0, 2.0, 2.0]),
    "plane": ({"size": 3.0}, {"vertices": 4, "edges": 4, "faces": 1, "triangles": 2}, [3.0, 3.0, 0.0]),
    "cylinder": (
        {"radius": 0.5, "depth": 2.0, "segments": 32},
        {"vertices": 64, "edges": 96, "faces": 34, "triangles": 124},
        [1.0, 1.0, 2.0],
    ),
    "cone": (
        {"radius": 1.0, "depth": 2.0, "segments": 32},
        {"vertices": 33, "edges": 64, "faces": 33, "triangles": 62},
        [2.0, 2.0, 2.0],
    ),
    "sphere": (
        {"radius": 1.0, "segments": 32, "rings": 16},
        {"vertices": 482, "edges": 992, "faces": 512, "triangles": 960},
        [2.0, 2.0, 2.0],
    ),
    "ico_sphere": (
        {"radius": 1.0, "subdivisions": 2},
        {"vertices": 42, "edges": 120, "faces": 80, "triangles": 80},
        None,
    ),
    "torus": (
        {"radius": 1.0, "minor_radius": 0.25, "segments": 48, "rings": 12},
        {"vertices": 576, "edges": 1152, "faces": 576, "triangles": 1152},
        [2.5, 2.5, 0.5],
    ),
}


def test_add_primitive_builds_every_type(bridge):
    for kind, (options, counts, dimensions) in PRIMITIVES.items():
        result = bridge.ok("add_primitive", type=kind, **options)
        assert result["mesh"] == counts, (kind, result["mesh"])
        if dimensions is not None:
            close(result["dimensions"], dimensions, 1e-3)
        assert bridge.info(result["name"])["uv_layers"] == ["UVMap"], kind


def test_add_primitive_places_and_names(bridge):
    result = bridge.ok("add_primitive", type="cube", name="Box", size=1.0, location=[1.0, 2.0, 3.0], rotation=[0.0, 0.0, 90.0])
    assert result["name"] == "Box"
    box = bridge.info("Box")
    close(box["location"], [1.0, 2.0, 3.0])
    close(box["rotation"], [0.0, 0.0, 90.0])


def test_add_primitive_refuses_bad_arguments(bridge):
    bridge.refuse("add_primitive", "bad_args", type="pyramid")
    bridge.refuse("add_primitive", "bad_args", type="cube", radius=1.0)
    bridge.refuse("add_primitive", "bad_args", type="sphere", segments=2)
    bridge.refuse("add_primitive", "bad_args", type="torus", radius=1.0, minor_radius=1.5)
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("add_primitive", "bad_args", type="cube", name="Box")


def test_transform_sets_and_adds(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    result = bridge.ok("transform", name="Box", location=[1.0, 0.0, 0.0], rotation=[0.0, 0.0, 45.0], scale=[2.0, 1.0, 1.0])
    close(result["location"], [1.0, 0.0, 0.0])
    close(result["rotation"], [0.0, 0.0, 45.0])
    result = bridge.ok("transform", name="Box", location=[0.0, 1.0, 0.0], rotation=[0.0, 0.0, 45.0], scale=[0.5, 1.0, 3.0], relative=True)
    close(result["location"], [1.0, 1.0, 0.0])
    close(result["rotation"], [0.0, 0.0, 90.0])
    close(result["scale"], [1.0, 1.0, 3.0])


def test_transform_refuses_bad_arguments(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("transform", "not_found", name="Ghost", location=[0.0, 0.0, 0.0])
    bridge.refuse("transform", "bad_args", name="Box")
    bridge.refuse("transform", "bad_args", name="Box", scale=[1.0, 0.0, 1.0])


def test_apply_transform_bakes_scale_and_rotation(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0, location=[0.0, 0.0, 1.0])
    bridge.ok("transform", name="Box", scale=[2.0, 1.0, 0.5], rotation=[0.0, 0.0, 90.0])
    result = bridge.ok("apply_transform", name="Box")
    close(result["scale"], [1.0, 1.0, 1.0])
    close(result["rotation"], [0.0, 0.0, 0.0])
    close(result["location"], [0.0, 0.0, 1.0])
    close(result["dimensions"], [2.0, 4.0, 1.0])
    result = bridge.ok("apply_transform", name="Box", location=True)
    close(result["location"], [0.0, 0.0, 0.0])
    close(bridge.info("Box")["bounds"]["min"], [-1.0, -2.0, 0.5])


def test_apply_transform_keeps_children_in_place(bridge):
    bridge.ok("add_primitive", type="cube", name="Parent")
    bridge.ok("add_primitive", type="cube", name="Child", location=[3.0, 0.0, 0.0])
    bridge.ok("parent", name="Child", parent="Parent")
    bridge.ok("transform", name="Parent", scale=[2.0, 2.0, 2.0])
    before = bridge.info("Child")["bounds"]
    bridge.ok("apply_transform", name="Parent")
    after = bridge.info("Child")["bounds"]
    close(after["min"], before["min"])
    close(after["max"], before["max"])


def test_apply_transform_refuses_shared_and_non_mesh(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.ok("duplicate", name="Box", new_name="Twin", linked=True)
    bridge.refuse("apply_transform", "bad_args", name="Box")
    bridge.ok("add_light", type="point", name="Lamp")
    bridge.refuse("apply_transform", "bad_args", name="Lamp")
    bridge.refuse("apply_transform", "not_found", name="Ghost")


def test_set_origin_moves_origin_not_geometry(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0, location=[0.0, 0.0, 5.0])
    result = bridge.ok("set_origin", name="Box", to="bottom_centre")
    close(result["origin"], [0.0, 0.0, 4.0])
    close(bridge.info("Box")["bounds"]["min"], [-1.0, -1.0, 4.0])
    result = bridge.ok("set_origin", name="Box", to="geometry_centre")
    close(result["origin"], [0.0, 0.0, 5.0])
    result = bridge.ok("set_origin", name="Box", to="cursor", point=[1.0, 1.0, 1.0])
    close(result["origin"], [1.0, 1.0, 1.0])
    close(bridge.info("Box")["bounds"]["max"], [1.0, 1.0, 6.0])
    result = bridge.ok("set_origin", name="Box", to="cursor")
    close(result["origin"], [0.0, 0.0, 0.0])


def test_set_origin_refuses_bad_arguments(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("set_origin", "bad_args", name="Box", to="top")
    bridge.refuse("set_origin", "bad_args", name="Box", to="bottom_centre", point=[0.0, 0.0, 0.0])
    bridge.refuse("set_origin", "not_found", name="Ghost", to="cursor")


def test_duplicate_copies_or_links(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    assert bridge.ok("duplicate", name="Box", new_name="Copy", offset=[3.0, 0.0, 0.0]) == {"name": "Copy"}
    close(bridge.info("Copy")["location"], [3.0, 0.0, 0.0])
    bridge.ok("duplicate", name="Box", new_name="Linked", linked=True)
    import bpy

    assert bpy.data.objects["Copy"].data != bpy.data.objects["Box"].data
    assert bpy.data.objects["Linked"].data == bpy.data.objects["Box"].data


def test_duplicate_refuses_taken_names(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("duplicate", "bad_args", name="Box", new_name="Box")
    bridge.refuse("duplicate", "not_found", name="Ghost")


def test_join_merges_meshes(bridge):
    bridge.ok("add_primitive", type="cube", name="A")
    bridge.ok("add_primitive", type="cube", name="B", location=[3.0, 0.0, 0.0])
    result = bridge.ok("join", names=["A", "B"])
    assert result["name"] == "A"
    assert result["mesh"]["vertices"] == 16 and result["mesh"]["triangles"] == 24
    info = bridge.ok("scene_info")
    assert [entry["name"] for entry in info["objects"]] == ["A"]
    close(info["bounds"]["max"], [4.0, 1.0, 1.0])


def test_join_refuses_bad_arguments(bridge):
    bridge.ok("add_primitive", type="cube", name="A")
    bridge.ok("add_light", type="point", name="Lamp")
    bridge.refuse("join", "bad_args", names=["A"])
    bridge.refuse("join", "bad_args", names=["A", "Lamp"])
    bridge.refuse("join", "bad_args", names=["A", "A"])
    bridge.ok("add_primitive", type="cube", name="B")
    bridge.refuse("join", "bad_args", names=["A", "B"], target="Lamp")


def test_rename_renames_object_and_data(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    assert bridge.ok("rename", name="Box", new_name="Crate") == {"name": "Crate"}
    import bpy

    assert bpy.data.objects["Crate"].data.name == "Crate"


def test_rename_refuses_taken_names(bridge):
    bridge.ok("add_primitive", type="cube", name="A")
    bridge.ok("add_primitive", type="cube", name="B")
    bridge.refuse("rename", "bad_args", name="A", new_name="B")
    bridge.refuse("rename", "not_found", name="C", new_name="D")


def test_parent_sets_and_clears(bridge):
    bridge.ok("add_primitive", type="cube", name="Parent", location=[1.0, 0.0, 0.0])
    bridge.ok("add_primitive", type="cube", name="Child", location=[2.0, 0.0, 0.0])
    result = bridge.ok("parent", name="Child", parent="Parent")
    assert result["parent"] == "Parent"
    close(result["location"], [1.0, 0.0, 0.0])
    bridge.ok("transform", name="Parent", location=[1.0, 0.0, 1.0], relative=True)
    close(bridge.info("Child")["bounds"]["centre"], [3.0, 0.0, 1.0])
    result = bridge.ok("parent", name="Child")
    assert result["parent"] is None
    close(result["location"], [3.0, 0.0, 1.0])


def test_parent_refuses_cycles(bridge):
    bridge.ok("add_primitive", type="cube", name="A")
    bridge.ok("add_primitive", type="cube", name="B")
    bridge.ok("parent", name="B", parent="A")
    bridge.refuse("parent", "bad_args", name="A", parent="B")
    bridge.refuse("parent", "bad_args", name="A", parent="A")
    bridge.refuse("parent", "not_found", name="A", parent="Ghost")


run(globals())
