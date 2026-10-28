import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Vector

from harness import close, run
from rig_helpers import bone_world, chest, distance, dominant_vertices, evaluated_world, fox, hero

from blendworks_bridge.clips import CLIP_NAME
from blendworks_bridge.gaits import STANCE
from blendworks_bridge.motion_presets import PRESETS

CONTACT_BAND = 0.004
PLANT_DRIFT = 0.002


def pose(bridge, clip, frame):
    bridge.ok("clip_pose", clip=clip, frame=frame)


def test_clip_keys_animate_objects_and_bones_with_interpolation(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=0.5)
    bridge.ok("armature_create", name="Rig", bones=[{"name": "Arm", "head": [0, 0, 0], "tail": [0, 0, 1]}])
    keys = [{"frame": 1, "value": [0.0, 0.0, 0.0]}, {"frame": 11, "value": [2.0, 0.0, 1.0]}]
    moved = bridge.ok("clip_keys", clip="slide", object="Box", channel="location", keys=keys, interpolation="linear")
    assert moved["owners"] == ["Box"] and moved["frame_start"] == 1 and moved["frame_end"] == 11 and moved["channels"] == 3
    bridge.ok("clip_keys", clip="slide", object="Box", channel="scale", keys=[{"frame": 1, "value": [1, 1, 1]}, {"frame": 11, "value": [2, 2, 2]}], interpolation="constant")
    bridge.ok("clip_keys", clip="slide", object="Rig", bone="Arm", channel="rotation", keys=[{"frame": 1, "value": [0, 0, 0]}, {"frame": 11, "value": [90, 0, 0]}], interpolation="linear")
    pose(bridge, "slide", 6)
    box = bpy.data.objects["Box"]
    close(list(box.location), [1.0, 0.0, 0.5], 1e-5)
    close(list(box.scale), [1.0, 1.0, 1.0], 1e-6)
    tail = bone_world(bpy.data.objects["Rig"], "Arm", "tail")
    close(math.degrees(Vector((0, 0, 1)).angle(tail)), 45.0, 0.5)
    pose(bridge, "slide", 11)
    close(list(box.scale), [2.0, 2.0, 2.0], 1e-6)
    info = bridge.ok("clip_info")
    assert [clip["name"] for clip in info["clips"]] == ["slide"]
    assert info["clips"][0]["owners"] == ["Box", "Rig"] and info["clips"][0]["bones"] == ["Arm"]
    assert sorted((track["owner"], track["track"], track["muted"]) for track in info["tracks"]) == [("Box", "slide", True), ("Rig", "slide", True)]
    bridge.ok("clip_pose", rest=True)
    assert box.animation_data.action is None
    bridge.refuse("clip_pose", "bad_args")
    assert CLIP_NAME.match("walk_2") and not CLIP_NAME.match("bad/name")
    bridge.refuse("clip_keys", "bad_args", clip="bad/name", object="Box", channel="location", keys=keys)
    bridge.refuse("clip_pose", "bad_args", clip="slide", rest=True)
    bridge.refuse("clip_pose", "not_found", clip="missing")
    bridge.refuse("clip_keys", "bad_args", clip="slide", object="Box", channel="location", keys=[{"frame": 1, "value": [1.0]}])
    bridge.refuse("clip_keys", "not_found", clip="slide", object="Box", channel="value", shape_key="Smile", keys=[{"frame": 1, "value": [1.0]}])


def test_clip_edit_closes_loops_sets_ranges_cycles_renames_and_deletes(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=0.5)
    keys = [{"frame": 1, "value": [0.0, 0.0, 0.0]}, {"frame": 13, "value": [0.0, 0.0, 1.0]}, {"frame": 24, "value": [0.0, 0.0, 0.3]}]
    bridge.ok("clip_keys", clip="hop", object="Box", channel="location", keys=keys)
    assert "come after" in bridge.refuse("clip_edit", "bad_args", clip="hop", frame_end=0)
    bridge.refuse("clip_edit", "bad_args", clip="hop", delete=True, rename="x")
    edited = bridge.ok("clip_edit", clip="hop", frame_end=25, make_loop=True, cyclic=True, rename="bounce")
    assert edited["name"] == "bounce" and edited["frame_end"] == 25 and edited["cyclic"] is True
    pose(bridge, "bounce", 25)
    close(list(bpy.data.objects["Box"].location), [0.0, 0.0, 0.0], 1e-6)
    pose(bridge, "bounce", 25 + 12)
    close(bpy.data.objects["Box"].location.z, 1.0, 1e-5)
    tracks = bridge.ok("clip_info")["tracks"]
    assert [track["track"] for track in tracks] == ["bounce"], tracks
    linear = bridge.ok("clip_edit", clip="bounce", interpolation="linear")
    assert linear["keyframes"] == 12
    assert bridge.ok("clip_edit", clip="bounce", delete=True) == {"deleted": "bounce"}
    bridge.refuse("clip_edit", "not_found", clip="bounce")
    bridge.refuse("clip_info", "not_found", clip="bounce")
    left = bridge.ok("clip_info")
    assert left == {"fps": 24.0, "clips": [], "tracks": []}, left


