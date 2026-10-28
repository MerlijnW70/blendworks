import math

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from ..bones import get_armature, rig_metadata
from ..clips import (
    INTERPOLATIONS,
    MAX_FRAME,
    all_curves,
    assign,
    channels,
    check_clip_name,
    clip,
    curve,
    describe_clip,
    find_clip,
    key_at,
    key_frames,
    owners,
    refresh_tracks,
    release,
    remove_clip,
    scene_fps,
    set_cyclic,
    set_range,
    write_keys,
)
from ..errors import bad_args, not_found
from ..motion_presets import PRESETS, gait, idle, moving_bones, prop_motion, write_rows
from ..registry import command
from ..schema import array, boolean, integer, length, number, obj as object_schema, string, vector3
from ..util import get_object

CHANNELS = {"location": 3, "rotation": 3, "scale": 3, "value": 1}
KEY = object_schema(
    {
        "frame": number("Frame of the key.", -MAX_FRAME, MAX_FRAME),
        "value": array({"type": "number", "minimum": -1e6, "maximum": 1e6}, "Location [x, y, z] in metres, rotation [x, y, z] in degrees (Euler XYZ), scale [x, y, z], or a shape key [value].", 1, 3),
    },
    ["frame", "value"],
)
ROLE = object_schema({"role": string("Role, such as hips or leftUpperLeg.", max_length=64), "bone": string("Bone that plays it.", max_length=63)}, ["role", "bone"])
GAIT_FIELDS = {
    "stride": length("Walk and trot: distance covered in one cycle, in metres. Default: from the leg length.", maximum=100.0),
    "speed": length("Walk and trot: metres per second; sets the cycle length from the stride.", maximum=100.0),
    "cadence": number("Walk and trot: steps per minute (two steps per cycle); sets the cycle length.", 10.0, 600.0),
    "root_motion": boolean("Walk and trot: the Root bone travels forward (-Y) by the stride each cycle; false keeps the clip in place.", False),
    "lift": length("Walk and trot: how high a foot rises in swing, in metres.", maximum=10.0),
    "bob": number("Walk and trot: how far the hips dip twice per cycle, in metres. Default: what keeps the legs straightest, at most 8 % of the leg.", 0.0, 10.0),
    "sway": number("Humanoid walk: sideways hip sway in metres.", 0.0, 10.0),
    "arm_swing": number("Humanoid walk: arm swing in degrees either way.", 0.0, 80.0),
    "heel_angle": number("Humanoid walk: how far the heel lifts before toe-off, in degrees.", 0.0, 60.0),
}
PROP_FIELDS = {
    "bone": string("Prop presets: the bone to move. Default: the template's lid, wheel or rod.", max_length=63),
    "axis": vector3("Prop presets: the hinge, axle or stroke axis. Default: the template's axis."),
    "angle": number("open and turn: degrees to open or turn (default 100 for open, 90 for turn).", -720.0, 720.0),
    "turns": number("spin: full turns per clip (default 1).", -100.0, 100.0),
    "distance": number("pump: stroke in metres along the axis (default 0.1).", -100.0, 100.0),
    "loop": boolean("Prop presets: return to the start pose so the clip loops (spin always loops).", True),
}


def preset_roles(armature, args):
    metadata = rig_metadata(armature)
    roles = dict(metadata.get("roles", {}))
    for entry in args.get("bone_map", []):
        if entry["bone"] not in armature.data.bones:
            raise not_found(f"{armature.name} has no bone named {entry['bone']}")
        roles[entry["role"]] = entry["bone"]
    return metadata, roles


def check_timing(args):
    for name in ("speed", "cadence"):
        if name in args and "frames" in args:
            raise bad_args(f"give frames or {name}, not both")
    if "speed" in args and "cadence" in args:
        raise bad_args("give speed or cadence, not both")


