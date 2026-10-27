from array import array
from collections import Counter
from math import ceil, floor, inf

import bpy
import numpy as np

from judge_common import rounded

GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
ANIMATED_DATA = ("objects", "shape_keys", "meshes", "armatures", "materials", "lights", "cameras", "curves", "node_groups", "worlds")
MAX_CLIP_SAMPLES = 240
SAMPLE_BUDGET = 40_000_000
MAX_NAMES = 256
NAME_LENGTH = 120
TIME_DIGITS = 4


def scene_fps(scene):
    return scene.render.fps / scene.render.fps_base


def animated_blocks():
    for collection in ANIMATED_DATA:
        for block in getattr(bpy.data, collection):
            if block.animation_data is not None:
                yield block


def silence_animation():
    for block in animated_blocks():
        block.animation_data.action = None
        block.animation_data.use_nla = False


class HeldAnimation:
    def __init__(self):
        self.blocks = [(block, block.animation_data.action, block.animation_data.action_slot, block.animation_data.use_nla) for block in animated_blocks()]
        self.with_data = {block.as_pointer() for block, _, _, _ in self.blocks}

    def restore(self):
        for block in list(animated_blocks()):
            if block.as_pointer() not in self.with_data:
                block.animation_data_clear()
        for block, action, slot, use_nla in self.blocks:
            data = block.animation_data
            data.action = action
            if action is not None and slot is not None and data.action_slot != slot:
                data.action_slot = slot
            data.use_nla = use_nla


OBJECT_CHANNELS = ("location", "rotation_quaternion", "rotation_euler", "rotation_axis_angle", "scale")


class HeldPose:
    def __init__(self, scene):
        self.scene = scene
        self.frame = (scene.frame_current, scene.frame_subframe)
        self.objects = [(obj, obj.matrix_basis.copy()) for obj in scene.objects]
        self.channels = [(obj, obj.rotation_mode, [tuple(getattr(obj, name)) for name in OBJECT_CHANNELS]) for obj in scene.objects]
        self.bones = []
        for obj in scene.objects:
            if obj.type == "ARMATURE" and obj.pose is not None:
                for bone in obj.pose.bones:
                    channels = (bone.location, bone.rotation_quaternion, bone.rotation_euler, bone.rotation_axis_angle, bone.scale)
                    self.bones.append((bone, [tuple(channel) for channel in channels]))
        self.keys = [(block, block.value) for key in bpy.data.shape_keys for block in key.key_blocks]

    def restore(self):
        for obj, matrix in self.objects:
            obj.matrix_basis = matrix
        for bone, (location, quaternion, euler, axis_angle, scale) in self.bones:
            bone.location = location
            bone.rotation_quaternion = quaternion
            bone.rotation_euler = euler
            bone.rotation_axis_angle = axis_angle
            bone.scale = scale
        for block, value in self.keys:
            block.value = value

    def restore_exactly(self):
        self.restore()
        for obj, mode, values in self.channels:
            obj.rotation_mode = mode
            for name, value in zip(OBJECT_CHANNELS, values):
                setattr(obj, name, value)
        frame, subframe = self.frame
        self.scene.frame_set(frame, subframe=subframe)


def slot_targets(action):
    targets = []
    for slot in action.slots:
        users = list(slot.users())
        if not users and slot.target_id_type == "OBJECT":
            found = bpy.data.objects.get(slot.identifier[2:])
            users = [found] if found is not None else []
        targets.extend((user, slot) for user in users)
    return targets


def clip_curves(action, identifiers):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                if bag.slot is not None and bag.slot.identifier in identifiers:
                    yield from bag.fcurves


def key_times(curves):
    times = set()
    points = 0
    channels = 0
    for curve in curves:
        channels += 1
        count = len(curve.keyframe_points)
        points += count
        values = array("f", [0.0]) * (count * 2)
        curve.keyframe_points.foreach_get("co", values)
        times.update(round(values[index], TIME_DIGITS) for index in range(0, len(values), 2))
    return sorted(times), points, channels


def key_rate(times, fps):
    gaps = Counter(round(later - earlier, TIME_DIGITS) for earlier, later in zip(times, times[1:]))
    if not gaps:
        return None
    common = min(gaps, key=lambda gap: (-gaps[gap], gap))
    return round(fps / common, 3)


def sample_frames(start, end, times, limit):
    candidates = {round(start, TIME_DIGITS), round(end, TIME_DIGITS)}
    candidates.update(float(frame) for frame in range(ceil(start), floor(end) + 1))
    candidates.update(time for time in times if start <= time <= end)
    ordered = sorted(candidates)
    if len(ordered) <= limit:
        return ordered, len(ordered)
    picks = sorted({round(index * (len(ordered) - 1) / (limit - 1)) for index in range(limit)})
    return [ordered[index] for index in picks], len(ordered)


def instance_key(instance):
    obj = instance.object
    if not instance.is_instance:
        return (obj.original.name,)
    owner = instance.parent.original.name if instance.parent is not None else ""
    return (obj.original.name, owner, tuple(instance.persistent_id))


