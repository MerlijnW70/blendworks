FIXTURE_DEPS = ()
import os
import sys

import bmesh
import bpy

BONES = (
    ("hips", (0.0, 0.0, 0.9), (0.0, 0.0, 1.0), None),
    ("spine", (0.0, 0.0, 1.0), (0.0, 0.0, 1.4), "hips"),
    ("head", (0.0, 0.0, 1.4), (0.0, 0.0, 1.7), "spine"),
    ("arm.L", (0.2, 0.0, 1.35), (0.2, 0.0, 0.95), "spine"),
    ("arm.R", (-0.2, 0.0, 1.35), (-0.2, 0.0, 0.95), "spine"),
    ("thigh.L", (0.1, 0.0, 0.9), (0.1, 0.0, 0.45), "hips"),
    ("shin.L", (0.1, 0.0, 0.45), (0.1, 0.0, 0.0), "thigh.L"),
    ("thigh.R", (-0.1, 0.0, 0.9), (-0.1, 0.0, 0.45), "hips"),
    ("shin.R", (-0.1, 0.0, 0.45), (-0.1, 0.0, 0.0), "thigh.R"),
)

STRIDE = 0.4
SWING = 0.3
WALK_KEYS = ((1, 0.0), (7, 1.0), (19, -1.0), (25, 0.0))


def arguments():
    rest = sys.argv[sys.argv.index("--") + 1 :]
    return rest[0]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 24
    bpy.context.scene.render.fps_base = 1.0


def box(graph, low, high, levels=(0.0, 1.0)):
    rings = []
    for fraction in levels:
        z = low[2] + (high[2] - low[2]) * fraction
        rings.append([graph.verts.new((x, y, z)) for x, y in ((low[0], low[1]), (high[0], low[1]), (high[0], high[1]), (low[0], high[1]))])
    graph.faces.new(list(reversed(rings[0])))
    graph.faces.new(rings[-1])
    for lower, upper in zip(rings, rings[1:]):
        for side in range(4):
            graph.faces.new((lower[side], lower[(side + 1) % 4], upper[(side + 1) % 4], upper[side]))
    return rings


def figure_mesh():
    graph = bmesh.new()
    parts = {
        "torso": box(graph, (-0.15, -0.1, 0.9), (0.15, 0.1, 1.4)),
        "head": box(graph, (-0.1, -0.1, 1.45), (0.1, 0.1, 1.7)),
        "arm.L": box(graph, (0.17, -0.03, 0.95), (0.23, 0.03, 1.35)),
        "arm.R": box(graph, (-0.23, -0.03, 0.95), (-0.17, 0.03, 1.35)),
        "leg.L": box(graph, (0.05, -0.05, 0.0), (0.15, 0.05, 0.9), (0.0, 0.5, 1.0)),
        "leg.R": box(graph, (-0.15, -0.05, 0.0), (-0.05, 0.05, 0.9), (0.0, 0.5, 1.0)),
    }
    mesh = bpy.data.meshes.new("Body")
    graph.verts.index_update()
    indices = {name: [[vertex.index for vertex in ring] for ring in rings] for name, rings in parts.items()}
    graph.to_mesh(mesh)
    graph.free()
    return mesh, indices


def rigid_weights(indices):
    weights = {}
    torso = indices["torso"]
    weights.update({vertex: {"hips": 1.0} for vertex in torso[0]})
    weights.update({vertex: {"spine": 1.0} for vertex in torso[1]})
    for name in ("head", "arm.L", "arm.R"):
        weights.update({vertex: {name: 1.0} for ring in indices[name] for vertex in ring})
    for side in ("L", "R"):
        bottom, knee, top = indices[f"leg.{side}"]
        weights.update({vertex: {f"shin.{side}": 1.0} for vertex in bottom})
        weights.update({vertex: {f"thigh.{side}": 0.5, f"shin.{side}": 0.5} for vertex in knee})
        weights.update({vertex: {f"thigh.{side}": 1.0} for vertex in top})
    return weights


HANDS = (("hand.L", (0.2, 0.0, 0.95), (0.2, 0.0, 0.85), "arm.L"), ("hand.R", (-0.2, 0.0, 0.95), (-0.2, 0.0, 0.85), "arm.R"))