@command(
    "animation_preset",
    "Animate a rig with a preset clip: walk (humanoid, quadruped), trot, idle, or a prop's open, spin, turn or pump; loops seamlessly, keys every frame.",
    {
        "armature": string("Armature object, ideally made by rig_template."),
        "preset": string("Preset clip.", list(PRESETS)),
        "clip": string("Clip name. Default: the preset name.", max_length=63),
        "start": integer("First frame of the clip.", -MAX_FRAME, MAX_FRAME, 1),
        "frames": integer("Frames in one cycle. Default: from the leg length (walk, trot), 3 s (idle), 2 s (props).", 8, 2400),
        "rig": string("Rig kind when the armature was not made by rig_template.", ["humanoid", "quadruped"]),
        "bone_map": array(ROLE, "Roles to bones when the armature was not made by rig_template, or to override some.", 1, 128),
        **GAIT_FIELDS,
        **PROP_FIELDS,
    },
    ["armature", "preset"],
    family="animation",
    intents=("make the character walk in place", "trot cycle for the dog", "idle breathing loop", "open the chest lid", "spin the wheel"),
    nearest=(("clip_keys", "to key your own poses"), ("clip_edit", "to change a clip's range, loop or name")),
)
def animation_preset(ctx, args):
    armature = get_armature(args["armature"])
    metadata, roles = preset_roles(armature, args)
    kind = args.get("rig") or metadata.get("template")
    preset = args["preset"]
    fps = scene_fps(ctx.scene)
    check_timing(args)
    if preset in ("walk", "trot", "idle"):
        if kind not in ("humanoid", "quadruped"):
            raise bad_args(f"the {preset} preset needs a humanoid or quadruped rig; set rig and bone_map for an armature not made by rig_template")
        if preset == "trot" and kind != "quadruped":
            raise bad_args("trot is a quadruped gait; use walk for a humanoid")
        rows, frames, info = idle(armature, roles, kind, fps, args) if preset == "idle" else gait(armature, roles, kind, preset, fps, args)
        travelling = [roles["root"]] if info.get("root_motion") and "root" in roles else []
        cyclic = True
    else:
        axis = Vector(args.get("axis", metadata.get("axis", [1.0, 0.0, 0.0])))
        if axis.length < 1e-6:
            raise bad_args("axis must not be zero")
        rows, frames, info = prop_motion(armature, roles, preset, fps, args, axis.normalized())
        travelling = []
        cyclic = info["loop"]
    action = clip(args.get("clip", preset))
    bones = moving_bones(rows, [bone.name for bone in armature.data.bones])
    write_rows(armature, action, rows, args["start"], bones, cyclic, travelling)
    release(armature)
    entry = describe_clip(action, fps)
    entry.update({"preset": preset, "rig": kind, "fps": round(fps, 6), "keyed_bones": bones, **info})
    return entry


def euler_quaternion(degrees, previous):
    quaternion = Euler([math.radians(value) for value in degrees], "XYZ").to_quaternion()
    if previous is not None and quaternion.dot(previous) < 0:
        quaternion = Quaternion((-quaternion.w, -quaternion.x, -quaternion.y, -quaternion.z))
    return quaternion


def key_target(obj, args):
    if "bone" in args and "shape_key" in args:
        raise bad_args("give bone or shape_key, not both")
    if "shape_key" in args:
        keys = obj.data.shape_keys if obj.type == "MESH" else None
        if keys is None or args["shape_key"] not in keys.key_blocks:
            raise not_found(f"{obj.name} has no shape key named {args['shape_key']}; shape_key_add makes one")
        if args["channel"] != "value":
            raise bad_args("a shape key takes the value channel")
        return keys, f'key_blocks["{args["shape_key"]}"].value', None
    if args["channel"] == "value":
        raise bad_args("the value channel is for shape keys; give shape_key")
    if "bone" in args:
        if obj.type != "ARMATURE" or args["bone"] not in obj.pose.bones:
            raise not_found(f"{obj.name} has no bone named {args['bone']}")
        if args["channel"] == "rotation":
            obj.pose.bones[args["bone"]].rotation_mode = "QUATERNION"
        path = {"location": "location", "rotation": "rotation_quaternion", "scale": "scale"}[args["channel"]]
        return obj, f'pose.bones["{args["bone"]}"].{path}', args["bone"]
    if args["channel"] == "rotation":
        obj.rotation_mode = "XYZ"
    return obj, {"location": "location", "rotation": "rotation_euler", "scale": "scale"}[args["channel"]], "Object Transforms"


