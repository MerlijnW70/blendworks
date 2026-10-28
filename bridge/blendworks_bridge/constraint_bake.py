import contextlib
import math

import bpy
from bpy_extras import anim_utils

BAKED_PREFIX = "blendworks_baked_"


def constrained(obj):
    return obj.type == "ARMATURE" and obj.pose is not None and any(constraint.enabled for bone in obj.pose.bones for constraint in bone.constraints)


def bake_options():
    return anim_utils.BakeOptions(
        only_selected=False,
        do_pose=True,
        do_object=True,
        do_visual_keying=True,
        do_constraint_clear=False,
        do_parents_clear=False,
        do_clean=False,
        do_location=True,
        do_rotation=True,
        do_scale=True,
        do_bbone=False,
        do_custom_props=False,
    )


def bake_strip(obj, strip):
    data = obj.animation_data
    source = strip.action
    data.action = source
    if strip.action_slot is not None and data.action_slot != strip.action_slot:
        data.action_slot = strip.action_slot
    start, end = (float(value) for value in source.frame_range)
    frames = range(math.floor(start), math.ceil(end) + 1)
    baked = anim_utils.bake_action(obj, action=None, frames=frames, bake_options=bake_options())
    baked.name = BAKED_PREFIX + source.name
    baked.use_frame_range = True
    baked.frame_start = start
    baked.frame_end = end
    data.action = None
    return baked


@contextlib.contextmanager
def baked_constraints(objects, active):
    armatures = [obj for obj in objects if active and constrained(obj) and obj.animation_data is not None]
    held = []
    strips = []
    baked = []
    switched = []
    try:
        for obj in armatures:
            data = obj.animation_data
            held.append((obj, data.action, data.action_slot, data.use_nla, data.action_blend_type))
            data.use_nla = False
            for track in data.nla_tracks:
                for strip in track.strips:
                    if strip.action is None:
                        continue
                    strips.append((strip, strip.action, strip.action_slot, strip.action_frame_start, strip.action_frame_end))
                    action = bake_strip(obj, strip)
                    baked.append(action)
                    strip.action = action
                    strip.action_slot = action.slots[0]
                    strip.action_frame_start, strip.action_frame_end = strips[-1][3], strips[-1][4]
        for obj in armatures:
            for bone in obj.pose.bones:
                for constraint in bone.constraints:
                    if constraint.enabled:
                        constraint.enabled = False
                        switched.append(constraint)
        bpy.context.view_layer.update()
        yield [obj.name for obj in armatures]
    finally:
        for constraint in switched:
            constraint.enabled = True
        for strip, action, slot, start, end in strips:
            strip.action = action
            if slot is not None:
                strip.action_slot = slot
            strip.action_frame_start = start
            strip.action_frame_end = end
        for obj, action, slot, use_nla, blend in held:
            data = obj.animation_data
            data.action = action
            if action is not None and slot is not None:
                data.action_slot = slot
            data.use_nla = use_nla
            data.action_blend_type = blend
        for action in baked:
            bpy.data.actions.remove(action)
        bpy.context.view_layer.update()
