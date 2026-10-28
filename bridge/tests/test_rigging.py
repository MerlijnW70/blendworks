import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run

from blendworks_bridge.bones import mirrored_name

ARM = [
    {"name": "UpperArm.L", "head": [0.2, 0.0, 1.4], "tail": [0.5, 0.05, 1.3], "roll": 30.0},
    {"name": "LowerArm.L", "head": [0.5, 0.05, 1.3], "tail": [0.75, 0.0, 1.2], "parent": "UpperArm.L", "connect": True, "roll": -20.0},
    {"name": "Spine", "head": [0.0, 0.0, 1.0], "tail": [0.0, 0.0, 1.4]},
]


def bones_by_name(result):
    return {bone["name"]: bone for bone in result["bones"]}


def test_armature_create_places_bones_by_head_tail_roll_parent_and_deform(bridge):
    result = bridge.ok("armature_create", name="Rig", bones=ARM + [{"name": "Target", "head": [0.8, 0.0, 1.2], "tail": [0.8, 0.0, 1.3], "deform": False}])
    bones = bones_by_name(result)
    close(bones["UpperArm.L"]["head"], [0.2, 0.0, 1.4])
    close(bones["UpperArm.L"]["tail"], [0.5, 0.05, 1.3])
    close(bones["UpperArm.L"]["roll"], 30.0, 1e-3)
    close(bones["LowerArm.L"]["roll"], -20.0, 1e-3)
    assert bones["LowerArm.L"]["parent"] == "UpperArm.L" and bones["LowerArm.L"]["connect"] is True
    assert bones["Target"]["deform"] is False and bones["Spine"]["deform"] is True
    assert bpy.data.objects["Rig"].type == "ARMATURE"
    assert "already exists" in bridge.refuse("armature_create", "bad_args", name="Rig")
    bridge.refuse("armature_create", "bad_args", name="Other", bones=[{"name": "A", "head": [0, 0, 0], "tail": [0, 0, 1], "connect": True}])
    bridge.refuse("rig_info", "not_found", armature="Nope")
    bridge.ok("add_primitive", type="cube", name="Box")
    assert "not an armature" in bridge.refuse("rig_info", "bad_args", armature="Box")


def test_bone_add_and_bone_edit_rename_move_orient_and_reparent(bridge):
    bridge.ok("armature_create", name="Rig", bones=ARM)
    bridge.ok("add_primitive", type="cube", name="Body", size=0.2)
    bpy.data.objects["Body"].vertex_groups.new(name="Spine")
    bpy.data.objects["Body"].modifiers.new("Armature", "ARMATURE").object = bpy.data.objects["Rig"]
    added = bridge.ok("bone_add", armature="Rig", bones=[{"name": "Head", "head": [0.0, 0.0, 1.45], "tail": [0.0, 0.0, 1.7], "parent": "Spine"}])
    assert added["added"] == ["Head"] and added["count"] == 4
    edited = bridge.ok("bone_edit", armature="Rig", bones=[
        {"name": "Spine", "rename": "Chest", "tail": [0.0, 0.05, 1.42], "roll": 15.0},
        {"name": "UpperArm.L", "parent": "Chest"},
        {"name": "Head", "deform": False, "clear_parent": True},
    ])
    bones = bones_by_name(edited)
    assert edited["renamed"] == {"Spine": "Chest"}
    close(bones["Chest"]["tail"], [0.0, 0.05, 1.42])
    close(bones["Chest"]["roll"], 15.0, 1e-3)
    assert bones["UpperArm.L"]["parent"] == "Chest"
    assert bones["Head"]["parent"] is None and bones["Head"]["deform"] is False
    assert "Chest" in bpy.data.objects["Body"].vertex_groups and "Spine" not in bpy.data.objects["Body"].vertex_groups


