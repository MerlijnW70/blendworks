import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run

ROOT = "Scene Collection"


def gltf_tree(path):
    with open(path, "rb") as handle:
        data = handle.read()
    length, kind = struct.unpack("<I4s", data[12:20])
    assert kind == b"JSON"
    nodes = json.loads(data[20 : 20 + length])["nodes"]
    by_name = {node["name"]: node for node in nodes}
    return by_name, {name: sorted(nodes[index]["name"] for index in node.get("children", [])) for name, node in by_name.items()}


def cart(bridge):
    bridge.ok("add_empty", name="Cart", display="arrows", size=0.5, location=[1.0, 0.0, 0.0])
    bridge.ok("add_empty", name="Wheels", parent="Cart", location=[0.0, 1.0, 0.0], rotation=[0.0, 0.0, 90.0], scale=[2.0, 2.0, 2.0])
    bridge.ok("add_primitive", type="cube", name="FrontLeft", size=0.2, location=[0.5, 0.0, 0.0])
    bridge.ok("add_primitive", type="cube", name="FrontRight", size=0.2, location=[-0.5, 0.0, 0.0])
    bridge.ok("parent", name="FrontLeft", parent="Wheels", keep_transform=False)
    bridge.ok("parent", name="FrontRight", parent="Wheels", keep_transform=False)
    bridge.ok("add_primitive", type="cube", name="Loose", size=0.2, location=[5.0, 0.0, 0.0])


def test_add_empty_takes_a_display_type_a_size_and_a_transform(bridge):
    result = bridge.ok("add_empty", name="Marker", display="cone", size=0.25, location=[1.0, 2.0, 3.0], rotation=[0.0, 0.0, 90.0], scale=[1.0, 2.0, 3.0])
    assert result == {"name": "Marker", "display": "cone", "size": 0.25, "parent": None, "collections": [ROOT], "location": [1.0, 2.0, 3.0]}
    empty = bpy.data.objects["Marker"]
    assert empty.type == "EMPTY" and empty.empty_display_type == "CONE" and empty.empty_display_size == 0.25
    close(list(empty.scale), [1.0, 2.0, 3.0])
    close(list(empty.rotation_euler), [0.0, 0.0, 1.5707963], 1e-5)
    default = bridge.ok("add_empty", name="Plain")
    assert default["display"] == "plain_axes" and default["size"] == 1.0 and default["location"] == [0.0, 0.0, 0.0]


def test_a_parented_empty_takes_its_transform_relative_to_the_parent(bridge):
    cart(bridge)
    close(list(bpy.data.objects["Wheels"].matrix_world.translation), [1.0, 1.0, 0.0])
    close(list(bpy.data.objects["FrontLeft"].matrix_world.translation), [1.0, 2.0 * 0.5 + 1.0, 0.0])
    assert bpy.data.objects["Wheels"].parent.name == "Cart"


def test_scene_info_reports_parents_collections_and_empties(bridge):
    cart(bridge)
    bridge.ok("collection_create", name="Props", objects=["Cart", "Wheels", "FrontLeft", "FrontRight"])
    bridge.ok("collection_create", name="Inner", parent="Props")
    bridge.ok("collection_link", collection="Inner", names=["FrontLeft"], move=True)
    info = bridge.ok("scene_info")
    objects = {entry["name"]: entry for entry in info["objects"]}
    assert objects["Wheels"]["parent"] == "Cart" and objects["FrontLeft"]["parent"] == "Wheels" and objects["Cart"]["parent"] is None
    assert objects["Cart"]["display"] == "arrows" and objects["Cart"]["display_size"] == 0.5 and "display" not in objects["Loose"]
    assert objects["Cart"]["collections"] == ["Props", ROOT]
    assert objects["FrontLeft"]["collections"] == ["Inner"] and objects["Loose"]["collections"] == [ROOT]
    assert info["collections"] == [
        {"name": "Inner", "parent": "Props", "objects": 1},
        {"name": "Props", "parent": ROOT, "objects": 3},
    ]
    assert info["totals"]["by_type"]["empty"] == 2
    full = bridge.ok("scene_info", detail="full")
    assert {entry["name"]: entry["collections"] for entry in full["objects"]}["FrontLeft"] == ["Inner"]


def test_an_empty_can_start_in_a_collection_under_a_parent(bridge):
    bridge.ok("collection_create", name="Rigging")
    bridge.ok("add_empty", name="Root")
    result = bridge.ok("add_empty", name="Child", parent="Root", collection="Rigging")
    assert result["collections"] == ["Rigging"] and result["parent"] == "Root"
    assert "Child" not in bpy.context.scene.collection.objects and "Child" in bpy.data.collections["Rigging"].objects


def test_collections_nest_link_move_and_unlink(bridge):
    bridge.ok("add_primitive", type="cube", name="A")
    bridge.ok("add_primitive", type="cube", name="B")
    created = bridge.ok("collection_create", name="Parts")
    assert created == {"name": "Parts", "parent": ROOT, "objects": []}
    nested = bridge.ok("collection_create", name="Small", parent="Parts", objects=["A"])
    assert nested == {"name": "Small", "parent": "Parts", "objects": ["A"]}
    assert [child.name for child in bpy.data.collections["Parts"].children] == ["Small"]
    assert bridge.ok("collection_link", collection="Parts", names=["A", "B"]) == {"collection": "Parts", "linked": ["A", "B"], "moved": False}
    assert sorted(item.name for item in bpy.data.objects["A"].users_collection) == ["Parts", ROOT, "Small"]
    bridge.ok("collection_link", collection="Small", names=["B"], move=True)
    assert [item.name for item in bpy.data.objects["B"].users_collection] == ["Small"]
    assert bridge.ok("collection_unlink", collection="Parts", names=["A"]) == {"collection": "Parts", "unlinked": ["A"]}
    assert sorted(item.name for item in bpy.data.objects["A"].users_collection) == [ROOT, "Small"]
    bridge.ok("collection_unlink", collection=ROOT, names=["A"])
    assert [item.name for item in bpy.data.objects["A"].users_collection] == ["Small"]
    bridge.ok("collection_link", collection=ROOT, names=["B"], move=True)
    assert [item.name for item in bpy.data.objects["B"].users_collection] == [ROOT]