def key_values(args, ordered):
    if args["channel"] == "rotation" and "bone" in args:
        previous = None
        values = []
        for key in ordered:
            previous = euler_quaternion(key["value"], previous)
            values.append(list(previous))
        return values
    if args["channel"] == "rotation":
        return [[math.radians(value) for value in key["value"]] for key in ordered]
    return [key["value"] for key in ordered]


@command(
    "clip_keys",
    "Key a clip: location, rotation (degrees) or scale of an object or bone, or a shape key's value, at frames, with constant, linear or bezier interpolation.",
    {
        "clip": string("Clip (action) name; made when new.", max_length=63),
        "object": string("Object to animate: a mesh, an empty, or an armature with bone."),
        "bone": string("Bone of the armature to key.", max_length=63),
        "shape_key": string("Shape key of the mesh to key; channel value.", max_length=63),
        "channel": string("What to key.", list(CHANNELS)),
        "keys": array(KEY, "Keys in any order; a key on an existing frame replaces it.", 1, 4096),
        "interpolation": string("Interpolation from each key to the next.", list(INTERPOLATIONS), "bezier"),
    },
    ["clip", "object", "channel", "keys"],
    family="animation",
    intents=("keyframe the lid rotation at frame 1 and 24", "animate a shape key value over time", "set keys on a bone"),
    nearest=(("animation_preset", "for a ready walk, trot, idle or prop loop"),),
)
def clip_keys(ctx, args):
    obj = get_object(args["object"])
    owner, path, group = key_target(obj, args)
    width = CHANNELS[args["channel"]]
    frames = [key["frame"] for key in args["keys"]]
    if len(set(frames)) != len(frames):
        raise bad_args("two keys share a frame")
    for key in args["keys"]:
        if len(key["value"]) != width:
            raise bad_args(f"the {args['channel']} channel takes {width} value(s) per key")
    action = clip(args["clip"])
    assign(owner, action)
    bag, _ = channels(action, owner)
    ordered = sorted(args["keys"], key=lambda key: key["frame"])
    values = key_values(args, ordered)
    for index in range(len(values[0])):
        fcurve = curve(bag, path, index, group)
        write_keys(fcurve, [(key["frame"], value[index]) for key, value in zip(ordered, values)], args["interpolation"])
    release(owner)
    refresh_tracks(action, [owner])
    return describe_clip(action, scene_fps(ctx.scene))


def close_loop(action):
    start, end = action.frame_range
    set_range(action, start, end)
    for _, curves in all_curves(action):
        for fcurve in curves:
            first = min(fcurve.keyframe_points, key=lambda key: key.co.x)
            key_at(fcurve, end, fcurve.evaluate(start)).interpolation = first.interpolation
            fcurve.update()


@command(
    "clip_edit",
    "Change a clip: rename it, set its frame range, cyclic playback or interpolation, close it into a seamless loop, or delete it.",
    {
        "clip": string("Clip name.", max_length=63),
        "rename": string("New clip name; also the glTF animation name.", max_length=63),
        "frame_start": number("First frame of the clip.", -MAX_FRAME, MAX_FRAME),
        "frame_end": number("Last frame of the clip.", -MAX_FRAME, MAX_FRAME),
        "cyclic": boolean("Play the clip as a cycle in Blender (Cycles modifiers on its curves)."),
        "interpolation": string("Interpolation for every key of the clip.", list(INTERPOLATIONS)),
        "make_loop": boolean("Key the last frame with the first frame's pose on every channel, so the loop does not pop."),
        "delete": boolean("Remove the clip and its NLA tracks."),
    },
    ["clip"],
    family="animation",
    intents=("make the clip loop without a pop", "rename the action to walk", "shorten the clip to 24 frames"),
    nearest=(("clip_info", "to list the clips"),),
)
def clip_edit(ctx, args):
    action = find_clip(args["clip"])
    if args.get("delete"):
        if len(args) > 2:
            raise bad_args("delete takes no other changes")
        remove_clip(action)
        return {"deleted": args["clip"]}
    if "rename" in args and args["rename"] != action.name:
        check_clip_name(args["rename"])
        if args["rename"] in bpy.data.actions:
            raise bad_args(f"a clip named {args['rename']} already exists")
        for owner, _ in owners(action):
            for track in list(owner.animation_data.nla_tracks if owner.animation_data else []):
                if track.name == action.name:
                    owner.animation_data.nla_tracks.remove(track)
        action.name = args["rename"]
    if "frame_start" in args or "frame_end" in args:
        start, end = action.frame_range
        set_range(action, args.get("frame_start", start), args.get("frame_end", end))
    if "interpolation" in args:
        for _, curves in all_curves(action):
            for fcurve in curves:
                for point in fcurve.keyframe_points:
                    point.interpolation = args["interpolation"].upper()
                fcurve.update()
    if args.get("make_loop"):
        close_loop(action)
    if "cyclic" in args:
        if args["cyclic"] and not action.use_frame_range:
            start, end = action.frame_range
            set_range(action, start, end)
        set_cyclic(action, args["cyclic"])
    refresh_tracks(action)
    return describe_clip(action, scene_fps(ctx.scene))