def test_bone_edit_refuses_loops_clashes_and_zero_length(bridge):
    bridge.ok("armature_create", name="Rig", bones=ARM)
    before = bones_by_name(bridge.ok("rig_info", armature="Rig"))
    assert "loop" in bridge.refuse("bone_edit", "bad_args", armature="Rig", bones=[{"name": "UpperArm.L", "parent": "LowerArm.L"}])
    bridge.refuse("bone_edit", "bad_args", armature="Rig", bones=[{"name": "Spine", "rename": "UpperArm.L"}])
    bridge.refuse("bone_edit", "bad_args", armature="Rig", bones=[{"name": "Spine", "tail": [0.0, 0.0, 1.0]}])
    bridge.refuse("bone_add", "bad_args", armature="Rig", bones=[{"name": "Spine", "head": [0, 0, 0], "tail": [0, 0, 1]}])
    bridge.refuse("bone_edit", "not_found", armature="Rig", bones=[{"name": "Nope"}])
    assert bones_by_name(bridge.ok("rig_info", armature="Rig")) == before


def test_bone_mirror_makes_symmetric_bones_by_name_and_position(bridge):
    assert [mirrored_name(name) for name in ("LeftHand", "arm.L", "thigh_R", "Spine")] == ["RightHand", "arm.R", "thigh_L", None]
    bridge.ok("armature_create", name="Rig", bones=ARM + [{"name": "LeftLeg", "head": [0.1, 0.0, 0.9], "tail": [0.12, -0.02, 0.5], "parent": "Spine", "roll": 12.0}])
    mirrored = bridge.ok("bone_mirror", armature="Rig")
    assert {pair["from"]: pair["to"] for pair in mirrored["pairs"]} == {"UpperArm.L": "UpperArm.R", "LowerArm.L": "LowerArm.R", "LeftLeg": "RightLeg"}
    assert mirrored["created"] == ["LowerArm.R", "RightLeg", "UpperArm.R"]
    bones = bones_by_name(bridge.ok("rig_info", armature="Rig"))
    for left, right in (("UpperArm.L", "UpperArm.R"), ("LowerArm.L", "LowerArm.R"), ("LeftLeg", "RightLeg")):
        for end in ("head", "tail"):
            x, y, z = bones[left][end]
            close(bones[right][end], [-x, y, z], 1e-5)
        close(bones[right]["roll"], -bones[left]["roll"], 1e-3)
        close(bones[right]["length"], bones[left]["length"], 1e-6)
    assert bones["LowerArm.R"]["parent"] == "UpperArm.R" and bones["LowerArm.R"]["connect"] is True
    assert bones["RightLeg"]["parent"] == "Spine"
    bridge.ok("bone_edit", armature="Rig", bones=[{"name": "UpperArm.L", "head": [0.25, 0.0, 1.45]}])
    again = bridge.ok("bone_mirror", armature="Rig", bones=["UpperArm.L"])
    assert again["created"] == []
    close(again["pairs"][0]["head"], [-0.25, 0.0, 1.45], 1e-5)
    assert "not named" in bridge.refuse("bone_mirror", "bad_args", armature="Rig", bones=["Spine"])


def test_humanoid_template_fits_the_bounds_and_returns_the_bone_map(bridge):
    result = bridge.ok("rig_template", template="humanoid", name="Rig", bounds={"min": [-0.5, -0.15, 0.0], "max": [0.5, 0.15, 1.8]})
    roles = result["bone_map"]
    expected = {"hips": "Hips", "spine": "Spine", "chest": "Chest", "neck": "Neck", "head": "Head", "leftHand": "LeftHand", "rightHand": "RightHand", "leftUpperLeg": "LeftUpperLeg", "rightFoot": "RightFoot", "leftToes": "LeftToes", "root": "Root"}
    assert expected.items() <= roles.items(), roles
    assert len(roles) == 22 and result["count"] == 22
    bones = bones_by_name(result)
    close(bones["Head"]["tail"][2], 1.8, 1e-6)
    close(bones["Root"]["head"], [0.0, 0.0, 0.0])
    assert bones["Root"]["deform"] is False and bones["Hips"]["parent"] == "Root"
    close(bones["LeftHand"]["tail"][0], 0.5, 1e-4)
    for name, bone in bones.items():
        for end in ("head", "tail"):
            assert -0.5 - 1e-6 <= bone[end][0] <= 0.5 + 1e-6 and 0.0 - 1e-6 <= bone[end][2] <= 1.8 + 1e-6, (name, bone)
        if name.startswith("Left"):
            assert bone["head"][0] > 0
            other = bones["Right" + name[4:]]
            close(other["head"], [-bone["head"][0], bone["head"][1], bone["head"][2]], 1e-6)
    assert bridge.ok("rig_info", armature="Rig")["bone_map"] == roles


