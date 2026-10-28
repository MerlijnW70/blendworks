import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from rig_helpers import accessor_floats, evaluated_world, gltf, hero

from blendworks_bridge.commands.shape_keys import MAX_SHAPE_KEYS

MAX_INFLUENCES = 4


def joint_attributes(document):
    return [set(primitive["attributes"]) for mesh in document["meshes"] for primitive in mesh["primitives"]]


def test_glb_carries_the_armature_skins_inverse_bind_matrices_and_every_clip_by_name(bridge):
    meshes, rig = hero(bridge)
    bridge.ok("animation_preset", armature=rig, preset="walk")
    bridge.ok("animation_preset", armature=rig, preset="idle")
    result = bridge.ok("export", path="hero.glb", names=meshes)
    assert result["armatures"] == [rig] and result["options"]["animation"] == "clips" and rig in result["objects"]
    document, binary = gltf(os.path.join(bridge.workspace, "hero.glb"))
    bones = len(bpy.data.objects[rig].data.bones)
    assert len(document["skins"]) == 1
    skin = document["skins"][0]
    assert len(skin["joints"]) == bones
    matrices = accessor_floats(document, binary, skin["inverseBindMatrices"])
    assert len(matrices) == bones and all(len(matrix) == 16 for matrix in matrices)
    names = {document["nodes"][joint]["name"] for joint in skin["joints"]}
    assert {"Hips", "Head", "LeftHand", "RightFoot"} <= names
    for attributes in joint_attributes(document):
        assert {"JOINTS_0", "WEIGHTS_0"} <= attributes and "JOINTS_1" not in attributes and "WEIGHTS_1" not in attributes
    assert sorted(animation["name"] for animation in document["animations"]) == ["idle", "walk"]
    joints = set(skin["joints"])
    for animation in document["animations"]:
        assert all(channel["target"]["node"] in joints for channel in animation["channels"])
    skinned = [node for node in document["nodes"] if "skin" in node]
    assert len(skinned) == len(meshes)


def test_glb_cuts_weights_to_four_influences_that_sum_to_one(bridge):
    bridge.ok("sweep", name="Tube", preset="circle", radius=0.06, segments=12, waypoints=[[0.0, 0.0, 0.05 * step] for step in range(25)])
    bones = [{"name": f"B{index}", "head": [0.0, 0.0, 0.1 * index], "tail": [0.0, 0.0, 0.1 * index + 0.1], "parent": f"B{index - 1}" if index else None} for index in range(12)]
    bridge.ok("armature_create", name="Rig", bones=[{key: value for key, value in bone.items() if value is not None} for bone in bones])
    bound = bridge.ok("skin_bind", meshes=["Tube"], armature="Rig", max_influences=8, smooth=12)
    assert bound["max_influences"] > MAX_INFLUENCES
    bridge.ok("export", path="tube.glb")
    document, binary = gltf(os.path.join(bridge.workspace, "tube.glb"))
    primitive = document["meshes"][0]["primitives"][0]
    assert "JOINTS_1" not in primitive["attributes"]
    weights = accessor_floats(document, binary, primitive["attributes"]["WEIGHTS_0"])
    assert max(sum(1 for value in entry if value > 0) for entry in weights) == MAX_INFLUENCES
    for entry in weights:
        close(sum(entry), 1.0, 1e-3)