@command(
    "clip_info",
    "List the animation clips: frame range, duration, cyclic flag, animated objects and bones, channels, keys and NLA tracks.",
    {"clip": string("Only this clip.", max_length=63)},
    mutates=False,
    family="animation",
    intents=("which animations does the scene have", "how long is the walk clip"),
    nearest=(("rig_info", "for the bones of a rig"),),
)
def clip_info(ctx, args):
    fps = scene_fps(ctx.scene)
    actions = [find_clip(args["clip"])] if "clip" in args else sorted((action for action in bpy.data.actions if action.users > 0), key=lambda action: action.name)
    clips = []
    for action in actions:
        entry = describe_clip(action, fps)
        entry["key_frames"] = len(key_frames(action))
        clips.append(entry)
    tracks = []
    for obj in sorted(ctx.scene.objects, key=lambda item: item.name):
        for owner in (obj, obj.data.shape_keys if obj.type == "MESH" else None):
            if owner is not None and owner.animation_data is not None:
                for track in owner.animation_data.nla_tracks:
                    tracks.append({"owner": owner.name, "track": track.name, "muted": track.mute, "clips": [strip.action.name for strip in track.strips if strip.action]})
    return {"fps": round(fps, 6), "clips": clips, "tracks": tracks}


def rest_all(scene):
    for obj in scene.objects:
        for owner in (obj, obj.data.shape_keys if obj.type == "MESH" else None):
            if owner is not None and owner.animation_data is not None:
                owner.animation_data.action = None
        if obj.type == "ARMATURE":
            for pose_bone in obj.pose.bones:
                pose_bone.matrix_basis = Matrix.Identity(4)


@command(
    "clip_pose",
    "Show one frame of a clip in the scene, for previews and checks, or put every rig back in its rest pose; exported clips stay as they are.",
    {
        "clip": string("Clip to play.", max_length=63),
        "frame": number("Frame to show. Default: the clip's first frame.", -MAX_FRAME, MAX_FRAME),
        "rest": boolean("Stop every clip and return every rig to its rest pose.", False),
    },
    family="animation",
    intents=("pose the rig at frame 12 of the walk to preview it", "back to the rest pose"),
    nearest=(("render_preview", "to look at the posed frame"),),
)
def clip_pose(ctx, args):
    if args["rest"] == ("clip" in args):
        raise bad_args("give clip (with an optional frame) or rest true")
    rest_all(ctx.scene)
    if args["rest"]:
        ctx.scene.frame_set(ctx.scene.frame_start)
        return {"rest": True, "frame": ctx.scene.frame_current}
    action = find_clip(args["clip"])
    targets = owners(action)
    if not targets:
        raise bad_args(f"clip {action.name} animates nothing")
    for owner, _ in targets:
        assign(owner, action)
    frame = args.get("frame", action.frame_range[0])
    whole = math.floor(frame)
    ctx.scene.frame_set(int(whole), subframe=frame - whole)
    return {"clip": action.name, "frame": frame, "owners": sorted(owner.name for owner, _ in targets)}
