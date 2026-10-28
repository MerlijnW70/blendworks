import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import close, run
from rig_helpers import evaluated_world, weights_of

from blendworks_bridge.weights import limited, normalized

CHAIN = [
    {"name": "Low", "head": [0.0, 0.0, 0.0], "tail": [0.0, 0.0, 0.4]},
    {"name": "Mid", "head": [0.0, 0.0, 0.4], "tail": [0.0, 0.0, 0.8], "parent": "Low", "connect": True},
    {"name": "Top", "head": [0.0, 0.0, 0.8], "tail": [0.0, 0.0, 1.2], "parent": "Mid", "connect": True},
    {"name": "Grip", "head": [0.3, 0.0, 1.2], "tail": [0.3, 0.0, 1.3], "deform": False},
]


def tube(bridge, name="Tube"):
    waypoints = [[0.0, 0.0, 0.05 * step] for step in range(25)]
    bridge.ok("sweep", name=name, preset="circle", radius=0.06, segments=12, waypoints=waypoints, shading="smooth")
    bridge.ok("armature_create", name="Rig", bones=CHAIN)


def test_automatic_weights_limit_influences_and_normalise(bridge):
    tube(bridge)
    result = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", max_influences=2, smooth=3)
    mesh = result["meshes"][0]
    assert result["weights"] == "automatic" and result["rest_pose"] is True
    assert mesh["unweighted_after_bind"] == 0 and mesh["unweighted"] == 0 and mesh["filled"] == 0
    assert mesh["groups"] == ["Low", "Mid", "Top"], mesh
    weights = weights_of(bpy.data.objects["Tube"])
    assert max(len(entry) for entry in weights) == 2 == result["max_influences"]
    assert sum(1 for entry in weights if len(entry) == 2) > 20
    for entry in weights:
        close(sum(entry.values()), 1.0, 1e-5)
        assert "Grip" not in entry
    obj = bpy.data.objects["Tube"]
    assert any(modifier.type == "ARMATURE" and modifier.object.name == "Rig" for modifier in obj.modifiers)


def test_default_limit_is_four_influences(bridge):
    kept = normalized(limited([{"a": 0.5, "b": 0.3, "c": 0.2}], 2))[0]
    assert sorted(kept) == ["a", "b"]
    close([kept["a"], kept["b"]], [0.625, 0.375], 1e-9)
    tube(bridge)
    for step in range(4):
        bridge.ok("bone_add", armature="Rig", bones=[{"name": f"Extra{step}", "head": [0.0, 0.0, 0.5 + 0.02 * step], "tail": [0.0, 0.0, 0.52 + 0.02 * step]}])
    result = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", smooth=10)
    weights = weights_of(bpy.data.objects["Tube"])
    assert max(len(entry) for entry in weights) == 4 == result["max_influences"]
    unlimited = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", smooth=10, max_influences=8)
    assert unlimited["max_influences"] > 4


def test_unweighted_vertices_are_reported_and_filled_from_the_nearest_bone(bridge):
    tube(bridge)
    bare = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", weights="none", fill_unweighted=False)
    vertices = len(bpy.data.objects["Tube"].data.vertices)
    assert bare["unweighted"] == vertices and bare["meshes"][0]["unweighted_after_bind"] == vertices
    filled = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", weights="none")
    assert filled["unweighted"] == 0 and filled["meshes"][0]["filled"] == vertices
    obj = bpy.data.objects["Tube"]
    for vertex, entry in zip(obj.data.vertices, weights_of(obj)):
        expected = "Low" if vertex.co.z < 0.4 - 1e-6 else "Top" if vertex.co.z > 0.8 + 1e-6 else None
        if expected:
            assert entry == {expected: 1.0}, (vertex.co.z, entry)