def stance_frames(result, offset):
    frames, start, stance = result["frames"], int(result["frame_start"]), result["stance"]
    first = round(((1.0 - offset) % 1.0) * frames)
    return [start + first + step for step in range(frames) if 0.02 < step / frames < stance - 0.02]


def test_humanoid_walk_plants_each_foot_in_stance_and_covers_the_stride(bridge):
    hero(bridge)
    result = bridge.ok("animation_preset", armature="HeroRig", preset="walk", root_motion=True, stride=0.9, cadence=110)
    assert result["frames"] == round(120.0 / 110 * 24) and result["root_motion"] is True and result["stance"] == STANCE["humanoid"]["walk"]
    close(result["stride"], 0.9, 1e-9)
    close(result["speed"], 0.9 / (result["frames"] / 24.0), 1e-6)
    rig = bpy.data.objects["HeroRig"]
    legs = bpy.data.objects["HeroLegs"]
    for side, offset in (("Left", 0.0), ("Right", 0.5)):
        sole = dominant_vertices(legs, {f"{side}Foot", f"{side}Toes"})
        frames = stance_frames(result, offset)
        lows, balls = [], []
        for frame in frames:
            pose(bridge, "walk", frame)
            lows.append(evaluated_world(legs)[sole][:, 2].min())
            balls.append(bone_world(rig, f"{side}Toes"))
        assert max(lows) - min(lows) < CONTACT_BAND and abs(min(lows)) < CONTACT_BAND, (side, lows)
        assert max(distance(ball, balls[0]) for ball in balls) < PLANT_DRIFT, (side, frames, [round(distance(ball, balls[0]), 5) for ball in balls])
        pose(bridge, "walk", frames[0] + result["frames"])
        close(distance(bone_world(rig, f"{side}Toes"), balls[0]), 0.9, 1e-3)
    assert result["leg_length"] > 0.8 and 0 <= result["hip_drop"] < 0.1


def test_in_place_walk_moves_the_planted_foot_back_at_the_walking_speed(bridge):
    hero(bridge)
    result = bridge.ok("animation_preset", armature="HeroRig", preset="walk", speed=1.2)
    rig = bpy.data.objects["HeroRig"]
    frames = stance_frames(result, 0.0)
    pose(bridge, "walk", frames[0])
    first = bone_world(rig, "LeftToes")
    pose(bridge, "walk", frames[-1])
    last = bone_world(rig, "LeftToes")
    close((last.y - first.y) / ((frames[-1] - frames[0]) / 24.0), result["speed"], 1e-3)
    close(result["speed"] * result["seconds"], result["stride"], 1e-5)
    pose(bridge, "walk", result["frame_start"])
    begin = evaluated_world(bpy.data.objects["HeroLegs"])
    pose(bridge, "walk", result["frame_end"])
    assert abs(evaluated_world(bpy.data.objects["HeroLegs"]) - begin).max() < 1e-5
    assert distance(bone_world(rig, "Root"), rig.matrix_world @ rig.data.bones["Root"].head_local) < 1e-9


