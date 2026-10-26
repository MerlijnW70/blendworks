import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run


def test_describe_lists_commands_with_schemas(bridge):
    result = bridge.ok("describe")
    assert result["units"] == {"length": "metres", "angle": "degrees"}
    names = [entry["name"] for entry in result["commands"]]
    assert "describe" in names and "render_preview" in names
    assert "run_python" not in names
    assert result["python"] is False


def test_describe_refuses_arguments(bridge):
    bridge.refuse("describe", "bad_args", verbose=True)


def test_scene_info_reports_counts_bounds_and_units(bridge):
    bridge.ok("add_primitive", type="cube", size=2.0, location=[1.0, 0.0, 1.0])
    bridge.ok("add_material", name="Red", base_color=[1.0, 0.0, 0.0])
    bridge.ok("assign_material", name="Cube", material="Red")
    bridge.ok("add_camera", name="Cam", location=[0.0, -8.0, 2.0])
    bridge.ok("add_light", type="point", name="Lamp")
    info = bridge.ok("scene_info")
    cube = next(entry for entry in info["objects"] if entry["name"] == "Cube")
    assert cube["mesh"] == {"vertices": 8, "edges": 12, "faces": 6, "triangles": 12}
    assert cube["materials"] == ["Red"]
    close(cube["bounds"]["min"], [0.0, -1.0, 0.0])
    close(cube["bounds"]["max"], [2.0, 1.0, 2.0])
    assert info["totals"]["triangles"] == 12
    assert info["cameras"] == ["Cam"] and info["active_camera"] == "Cam"
    assert info["lights"] == ["Lamp"]
    assert info["used_materials"] == ["Red"]
    assert info["units"]["system"] == "metric" and info["units"]["length"] == "meters"
    close(info["bounds"]["size"], [2.0, 2.0, 2.0])


def test_scene_info_refuses_arguments(bridge):
    bridge.refuse("scene_info", "bad_args", objects=["Cube"])


def test_new_scene_clears_everything(bridge):
    bridge.ok("add_primitive", type="cube")
    bridge.ok("add_primitive", type="plane")
    result = bridge.ok("new_scene")
    assert result["removed_objects"] == 2
    info = bridge.ok("scene_info")
    assert info["objects"] == [] and info["bounds"] is None


def test_new_scene_refuses_arguments(bridge):
    bridge.refuse("new_scene", "bad_args", keep=["Cube"])


def test_select_sets_adds_and_removes(bridge):
    for name in ("A", "B", "C"):
        bridge.ok("add_primitive", type="cube", name=name)
    assert bridge.ok("select", names=["A", "B"], active="B") == {"selected": ["A", "B"], "active": "B"}
    assert bridge.ok("select", names=["C"], mode="add")["selected"] == ["A", "B", "C"]
    assert bridge.ok("select", names=["A"], mode="remove")["selected"] == ["B", "C"]
    assert bridge.ok("select", names=[])["selected"] == []


def test_select_refuses_unknown_objects_and_modes(bridge):
    bridge.ok("add_primitive", type="cube", name="A")
    bridge.refuse("select", "not_found", names=["Nope"])
    bridge.refuse("select", "bad_args", names=["A"], mode="toggle")
    bridge.refuse("select", "bad_args", names=["A", "A"])


def test_delete_keeps_children_in_place(bridge):
    bridge.ok("add_primitive", type="cube", name="Parent", location=[2.0, 0.0, 0.0])
    bridge.ok("add_primitive", type="cube", name="Child", location=[3.0, 1.0, 0.0])
    bridge.ok("parent", name="Child", parent="Parent")
    assert bridge.ok("delete", names=["Parent"]) == {"deleted": ["Parent"]}
    child = bridge.info("Child")
    assert child["parent"] is None
    close(child["location"], [3.0, 1.0, 0.0])


def test_delete_refuses_missing_and_empty(bridge):
    bridge.refuse("delete", "not_found", names=["Ghost"])
    bridge.refuse("delete", "bad_args", names=[])


def test_protocol_refuses_bad_requests(bridge):
    handler = bridge.handler
    assert handler.handle({"id": 7, "cmd": "warp"})["error"]["code"] == "bad_args"
    assert handler.handle({"id": 8, "cmd": "describe", "extra": 1})["error"]["code"] == "bad_args"
    assert handler.handle({"id": 9, "cmd": "describe", "args": []})["error"]["code"] == "bad_args"
    assert handler.handle([1, 2])["error"]["code"] == "bad_args"
    reply = handler.handle_line("not json")
    assert '"ok":false' in reply and '"bad_args"' in reply and '"id":null' in reply
    assert handler.handle({"id": 10, "cmd": "describe"})["id"] == 10


def test_arguments_are_type_checked(bridge):
    bridge.refuse("add_primitive", "bad_args", type="cube", size="big")
    bridge.refuse("add_primitive", "bad_args", type="cube", size=True)
    bridge.refuse("add_primitive", "bad_args", type="cube", size=-1.0)
    bridge.refuse("add_primitive", "bad_args", type="cube", location=[0.0, 0.0])
    bridge.refuse("add_primitive", "bad_args", type="cube", segments=4)
    bridge.refuse("add_primitive", "bad_args", size=1.0)
    bridge.refuse("add_primitive", "bad_args", type="cube", colour="red")


run(globals())