def test_templates_follow_landmarks_and_mirror_the_right_side(bridge):
    landmarks = [{"name": "left_knee", "point": [0.12, -0.03, 0.48]}, {"name": "hips", "point": [0.0, 0.01, 0.95]}, {"name": "right_ankle", "point": [-0.13, 0.0, 0.09]}]
    bones = bones_by_name(bridge.ok("rig_template", template="humanoid", name="Rig", bounds={"min": [-0.6, -0.2, 0.0], "max": [0.6, 0.2, 1.75]}, landmarks=landmarks))
    close(bones["LeftLowerLeg"]["head"], [0.12, -0.03, 0.48])
    close(bones["RightLowerLeg"]["head"], [-0.12, -0.03, 0.48])
    close(bones["RightLowerLeg"]["tail"], [-0.13, 0.0, 0.09])
    close(bones["Hips"]["head"], [0.0, 0.01, 0.95])
    assert "unknown humanoid landmark" in bridge.refuse("rig_template", "bad_args", template="humanoid", name="Rig2", bounds={"min": [0, 0, 0], "max": [1, 1, 1]}, landmarks=[{"name": "tail_tip", "point": [0, 0, 0]}])


def test_quadruped_template_faces_minus_y_with_four_legs(bridge):
    bridge.ok("add_primitive", type="cube", name="Body", size=1.0)
    bridge.ok("transform", name="Body", scale=[0.3, 1.0, 0.7], location=[0.0, 0.0, 0.35])
    bridge.ok("apply_transform", name="Body")
    result = bridge.ok("rig_template", template="quadruped", name="Rig", fit=["Body"])
    bones = bones_by_name(result)
    roles = result["bone_map"]
    for side in ("left", "right"):
        for end in ("Front", "Back"):
            chain = [roles[f"{side}{end}{part}"] for part in ("UpperLeg", "LowerLeg", "Foot")]
            close(bones[chain[2]]["tail"][2], 0.0, 1e-6)
            assert bones[chain[1]]["parent"] == chain[0] and bones[chain[2]]["parent"] == chain[1]
    assert bones["Head"]["tail"][1] < bones["Head"]["head"][1] < bones["Hips"]["head"][1]
    assert bones["Tail"]["tail"][1] > bones["Hips"]["head"][1]
    assert bones[roles["leftFrontUpperLeg"]]["parent"] == "Chest" and bones[roles["leftBackUpperLeg"]]["parent"] == "Hips"


def test_prop_templates_put_the_moving_bone_on_its_hinge_axle_or_stroke(bridge):
    hinge = bones_by_name(bridge.ok("rig_template", template="hinge", name="Chest", bounds={"min": [-0.4, -0.25, 0.0], "max": [0.4, 0.25, 0.5]}, landmarks=[{"name": "hinge", "point": [0.0, 0.25, 0.4]}]))
    close(hinge["Lid"]["head"], [0.0, 0.25, 0.4])
    assert hinge["Lid"]["parent"] == "Base"
    piston = bridge.ok("rig_template", template="piston", name="Pump", bounds={"min": [-0.1, -0.1, 0.0], "max": [0.1, 0.1, 1.0]})
    assert piston["bone_map"] == {"base": "Base", "rod": "Rod"}
    close(bones_by_name(piston)["Rod"]["head"], [0.0, 0.0, 0.5])
    close(bones_by_name(piston)["Rod"]["tail"], [0.0, 0.0, 1.0])
    wheel = bridge.ok("rig_template", template="wheel", name="Cart", bounds={"min": [-0.05, -0.3, 0.0], "max": [0.05, 0.3, 0.6]}, axis=[1.0, 0.0, 0.0])
    close(bones_by_name(wheel)["Wheel"]["head"], [0.0, 0.0, 0.3])
    assert bridge.ok("rig_info", armature="Cart")["template"] == "wheel"
    bridge.refuse("rig_template", "bad_args", template="humanoid", name="Bad", bounds={"min": [0, 0, 0], "max": [1, 1, 1]}, axis=[1, 0, 0])
    bridge.refuse("rig_template", "bad_args", template="wheel", name="Bad", bounds={"min": [0, 0, 0], "max": [1, 1, 1]}, axis=[0, 0, 0])


run(globals())
