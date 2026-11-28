"""Animation clip helpers: names, lookup, channels and F-curve access."""

import contextlib
import re

import bpy
from bpy_extras import anim_utils

from . import limits
from .errors import bad_args, not_found
from .util import rounded

INTERPOLATIONS = ("constant", "linear", "bezier")
CLIP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,62}$")
MAX_CLIPS = 256
MAX_FRAME = limits.MAX_FRAME
CYCLES = "CYCLES"


def check_clip_name(name):
    if not CLIP_NAME.match(name):
        raise bad_args(f"clip name {name!r} must be 1 to 63 letters, digits, spaces, dots, dashes or underscores, starting with a letter or digit")


def find_clip(name):
    action = bpy.data.actions.get(name)
    if action is None:
        raise not_found(f"no clip named {name}; clip_keys or animation_preset makes one")
    return action


def clip(name, replace=False):
    check_clip_name(name)
    action = bpy.data.actions.get(name)
    if action is not None and action.users == 0 and not action.use_fake_user:
        bpy.data.actions.remove(action)
        action = None
    if action is not None and replace:
        remove_clip(action)
        action = None
    if action is None:
        if len(bpy.data.actions) >= MAX_CLIPS:
            raise bad_args(f"the scene already has {MAX_CLIPS} clips")
        action = bpy.data.actions.new(name)
    return action


def id_type(owner):
    return "KEY" if isinstance(owner, bpy.types.Key) else "OBJECT"


def slot_for(action, owner):
    for slot in action.slots:
        if slot.target_id_type == id_type(owner) and (owner in slot.users() or slot.name_display == owner.name):
            return slot
    return action.slots.new(id_type=id_type(owner), name=owner.name)


def channels(action, owner):
    slot = slot_for(action, owner)
    return anim_utils.action_ensure_channelbag_for_slot(action, slot), slot


def curve(bag, data_path, index, group):
    found = bag.fcurves.find(data_path, index=index)
    if found is None:
        found = bag.fcurves.new(data_path, index=index)
        if group:
            found.group = bag.groups.get(group) or bag.groups.new(group)
    return found


def key_at(fcurve, frame, value):
    for point in fcurve.keyframe_points:
        if abs(point.co.x - frame) < 1e-6:
            point.co.y = value
            return point
    fcurve.keyframe_points.add(1)
    point = fcurve.keyframe_points[-1]
    point.co = (frame, value)
    point.handle_left_type = "AUTO_CLAMPED"
    point.handle_right_type = "AUTO_CLAMPED"
    return point


def write_keys(fcurve, keys, interpolation):
    for frame, value in keys:
        key_at(fcurve, frame, value).interpolation = interpolation.upper()
    fcurve.update()


def write_samples(fcurve, frames, values):
    fcurve.keyframe_points.clear()
    fcurve.keyframe_points.add(len(frames))
    flat = []
    for frame, value in zip(frames, values):
        flat.extend((float(frame), float(value)))
    fcurve.keyframe_points.foreach_set("co", flat)
    for point in fcurve.keyframe_points:
        point.interpolation = "LINEAR"
    fcurve.update()


def all_curves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                yield bag.slot, bag.fcurves


def key_frames(action):
    frames = set()
    for _, curves in all_curves(action):
        for fcurve in curves:
            frames.update(round(point.co.x, 4) for point in fcurve.keyframe_points)
    return sorted(frames)


def set_range(action, start, end):
    if end <= start:
        raise bad_args("a clip's last frame must come after its first")
    action.use_frame_range = True
    action.frame_start = start
    action.frame_end = end


def set_cyclic(action, cyclic):
    action.use_cyclic = bool(cyclic) and action.use_frame_range
    for _, curves in all_curves(action):
        for fcurve in curves:
            existing = [modifier for modifier in fcurve.modifiers if modifier.type == CYCLES]
            if cyclic and not existing:
                fcurve.modifiers.new(CYCLES)
            if not cyclic:
                for modifier in existing:
                    fcurve.modifiers.remove(modifier)


def owners(action):
    found = []
    for slot in action.slots:
        for user in slot.users():
            found.append((user, slot))
    return found


def track_owner(owner, action, slot):
    data = owner.animation_data or owner.animation_data_create()
    for track in list(data.nla_tracks):
        if track.name == action.name:
            data.nla_tracks.remove(track)
    data.action = None
    track = data.nla_tracks.new()
    track.name = action.name
    start, end = action.frame_range
    strip = track.strips.new(action.name, int(round(start)), action)
    if strip.action_slot != slot:
        strip.action_slot = slot
    strip.action_frame_start = start
    strip.action_frame_end = end
    track.mute = True
    track.is_solo = False
    data.action = None
    return track


def refresh_tracks(action, extra=()):
    found = owners(action)
    for owner in extra:
        if all(owner != known for known, _ in found):
            found.append((owner, slot_for(action, owner)))
    for owner, slot in found:
        track_owner(owner, action, slot)


def assign(owner, action):
    data = owner.animation_data or owner.animation_data_create()
    data.action = action
    slot = slot_for(action, owner)
    if data.action_slot != slot:
        data.action_slot = slot
    return slot


def release(owner):
    if owner.animation_data is not None:
        owner.animation_data.action = None


def remove_clip(action):
    for owner, _ in owners(action):
        data = owner.animation_data
        if data is None:
            continue
        for track in list(data.nla_tracks):
            if track.name == action.name or any(strip.action == action for strip in track.strips):
                data.nla_tracks.remove(track)
        if data.action == action:
            data.action = None
    bpy.data.actions.remove(action)


def describe_clip(action, fps):
    start, end = (float(value) for value in action.frame_range)
    curves = [fcurve for _, group in all_curves(action) for fcurve in group]
    return {
        "name": action.name,
        "frame_start": rounded(start, 4),
        "frame_end": rounded(end, 4),
        "duration": rounded((end - start) / fps, 6),
        "cyclic": bool(action.use_cyclic),
        "owners": sorted(owner.name for owner, _ in owners(action)),
        "channels": len(curves),
        "keyframes": sum(len(fcurve.keyframe_points) for fcurve in curves),
        "bones": sorted({fcurve.data_path.split('"')[1] for fcurve in curves if fcurve.data_path.startswith("pose.bones[")}),
    }


def scene_fps(scene):
    return scene.render.fps / scene.render.fps_base


@contextlib.contextmanager
def unmuted_tracks(objects, active):
    switched = []
    if active:
        for obj in objects:
            for owner in (obj, obj.data.shape_keys if obj.type == "MESH" else None):
                if owner is not None and owner.animation_data is not None:
                    for track in owner.animation_data.nla_tracks:
                        if track.mute:
                            track.mute = False
                            switched.append((owner, track))
        rebuild(owner for owner, _ in switched)
    try:
        yield
    finally:
        for _, track in switched:
            track.mute = True
        rebuild(owner for owner, _ in switched)


def rebuild(owners_changed):
    for owner in {owner.as_pointer(): owner for owner in owners_changed}.values():
        owner.animation_data.action = owner.animation_data.action
    bpy.context.view_layer.update()