def test_shape_keys_add_animate_and_export(bridge):
    bridge.ok("add_primitive", type="sphere", name="Face", radius=0.5, segments=16, rings=8)
    bridge.ok("vertex_group", name="Face", group="cheek", box={"min": [0.2, -1.0, -1.0], "max": [1.0, 1.0, 1.0]})
    added = bridge.ok("shape_key_add", name="Face", key="puff", vertex_group="cheek", offset=[0.1, 0.0, 0.0], normal=0.02)
    assert added["keys"] == ["Basis", "puff"] and added["moved_vertices"] > 0 and len(added["keys"]) < MAX_SHAPE_KEYS
    close(added["largest_offset"], 0.12, 0.005)
    bridge.ok("shape_key_add", name="Face", key="lift", offset=[0.0, 0.0, 0.05])
    clip = bridge.ok("clip_keys", clip="talk", object="Face", shape_key="puff", channel="value", keys=[{"frame": 1, "value": [0.0]}, {"frame": 11, "value": [1.0]}, {"frame": 21, "value": [0.0]}], interpolation="linear")
    assert clip["owners"] == ["Key"] or clip["owners"][0].startswith("Key")
    rest = evaluated_world(bpy.data.objects["Face"])
    bridge.ok("clip_pose", clip="talk", frame=6)
    half = evaluated_world(bpy.data.objects["Face"])
    close(float(abs(half - rest).max()), 0.06, 0.003)
    bridge.ok("clip_pose", rest=True)
    bridge.ok("export", path="face.glb")
    document, binary = gltf(os.path.join(bridge.workspace, "face.glb"))
    mesh = document["meshes"][0]
    assert len(mesh["primitives"][0].get("targets", [])) == 2 and mesh.get("extras", {}).get("targetNames") == ["puff", "lift"], mesh
    animation = document["animations"][0]
    assert animation["name"] == "talk" and [channel["target"]["path"] for channel in animation["channels"]] == ["weights"], document["animations"]
    values = accessor_floats(document, binary, animation["samplers"][0]["output"])
    assert max(value[0] for value in values) > 0.99 and abs(values[0][0]) < 1e-6, (values, document["accessors"][animation["samplers"][0]["output"]])
    bridge.refuse("shape_key_add", "bad_args", name="Face", key="puff", offset=[0.1, 0.0, 0.0])
    bridge.refuse("shape_key_add", "bad_args", name="Face", key="still")
    bridge.refuse("shape_key_add", "not_found", name="Face", key="other", vertex_group="nope", offset=[0.0, 0.0, 0.1])


def test_a_clip_on_several_objects_exports_as_one_animation(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=0.5)
    bridge.ok("armature_create", name="Rig", bones=[{"name": "Arm", "head": [0, 0, 0], "tail": [0, 0, 1]}])
    bridge.ok("add_primitive", type="cylinder", name="Rod", radius=0.05, depth=1.0, location=[0.0, 0.0, 0.5])
    bridge.ok("skin_bind", meshes=["Rod"], armature="Rig")
    bridge.ok("clip_keys", clip="wave", object="Box", channel="location", keys=[{"frame": 1, "value": [0, 0, 0]}, {"frame": 10, "value": [0, 0, 1]}])
    bridge.ok("clip_keys", clip="wave", object="Rig", bone="Arm", channel="rotation", keys=[{"frame": 1, "value": [0, 0, 0]}, {"frame": 10, "value": [45, 0, 0]}])
    bridge.ok("clip_keys", clip="rest", object="Box", channel="scale", keys=[{"frame": 1, "value": [1, 1, 1]}, {"frame": 5, "value": [2, 2, 2]}])
    bridge.ok("export", path="wave.glb")
    document, _ = gltf(os.path.join(bridge.workspace, "wave.glb"))
    animations = {animation["name"]: animation for animation in document["animations"]}
    assert sorted(animations) == ["rest", "wave"], sorted(animations)
    nodes = {document["nodes"][channel["target"]["node"]]["name"] for channel in animations["wave"]["channels"]}
    assert {"Box", "Arm"} <= nodes, nodes


def test_existing_export_options_stay_valid_with_a_rig(bridge):
    for action in list(bpy.data.actions):
        if action.users == 0:
            bpy.data.actions.remove(action)
    meshes, rig = hero(bridge)
    bridge.ok("animation_preset", armature=rig, preset="idle", frames=24)
    still = bridge.ok("export", path="still.glb", names=meshes, animation="none", draco=True, yup=False)
    document, _ = gltf(os.path.join(bridge.workspace, "still.glb"))
    assert "animations" not in document and still["options"]["draco"] is True and len(document["skins"]) == 1
    actions = bridge.ok("export", path="actions.glb", names=meshes, animation="actions", apply_modifiers=False)
    named = [animation["name"] for animation in gltf(os.path.join(bridge.workspace, "actions.glb"))[0]["animations"]]
    assert named == ["idle"], named
    assert actions["options"]["animation"] == "actions"
    bridge.refuse("export", "bad_args", path="bad.glb", animation="actions", bake_constraints=True)
    bridge.refuse("export", "bad_args", path="bad.fbx", animation="none")
    fbx = bridge.ok("export", path="hero.fbx", names=meshes)
    assert rig in fbx["objects"] and fbx["bytes"] > 10_000


run(globals())
