import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run


def gltf_nodes(path):
    with open(path, "rb") as handle:
        data = handle.read()
    assert data[:4] == b"glTF"
    length, kind = struct.unpack("<I4s", data[12:20])
    assert kind == b"JSON"
    document = json.loads(data[20 : 20 + length])
    return {node["name"]: node for node in document["nodes"]}, document["nodes"]


def rigged(bridge):
    bridge.ok("add_primitive", type="cube", name="Wheel", size=0.5, location=[2.0, 0.0, 0.0])
    bridge.ok("add_primitive", type="cube", name="Axle", size=0.2, location=[2.0, 1.0, 0.0])
    rig = bpy.data.objects.new("Rig", None)
    bpy.context.scene.collection.objects.link(rig)
    rig.location = (1.0, 0.0, 0.0)
    root = bpy.data.objects.new("Root", None)
    bpy.context.scene.collection.objects.link(root)
    rig.parent = root
    bpy.context.view_layer.update()
    bridge.ok("parent", name="Wheel", parent="Rig")
    bridge.ok("parent", name="Axle", parent="Wheel")


def test_a_default_export_keeps_the_parent_empties(bridge):
    rigged(bridge)
    result = bridge.ok("export", path="rig.glb")
    assert result["objects"] == ["Axle", "Rig", "Root", "Wheel"]
    by_name, nodes = gltf_nodes(os.path.join(bridge.workspace, "rig.glb"))
    children = lambda name: sorted(nodes[index]["name"] for index in by_name[name].get("children", []))
    assert children("Root") == ["Rig"] and children("Rig") == ["Wheel"] and children("Wheel") == ["Axle"]
    close(by_name["Rig"]["translation"], [1.0, 0.0, 0.0])
    close(by_name["Wheel"]["translation"], [1.0, 0.0, 0.0])


def test_the_hierarchy_survives_a_round_trip(bridge):
    rigged(bridge)
    bridge.ok("export", path="rig.glb")
    bridge.ok("new_scene")
    imported = bridge.ok("import", path="rig.glb")
    assert sorted(imported["objects"]) == ["Axle", "Rig", "Root", "Wheel"]
    assert bpy.data.objects["Wheel"].parent.name == "Rig" and bpy.data.objects["Rig"].parent.name == "Root"
    close(list(bpy.data.objects["Wheel"].matrix_world.translation), [2.0, 0.0, 0.0])


def test_ancestors_can_be_left_out(bridge):
    rigged(bridge)
    flat = bridge.ok("export", path="flat.glb", names=["Wheel"], ancestors=False)
    assert flat["objects"] == ["Wheel"]
    by_name, _ = gltf_nodes(os.path.join(bridge.workspace, "flat.glb"))
    assert set(by_name) == {"Wheel"}
    close(by_name["Wheel"]["translation"], [2.0, 0.0, 0.0])
    named = bridge.ok("export", path="named.glb", names=["Axle"])
    assert named["objects"] == ["Axle", "Rig", "Root"]
    bridge.refuse("export", "bad_args", path="x.glb", ancestors="yes")


run(globals())