def test_quadruped_trot_and_walk_plant_their_paws(bridge):
    fox(bridge)
    rig = bpy.data.objects["FoxRig"]
    legs = bpy.data.objects["FoxLegs"]
    for preset, offsets in (("trot", {"LeftFront": 0.0, "RightBack": 0.0, "RightFront": 0.5}), ("walk", {"LeftBack": 0.0, "LeftFront": 0.25})):
        result = bridge.ok("animation_preset", armature="FoxRig", preset=preset, root_motion=True)
        for leg, offset in offsets.items():
            paw = dominant_vertices(legs, {f"{leg}Foot"})
            lows, tips = [], []
            for frame in stance_frames(result, offset):
                pose(bridge, preset, frame)
                lows.append(evaluated_world(legs)[paw][:, 2].min())
                tips.append(bone_world(rig, f"{leg}Foot", "tail"))
            assert max(lows) - min(lows) < CONTACT_BAND and abs(min(lows)) < 0.01, (preset, leg, lows)
            assert max(distance(tip, tips[0]) for tip in tips) < PLANT_DRIFT, (preset, leg, [round(distance(tip, tips[0]), 5) for tip in tips])
    assert bridge.refuse("animation_preset", "bad_args", armature="FoxRig", preset="walk", stride=5.0).startswith("the stride")


def test_idle_loops_and_keeps_the_feet_still(bridge):
    hero(bridge)
    result = bridge.ok("animation_preset", armature="HeroRig", preset="idle", frames=48)
    assert result["frame_end"] - result["frame_start"] == 48 and result["cyclic"] is True
    rig = bpy.data.objects["HeroRig"]
    body = bpy.data.objects["HeroBody"]
    pose(bridge, "idle", 1)
    start = evaluated_world(body)
    feet = [bone_world(rig, "LeftToes"), bone_world(rig, "RightFoot")]
    pose(bridge, "idle", 13)
    assert abs(evaluated_world(body) - start).max() > 0.005
    assert distance(bone_world(rig, "LeftToes"), feet[0]) < 1e-4 and distance(bone_world(rig, "RightFoot"), feet[1]) < 1e-4
    pose(bridge, "idle", 49)
    assert abs(evaluated_world(body) - start).max() < 1e-5


def test_prop_presets_open_spin_turn_and_pump(bridge):
    assert PRESETS == ("walk", "trot", "idle", "open", "spin", "turn", "pump")
    chest(bridge)
    rig = bpy.data.objects["ChestRig"]
    tip = bone_world(rig, "Lid", "tail")
    opened = bridge.ok("animation_preset", armature="ChestRig", preset="open", angle=90.0, frames=40)
    pose(bridge, "open", 1 + 20)
    lid = bone_world(rig, "Lid", "tail")
    close(list(lid), [tip.x, 0.26, 0.4 + 0.52], 1e-4)
    pose(bridge, "open", 41)
    close(list(bone_world(rig, "Lid", "tail")), list(tip), 1e-6)
    assert opened["loop"] is True and opened["keyed_bones"] == ["Lid"], opened
    one_way = bridge.ok("animation_preset", armature="ChestRig", preset="open", clip="open_once", loop=False, frames=24)
    assert one_way["cyclic"] is False and one_way["loop"] is False
    bridge.ok("rig_template", template="wheel", name="Cart", bounds={"min": [-0.05, -0.3, 0.0], "max": [0.05, 0.3, 0.6]})
    spin = bridge.ok("animation_preset", armature="Cart", preset="spin", turns=2.0, frames=32)
    cart = bpy.data.objects["Cart"]
    wheel = cart.pose.bones["Wheel"]
    pose(bridge, "spin", 1 + 4)
    close(math.degrees(wheel.matrix.to_3x3().col[2].angle(Vector((0, 0, 1)))), 90.0, 1e-3)
    assert spin["amount"] == 720.0 and spin["cyclic"] is True
    bridge.ok("rig_template", template="piston", name="Pump", bounds={"min": [-0.1, -0.1, 0.0], "max": [0.1, 0.1, 1.0]})
    bridge.ok("animation_preset", armature="Pump", preset="pump", distance=0.2, frames=20)
    pose(bridge, "pump", 11)
    close(bone_world(bpy.data.objects["Pump"], "Rod").z, 0.7, 1e-6)
    bridge.ok("animation_preset", armature="Cart", preset="turn", angle=30.0, frames=20, clip="wobble")
    pose(bridge, "wobble", 11)
    close(math.degrees(wheel.matrix.to_3x3().col[2].angle(Vector((0, 0, 1)))), 30.0, 1e-3)
    bridge.refuse("animation_preset", "bad_args", armature="ChestRig", preset="walk")
    bridge.refuse("animation_preset", "bad_args", armature="Pump", preset="open")


run(globals())
