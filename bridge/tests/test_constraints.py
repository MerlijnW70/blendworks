import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Vector

from harness import close, run
from rig_helpers import bone_world, distance

from blendworks_bridge.posing import bend_direction

IK_TOLERANCE = 1e-3
LEG = [
    {"name": "Root", "head": [0.0, 0.0, 0.0], "tail": [0.0, -0.2, 0.0], "deform": False},
    {"name": "Thigh", "head": [0.0, 0.0, 1.0], "tail": [0.0, -0.03, 0.5], "parent": "Root"},
    {"name": "Shin", "head": [0.0, -0.03, 0.5], "tail": [0.0, 0.0, 0.0], "parent": "Thigh", "connect": True},
]


def leg(bridge):
    bridge.ok("armature_create", name="Rig", bones=LEG)
    return bpy.data.objects["Rig"]


def settle():
    bpy.context.view_layer.update()


def move(rig, bone, point):
    matrix = rig.pose.bones[bone].bone.matrix_local.copy()
    matrix.translation = Vector(point)
    rig.pose.bones[bone].matrix = matrix
    settle()


def test_ik_chain_reaches_its_target_and_keeps_the_rest_pose(bridge):
    rig = leg(bridge)
    rest = {name: (bone_world(rig, name), bone_world(rig, name, "tail")) for name in ("Thigh", "Shin")}
    result = bridge.ok("ik_chain", armature="Rig", bone="Shin")
    assert result["chain"] == ["Thigh", "Shin"] and result["target"] == "Shin_IK" and result["pole"] == "Shin_Pole"
    assert sorted(result["created"]) == ["Shin_IK", "Shin_Pole"]
    assert result["reach_error"] < IK_TOLERANCE
    assert "lower chain_length" in bridge.refuse("ik_chain", "bad_args", armature="Rig", bone="Shin", chain_length=5)
    bridge.refuse("ik_chain", "bad_args", armature="Rig", bone="Thigh", chain_length=1, target_bone="Shin_IK", target_object="Rig")
    bridge.refuse("ik_chain", "not_found", armature="Rig", bone="Ankle")
    rig = bpy.data.objects["Rig"]
    data = rig.data.bones
    assert not data["Shin_IK"].use_deform and not data["Shin_Pole"].use_deform and data["Shin_IK"].parent.name == "Root"
    settle()
    for name, (head, tail) in rest.items():
        assert distance(bone_world(rig, name), head) < 1e-4 and distance(bone_world(rig, name, "tail"), tail) < 1e-4, name
    for goal in ([0.0, -0.3, 0.3], [0.1, 0.2, 0.4], [0.0, 0.0, 0.6]):
        move(rig, "Shin_IK", goal)
        target = bone_world(rig, "Shin_IK")
        close(list(target), goal, 1e-6)
        assert distance(bone_world(rig, "Shin", "tail"), target) < IK_TOLERANCE, goal
        assert bend_direction(bone_world(rig, "Thigh"), bone_world(rig, "Shin"), target).y < -0.5, goal


def test_ik_pole_keeps_the_bend_on_its_side(bridge):
    rig = leg(bridge)
    bridge.ok("ik_chain", armature="Rig", bone="Shin", pole_distance=0.5)
    pole = bone_world(rig, "Shin_Pole")
    close(list(pole), [0.0, -0.53, 0.5], 1e-3)
    move(rig, "Shin_IK", [0.0, 0.0, 0.5])
    assert bone_world(rig, "Shin").y < -0.2
    move(rig, "Shin_Pole", [0.0, 0.53, 0.5])
    assert bone_world(rig, "Shin").y > 0.2