def test_rigid_parts_by_vertex_group_loose_part_and_point(bridge):
    tube(bridge)
    bridge.ok("add_primitive", type="ico_sphere", name="Knob", radius=0.08, location=[0.0, 0.0, 1.3])
    bridge.ok("add_primitive", type="cube", name="Foot", size=0.15, location=[0.0, 0.0, -0.05])
    bridge.ok("join", names=["Tube", "Knob", "Foot"])
    group = bridge.ok("vertex_group", name="Tube", group="middle", box={"min": [-1, -1, 0.5], "max": [1, 1, 0.7]})
    assert group["vertices"] > 0
    result = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", rigid=[
        {"bone": "Top", "vertex_group": "middle"},
        {"bone": "Low", "near": [0.0, 0.0, 1.39]},
        {"bone": "Top", "near": [0.0, 0.0, -0.2]},
    ])
    obj = bpy.data.objects["Tube"]
    weights = [{name: weight for name, weight in entry.items() if name != "middle"} for entry in weights_of(obj)]
    members = {vertex.index for vertex in obj.data.vertices if any(element.group == obj.vertex_groups["middle"].index for element in vertex.groups)}
    for index in members:
        assert weights[index] == {"Top": 1.0}
    for vertex in obj.data.vertices:
        if vertex.co.z > 1.22:
            assert weights[vertex.index] == {"Low": 1.0}
        if vertex.co.z < -0.0001:
            assert weights[vertex.index] == {"Top": 1.0}
    assert result["meshes"][0]["parts"] == 3 and result["meshes"][0]["rigid_vertices"] > len(members)
    whole = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", rigid_parts=True)
    assert whole["max_influences"] == 1
    assert "not one of the deforming bones" in bridge.refuse("skin_bind", "bad_args", meshes=["Tube"], armature="Rig", rigid=[{"bone": "Grip", "near": [0, 0, 0]}])
    bridge.refuse("skin_bind", "bad_args", meshes=["Tube"], armature="Rig", rigid=[{"bone": "Top", "near": [0, 0, 0], "island": 1}])


def test_bones_limits_which_bones_the_weights_use(bridge):
    tube(bridge)
    result = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", bones=["Low", "Mid"])
    assert result["meshes"][0]["groups"] == ["Low", "Mid"]
    assert all(bone.use_deform for bone in bpy.data.objects["Rig"].data.bones if bone.name != "Grip")
    bridge.refuse("skin_bind", "bad_args", meshes=["Tube"], armature="Rig", bones=["Grip"])


def test_the_bind_pose_is_the_rest_pose(bridge):
    tube(bridge)
    rest = evaluated_world(bpy.data.objects["Tube"])
    bpy.data.objects["Rig"].pose.bones["Mid"].rotation_quaternion = (0.9, 0.3, 0.0, 0.0)
    bridge.ok("skin_bind", meshes=["Tube"], armature="Rig")
    rig = bpy.data.objects["Rig"]
    assert rig.data.pose_position == "POSE"
    rig.pose.bones["Mid"].rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    assert numpy.abs(evaluated_world(bpy.data.objects["Tube"]) - rest).max() < 1e-6
    rig.pose.bones["Top"].rotation_quaternion = (0.92, 0.38, 0.0, 0.0)
    bpy.context.view_layer.update()
    assert numpy.abs(evaluated_world(bpy.data.objects["Tube"]) - rest).max() > 0.05


def test_vertex_group_replaces_adds_and_removes(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    top = bridge.ok("vertex_group", name="Box", group="lid", facing="up", weight=0.5)
    assert top["vertices"] == 4
    added = bridge.ok("vertex_group", name="Box", group="lid", facing="down", mode="add")
    assert added["vertices"] == 8
    removed = bridge.ok("vertex_group", name="Box", group="lid", facing="down", mode="remove")
    assert removed["vertices"] == 4
    weights = [element.weight for vertex in bpy.data.objects["Box"].data.vertices for element in vertex.groups]
    assert weights == [0.5] * 4
    bridge.refuse("vertex_group", "bad_args", name="Box", group="missing", mode="remove")


run(globals())