def armature(names=None, extra=()):
    data = bpy.data.armatures.new("Figure")
    rig = bpy.data.objects.new("Figure", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    created = {}
    for name, head, tail, parent in BONES + tuple(extra):
        bone = data.edit_bones.new((names or {}).get(name, name))
        bone.head = head
        bone.tail = tail
        if parent is not None:
            bone.parent = created[parent]
        created[name] = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    for bone in rig.pose.bones:
        bone.rotation_mode = "XYZ"
    return rig


def skinned_body(rig, mesh, weights):
    body = bpy.data.objects.new("Body", mesh)
    bpy.context.scene.collection.objects.link(body)
    for vertex, influences in weights.items():
        for bone, weight in influences.items():
            group = body.vertex_groups.get(bone) or body.vertex_groups.new(name=bone)
            group.add([vertex], weight, "REPLACE")
    body.parent = rig
    body.modifiers.new("Armature", "ARMATURE").object = rig
    return body


def key(rig, bone, frame, channel, value):
    pose = rig.pose.bones[bone]
    if channel == "rotation":
        pose.rotation_euler = (value, 0.0, 0.0)
        pose.keyframe_insert("rotation_euler", index=0, frame=frame)
    else:
        pose.location = (0.0, 0.0, value)
        pose.keyframe_insert("location", index=2, frame=frame)


def walk(rig, name="walk", cycles=1, last=0.0, travel=0.0, bones=None):
    rig.animation_data_create()
    action = bpy.data.actions.new(name)
    rig.animation_data.action = action
    names = bones or {}
    frames = []
    for cycle in range(cycles):
        for frame, phase in WALK_KEYS:
            if cycle > 0 and frame == 1:
                continue
            frames.append((frame + 24 * cycle, phase))
    for index, (frame, phase) in enumerate(frames):
        final = index == len(frames) - 1
        legs = last if final else STRIDE * phase
        key(rig, names.get("thigh.L", "thigh.L"), frame, "rotation", legs)
        key(rig, names.get("thigh.R", "thigh.R"), frame, "rotation", -legs)
        key(rig, names.get("arm.L", "arm.L"), frame, "rotation", -SWING * phase)
        key(rig, names.get("arm.R", "arm.R"), frame, "rotation", SWING * phase)
        if travel:
            key(rig, "hips", frame, "location", travel * (frame - 1) / (frames[-1][0] - 1))
    for bag in action.layers[0].strips[0].channelbags:
        for curve in bag.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    bpy.context.scene.frame_set(1)
    return action


def export_glb(path, **options):
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_animation_mode="ACTIONS", export_force_sampling=True, **options)


def save_blend(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)


def figure(weights_change=None, names=None, extra=(), **clip):
    reset()
    rig = armature(names, extra)
    mesh, indices = figure_mesh()
    weights = rigid_weights(indices)
    if weights_change is not None:
        weights_change(weights, indices)
    if names:
        weights = {vertex: {names.get(bone, bone): value for bone, value in influences.items()} for vertex, influences in weights.items()}
    skinned_body(rig, mesh, weights)
    if clip.get("animated", True):
        walk(rig, bones=names, **{key: value for key, value in clip.items() if key != "animated"})
    return rig


def five_influences(weights, indices):
    for vertex in indices["leg.L"][1]:
        weights[vertex] = {"thigh.L": 0.2, "shin.L": 0.2, "hips": 0.2, "thigh.R": 0.2, "shin.R": 0.2}


def unweighted_head(weights, indices):
    for ring in indices["head"]:
        for vertex in ring:
            weights.pop(vertex)


def unnormalised_shoulders(weights, indices):
    for vertex in indices["torso"][1]:
        weights[vertex] = {"spine": 0.6}


def main():
    folder = arguments()
    os.makedirs(folder, exist_ok=True)
    figure()
    export_glb(os.path.join(folder, "figure.glb"))
    save_blend(os.path.join(folder, "figure.blend"))
    figure(five_influences)
    export_glb(os.path.join(folder, "figure-five.glb"), export_all_influences=True)
    figure(unweighted_head)
    save_blend(os.path.join(folder, "figure-unweighted.blend"))
    figure(unnormalised_shoulders)
    save_blend(os.path.join(folder, "figure-unnormalised.blend"))
    figure(last=0.2)
    export_glb(os.path.join(folder, "figure-nonloop.glb"))
    figure(cycles=2, travel=1.0)
    export_glb(os.path.join(folder, "figure-drift.glb"))
    figure(names={"head": "Bone", "spine": "Spine"}, extra=HANDS, name="stroll")
    export_glb(os.path.join(folder, "figure-renamed.glb"))
    figure(animated=False)
    bpy.data.objects["Figure"].pose.bones["head"].rotation_euler = (0.5, 0.0, 0.0)
    bpy.context.view_layer.update()
    export_glb(os.path.join(folder, "figure-posed.glb"), export_rest_position_armature=False)
    reset()
    mesh, _ = figure_mesh()
    body = bpy.data.objects.new("Body", mesh)
    bpy.context.scene.collection.objects.link(body)
    export_glb(os.path.join(folder, "figure-unrigged.glb"))


main()