def frame_geometry(depsgraph):
    shapes = {}
    for instance in depsgraph.object_instances:
        obj = instance.object
        if obj.type not in GEOMETRY_TYPES:
            continue
        matrix = np.array(instance.matrix_world, dtype=np.float64)
        key = instance_key(instance)
        mesh = obj.to_mesh()
        try:
            if mesh is None or len(mesh.polygons) == 0:
                continue
            coordinates = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", coordinates)
            loops = np.empty(len(mesh.loops), dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", loops)
            points = coordinates.reshape(-1, 3)[np.unique(loops)].astype(np.float64)
            shapes[key] = points @ matrix[:3, :3].T + matrix[:3, 3]
        finally:
            obj.to_mesh_clear()
    return shapes


def root_positions(scene, depsgraph):
    roots = {}
    for obj in scene.objects:
        evaluated = obj.evaluated_get(depsgraph)
        if obj.type == "ARMATURE" and evaluated.pose is not None:
            for bone in evaluated.pose.bones:
                if bone.parent is None:
                    roots[("bone", obj.name, bone.name)] = np.array(evaluated.matrix_world @ bone.head, dtype=np.float64)
        elif obj.parent is None:
            roots[("object", obj.name)] = np.array(evaluated.matrix_world.translation, dtype=np.float64)
    return roots


def loop_error(first, last):
    if first.keys() != last.keys() or any(first[key].shape != last[key].shape for key in first):
        return None
    return max((float(np.linalg.norm(last[key] - first[key], axis=1).max(initial=0.0)) for key in first), default=0.0)


class Extent:
    def __init__(self):
        self.low = np.full(3, inf)
        self.high = np.full(3, -inf)

    def add(self, points):
        if len(points) > 0:
            self.low = np.minimum(self.low, points.min(axis=0))
            self.high = np.maximum(self.high, points.max(axis=0))

    def include(self, other):
        self.low = np.minimum(self.low, other.low)
        self.high = np.maximum(self.high, other.high)

    def result(self):
        if not np.isfinite(self.low).all():
            return None, None
        return {"min": rounded(self.low.tolist()), "max": rounded(self.high.tolist())}, rounded((self.high - self.low).tolist())


def play(scene, action, targets, limit):
    for block, slot in targets:
        data = block.animation_data or block.animation_data_create()
        data.use_nla = False
        data.action = action
        if data.action_slot != slot:
            data.action_slot = slot
    start, end = (float(value) for value in action.frame_range)
    times, points, channels = key_times(clip_curves(action, {slot.identifier for _, slot in targets}))
    frames, candidates = sample_frames(start, end, times, limit)
    extent = Extent()
    first = first_roots = last = None
    motion = np.zeros(3)
    for index, frame in enumerate(frames):
        whole = floor(frame)
        scene.frame_set(int(whole), subframe=frame - whole)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        shapes = frame_geometry(depsgraph)
        for shape in shapes.values():
            extent.add(shape)
        roots = root_positions(scene, depsgraph)
        if index == 0:
            first, first_roots = shapes, roots
        for key, position in roots.items():
            if key in first_roots:
                moved = position - first_roots[key]
                motion = np.maximum(motion, [np.linalg.norm(moved), np.hypot(moved[0], moved[1]), abs(moved[2])])
        last = shapes
    for block, _ in targets:
        block.animation_data.action = None
    error = loop_error(first, last)
    return extent, {
        "start": start,
        "end": end,
        "times": times,
        "keyframes": points,
        "channels": channels,
        "samples": len(frames),
        "candidates": candidates,
        "loopError": None if error is None else round(error, 6),
        "rootMotion": {"max": round(float(motion[0]), 6), "horizontal": round(float(motion[1]), 6), "vertical": round(float(motion[2]), 6)},
    }


def clip_entry(action, played, extent, fps, file_format):
    bounds, size = extent.result()
    times = played.pop("times")
    rate = round(fps, 3) if file_format == "blend" else key_rate(times, fps)
    return {
        "name": action.name[:NAME_LENGTH],
        "duration": round((played["end"] - played["start"]) / fps, 6),
        "frameRate": rate,
        "keyTimes": len(times),
        **played,
        "bounds": bounds,
        "size": size,
    }


def measure_motion(scene, file_format, static_bounds, triangles):
    fps = scene_fps(scene)
    held = HeldPose(scene)
    animation = HeldAnimation()
    silence_animation()
    actions = [(action, slot_targets(action)) for action in sorted(bpy.data.actions, key=lambda action: action.name)]
    playable = [(action, targets) for action, targets in actions if targets]
    ignored = sorted(action.name[:NAME_LENGTH] for action, targets in actions if not targets)
    limit = max(2, min(MAX_CLIP_SAMPLES, SAMPLE_BUDGET // max(1, triangles * max(1, len(playable)))))
    overall = Extent()
    overall.add(np.array([static_bounds["min"], static_bounds["max"]], dtype=np.float64))
    clips = []
    for action, targets in playable:
        held.restore()
        extent, played = play(scene, action, targets, limit)
        overall.include(extent)
        clips.append(clip_entry(action, played, extent, fps, file_format))
    animation.restore()
    held.restore_exactly()
    bounds, size = overall.result()
    return {
        "clips": len(clips),
        "names": sorted(clip["name"] for clip in clips)[:MAX_NAMES],
        "ignored": ignored[:MAX_NAMES],
        "fps": round(fps, 6),
        "samplesPerClip": limit,
        "bounds": bounds,
        "size": size,
        "items": clips[:MAX_NAMES],
    }