def membership():
    return ({obj.name: sorted(item.name for item in obj.users_collection) for obj in bpy.data.objects}, sorted(collection.name for collection in bpy.data.collections))


def test_new_scene_clears_collections_too(bridge):
    bridge.ok("add_primitive", type="cube", name="A")
    bridge.ok("collection_create", name="Outer", objects=["A"])
    bridge.ok("collection_create", name="Inner", parent="Outer")
    assert bridge.ok("new_scene")["removed_objects"] == 1
    assert len(bpy.data.collections) == 0 and bridge.ok("scene_info")["collections"] == []
    assert bridge.ok("collection_create", name="Outer")["parent"] == ROOT


def test_hierarchy_commands_refuse_nonsense_and_change_nothing(bridge):
    bridge.ok("add_primitive", type="cube", name="A")
    bridge.ok("add_primitive", type="cube", name="B")
    bridge.ok("collection_create", name="Parts", objects=["A"])
    bridge.ok("collection_create", name="Solo", objects=["B"])
    bridge.ok("collection_unlink", collection=ROOT, names=["B"])
    before = membership()
    bridge.refuse("collection_create", "bad_args", name="Parts")
    bridge.refuse("collection_create", "bad_args", name=ROOT)
    bridge.refuse("collection_create", "not_found", name="New", parent="Nowhere")
    bridge.refuse("collection_create", "not_found", name="New", objects=["Ghost"])
    bridge.refuse("collection_create", "bad_args", name="New", objects=["A", "A"])
    bridge.refuse("collection_link", "not_found", collection="Nowhere", names=["A"])
    bridge.refuse("collection_link", "not_found", collection="Parts", names=["Ghost"])
    assert "already in Parts" in bridge.refuse("collection_link", "bad_args", collection="Parts", names=["B", "A"])
    assert "not in Parts" in bridge.refuse("collection_unlink", "bad_args", collection="Parts", names=["A", "B"])
    assert "would be in no collection" in bridge.refuse("collection_unlink", "bad_args", collection="Solo", names=["B"])
    bridge.refuse("collection_unlink", "not_found", collection="Nowhere", names=["A"])
    bridge.refuse("add_empty", "bad_args", name="A")
    bridge.refuse("add_empty", "bad_args", name="E", display="pyramid")
    bridge.refuse("add_empty", "bad_args", name="E", size=0.0)
    bridge.refuse("add_empty", "not_found", name="E", parent="Ghost")
    bridge.refuse("add_empty", "not_found", name="E", collection="Ghost")
    assert membership() == before and "E" not in bpy.data.objects


def test_an_exported_glb_has_the_expected_node_tree(bridge):
    cart(bridge)
    result = bridge.ok("export", path="cart.glb")
    assert result["objects"] == ["Cart", "FrontLeft", "FrontRight", "Loose", "Wheels"]
    by_name, children = gltf_tree(os.path.join(bridge.workspace, "cart.glb"))
    assert children["Cart"] == ["Wheels"] and children["Wheels"] == ["FrontLeft", "FrontRight"] and children["FrontLeft"] == [] and children["Loose"] == []
    close(by_name["Cart"]["translation"], [1.0, 0.0, 0.0])
    close(by_name["Wheels"]["translation"], [0.0, 0.0, -1.0])
    close(by_name["Wheels"]["scale"], [2.0, 2.0, 2.0])
    close(by_name["FrontLeft"]["translation"], [0.5, 0.0, 0.0])
    parented = {child for names in children.values() for child in names}
    assert sorted(set(children) - parented) == ["Cart", "Loose"]


def test_exporting_a_collection_keeps_the_empties_above_its_objects(bridge):
    cart(bridge)
    bridge.ok("collection_create", name="Outer")
    bridge.ok("collection_create", name="Inner", parent="Outer", objects=["FrontLeft"])
    result = bridge.ok("export", path="inner.glb", collection="Outer")
    assert result["objects"] == ["Cart", "FrontLeft", "Wheels"]
    _, children = gltf_tree(os.path.join(bridge.workspace, "inner.glb"))
    assert children == {"Cart": ["Wheels"], "Wheels": ["FrontLeft"], "FrontLeft": []}
    flat = bridge.ok("export", path="flat.glb", collection="Inner", ancestors=False)
    assert flat["objects"] == ["FrontLeft"]
    bridge.refuse("export", "not_found", path="x.glb", collection="Ghost")
    bridge.refuse("export", "bad_args", path="x.glb", collection="Inner", names=["Loose"])


def test_a_hierarchy_made_with_the_commands_survives_an_export_import_round_trip(bridge):
    cart(bridge)
    bridge.ok("export", path="cart.glb", names=["FrontRight"])
    bridge.ok("new_scene")
    bridge.ok("import", path="cart.glb")
    assert bpy.data.objects["FrontRight"].parent.name == "Wheels" and bpy.data.objects["Wheels"].parent.name == "Cart"
    close(list(bpy.data.objects["FrontRight"].matrix_world.translation), [1.0, 0.0, 0.0], 1e-5)
    close(list(bpy.data.objects["Wheels"].matrix_world.translation), [1.0, 1.0, 0.0], 1e-5)


run(globals())