def test_copy_rotation_damped_track_and_limit_rotation_pose_the_bone(bridge):
    bridge.ok("armature_create", name="Rig", bones=[
        {"name": "Driver", "head": [0.0, 0.0, 0.0], "tail": [0.0, 0.0, 1.0]},
        {"name": "Follower", "head": [1.0, 0.0, 0.0], "tail": [1.0, 0.0, 1.0]},
        {"name": "Looker", "head": [2.0, 0.0, 0.0], "tail": [2.0, 0.0, 1.0]},
        {"name": "Target", "head": [2.0, -1.0, 1.0], "tail": [2.0, -1.0, 1.2], "deform": False},
        {"name": "Elbow", "head": [3.0, 0.0, 0.0], "tail": [3.0, 0.0, 1.0]},
    ])
    rig = bpy.data.objects["Rig"]
    bridge.ok("bone_constraint", armature="Rig", bone="Follower", type="copy_rotation", target_bone="Driver", space="local")
    bridge.ok("bone_constraint", armature="Rig", bone="Looker", type="damped_track", target_bone="Target")
    limited = bridge.ok("bone_constraint", armature="Rig", bone="Elbow", type="limit_rotation", axes=["x"], min=[0.0, 0.0, 0.0], max=[45.0, 0.0, 0.0])
    assert limited["constraints"] == ["Limit Rotation"]
    rig.pose.bones["Driver"].rotation_mode = "XYZ"
    rig.pose.bones["Driver"].rotation_euler = (math.radians(30.0), 0.0, 0.0)
    rig.pose.bones["Elbow"].rotation_mode = "XYZ"
    rig.pose.bones["Elbow"].rotation_euler = (math.radians(80.0), 0.0, 0.0)
    settle()
    driver = rig.pose.bones["Driver"].matrix.to_3x3()
    follower = rig.pose.bones["Follower"].matrix.to_3x3()
    assert max(abs(a - b) for row_a, row_b in zip(driver, follower) for a, b in zip(row_a, row_b)) < 1e-5
    looker = rig.pose.bones["Looker"]
    aim = (bone_world(rig, "Target") - bone_world(rig, "Looker")).normalized()
    assert (looker.tail - looker.head).normalized().dot(aim) > 0.99999
    elbow = rig.pose.bones["Elbow"]
    close(math.degrees((elbow.tail - elbow.head).angle(Vector((0.0, 0.0, 1.0)))), 45.0, 1e-3)
    bridge.refuse("bone_constraint", "bad_args", armature="Rig", bone="Follower", type="copy_rotation")
    bridge.refuse("bone_constraint", "bad_args", armature="Rig", bone="Elbow", type="limit_rotation", target_bone="Driver")
    bridge.refuse("bone_constraint", "bad_args", armature="Rig", bone="Elbow", type="limit_rotation", min=[50.0, 0.0, 0.0], max=[10.0, 0.0, 0.0])


def constrained_tips(rig, frames):
    tips = []
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        tips.append((bone_world(rig, "Shin", "tail"), bone_world(rig, "Shin")))
    return tips


def test_constraints_bake_into_keys_that_match_the_constrained_pose_on_export(bridge):
    leg(bridge)
    bridge.ok("add_primitive", type="cylinder", name="Shank", radius=0.05, depth=1.0, location=[0.0, -0.015, 0.5])
    bridge.ok("skin_bind", meshes=["Shank"], armature="Rig")
    bridge.ok("ik_chain", armature="Rig", bone="Shin")
    keys = [{"frame": 1, "value": [0.0, 0.0, 0.0]}, {"frame": 11, "value": [0.0, -0.35, 0.35]}, {"frame": 21, "value": [0.15, -0.1, 0.2]}]
    bridge.ok("clip_keys", clip="kick", object="Rig", bone="Shin_IK", channel="location", keys=keys, interpolation="linear")
    rig = bpy.data.objects["Rig"]
    bridge.ok("clip_pose", clip="kick", frame=1)
    frames = list(range(1, 22, 4))
    expected = constrained_tips(rig, frames)
    assert distance(expected[2][0], expected[0][0]) > 0.3
    bridge.ok("clip_pose", rest=True)
    result = bridge.ok("export", path="kick.glb", names=["Shank"])
    assert result["baked_constraints"] == ["Rig"] and result["armatures"] == ["Rig"]
    assert rig.pose.bones["Shin"].constraints[0].enabled and not any(action.name.startswith("blendworks_baked_") for action in bpy.data.actions)
    assert [action.name for action in bpy.data.actions] == ["kick"]
    bridge.ok("new_scene")
    for action in list(bpy.data.actions):
        if action.users == 0:
            bpy.data.actions.remove(action)
    bridge.ok("import", path="kick.glb")
    imported = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    assert all(len(bone.constraints) == 0 for bone in imported.pose.bones)
    assert [action.name for action in bpy.data.actions] == ["kick"], [(action.name, [slot.identifier for slot in action.slots]) for action in bpy.data.actions]
    data = imported.animation_data or imported.animation_data_create()
    data.action = bpy.data.actions["kick"]
    data.action_slot = next(slot for slot in data.action.slots if slot.target_id_type == "OBJECT" and slot.name_display == imported.name)
    for (tip, knee), (baked_tip, baked_knee) in zip(expected, constrained_tips(imported, frames)):
        assert distance(tip, baked_tip) < IK_TOLERANCE and distance(knee, baked_knee) < IK_TOLERANCE, (tip, baked_tip)


run(globals())
