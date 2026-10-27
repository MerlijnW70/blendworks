import hashlib
import json
import os
import sys

arguments = sys.argv[sys.argv.index("--") + 1 :]
judge_dir, asset, out_dir = arguments[0], arguments[1], arguments[2]
sys.path.insert(0, judge_dir)

import bpy

import judge_pass
import judge_render_stages
from judge_stage_scene import stage_scene

STAGES = "measure,reference,views,sheet"
SCENE_SETTINGS = (
    ("render", "engine"),
    ("render", "film_transparent"),
    ("render", "resolution_x"),
    ("render", "use_compositing"),
    ("cycles", "samples"),
    ("cycles", "filter_width"),
    ("cycles", "max_bounces"),
    ("view_settings", "view_transform"),
)


def options(stages):
    chosen = dict(judge_pass.PASS_DEFAULTS)
    chosen.update({"stages": stages, "reference-views": "front:64,left:64", "res": "64", "samples": "2", "views": "front,three-quarter"})
    return chosen


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def silhouettes(folder):
    document = json.loads(read(os.path.join(folder, "silhouettes.json")))
    return {"frame": document["frame"], "views": [[view["view"], view["size"], digest(view["path"])] for view in document["views"]]}


def scene_state(scene):
    settings = [repr(getattr(getattr(scene, group), name)) for group, name in SCENE_SETTINGS]
    layer = scene.view_layers[0]
    return {
        "settings": settings,
        "override": layer.material_override.name if layer.material_override else None,
        "compositing": scene.compositing_node_group.name if scene.compositing_node_group else None,
        "camera": scene.camera.name if scene.camera else None,
        "world": scene.world.name if scene.world else None,
        "objects": sorted(obj.name for obj in scene.objects),
        "data": {kind: len(getattr(bpy.data, kind)) for kind in ("objects", "cameras", "lights", "materials", "worlds", "node_groups", "meshes", "scenes")},
    }


def tampering(stage):
    def tampered(context):
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj.scale = (3.0, 3.0, 3.0)
                obj.location.x += 5.0
        for material in bpy.data.materials:
            material.diffuse_color = (1.0, 0.0, 0.0, 1.0)
        document = context.framing()
        document["measurements"]["triangles"] = -1
        document["measurements"]["size"] = [0.0, 0.0, 0.0]
        return stage(context)

    return tampered


def run(name, stages, tamper=False):
    folder = os.path.join(out_dir, name)
    os.makedirs(folder, exist_ok=True)
    originals = dict(judge_pass.STAGES)
    if tamper:
        judge_pass.STAGES["views"] = tampering(originals["views"])
    try:
        judge_pass.run_pass(asset, folder, options(stages))
    finally:
        judge_pass.STAGES.update(originals)
    return folder


def stage_leaves_no_trace():
    context = judge_pass.Context(asset, os.path.join(out_dir, "scoped"), options("views"))
    os.makedirs(context.out_dir, exist_ok=True)
    judge_pass.load_asset(asset, 2_000_000)
    context.prepare_scene()
    before = scene_state(context.scene)
    with stage_scene(context.scene, "probe") as scene:
        judge_render_stages.configure_silhouettes(scene)
        judge_render_stages.Rig(scene, [-1.0, -1.0, 0.0], [1.0, 1.0, 1.0], [0.0, 0.0, 0.0])
        inside = scene_state(scene)
    after = scene_state(context.scene)
    return {"before": before, "after": after, "changedInside": inside != before}


clean = run("clean", STAGES)
tampered = run("tampered", STAGES, tamper=True)
alone = run("alone", "measure")
result = {
    "clean": read(os.path.join(clean, "measurements.json")),
    "tampered": read(os.path.join(tampered, "measurements.json")),
    "alone": read(os.path.join(alone, "measurements.json")),
    "cleanSilhouettes": silhouettes(clean),
    "tamperedSilhouettes": silhouettes(tampered),
    "views": [digest(os.path.join(folder, "views", "front.png")) for folder in (clean, tampered)],
    "scope": stage_leaves_no_trace(),
}
with open(os.path.join(out_dir, "probe.json"), "w", encoding="utf-8") as handle:
    json.dump(result, handle)
