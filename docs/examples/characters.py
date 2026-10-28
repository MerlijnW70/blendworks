import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))
sys.path.insert(0, HERE)

import character_models
from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "characters"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "512"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "16"))
SHOTS = os.environ.get("BLENDWORKS_CHARACTER_SHOTS", "1") != "0"
ASSETS = os.environ.get("BLENDWORKS_CHARACTERS", "hero,fox,chest").split(",")
HANDLER = None
LOG = []
SUMMARY_KEYS = ("name", "template", "count", "unweighted", "max_influences", "preset", "frame_start", "frame_end", "duration", "stride", "speed", "cadence", "hip_drop", "frames", "bytes", "armatures", "objects")

SPECS = {
    "hero": {
        "name": "stylised hero",
        "format": "glb",
        "size": {"x": [0.5, 1.4], "y": [0.2, 1.4], "z": [1.6, 1.85]},
        "rig": {"required": True, "maxBones": 64, "requiredBones": ["hips", "head", "leftHand", "rightFoot"], "boneMap": {"hips": ["Hips", "mixamorig:Hips"], "head": "Head", "leftHand": ["LeftHand", "hand.L"], "rightFoot": ["RightFoot", "foot.R"]}},
        "skin": {"maxInfluences": 4, "maxUnweighted": 0, "normalized": True, "restPose": True},
        "animation": {"requiredClips": ["walk", "idle"], "loop": {"clips": ["walk", "idle"], "tolerance": 0.001}, "maxDuration": 4, "maxRootMotion": 0.05, "boundsWithin": True},
        "gltf": {"validator": {"maxErrors": 0, "maxWarnings": 0}},
        "views": ["front", "right", "three-quarter"],
    },
    "fox": {
        "name": "fox",
        "format": "glb",
        "size": {"x": [0.15, 0.6], "y": [0.8, 1.6], "z": [0.7, 1.0]},
        "rig": {"required": True, "maxBones": 64, "requiredBones": ["hips", "head", "tail"], "boneMap": {"hips": "Hips", "head": "Head", "tail": ["Tail", "tail*"]}},
        "skin": {"maxInfluences": 4, "maxUnweighted": 0, "normalized": True, "restPose": True},
        "animation": {"requiredClips": ["trot", "idle"], "loop": {"clips": ["trot", "idle"], "tolerance": 0.001}, "maxDuration": 4, "maxRootMotion": 0.05, "boundsWithin": True},
        "gltf": {"validator": {"maxErrors": 0, "maxWarnings": 0}},
        "views": ["right", "front", "three-quarter"],
    },
    "chest": {
        "name": "treasure chest",
        "format": "glb",
        "size": {"x": [0.75, 0.9], "y": [0.45, 1.0], "z": [0.45, 1.1]},
        "rig": {"required": True, "maxBones": 4, "requiredBones": ["lid"], "boneMap": {"lid": "Lid"}},
        "skin": {"maxInfluences": 1, "maxUnweighted": 0, "normalized": True, "restPose": True},
        "animation": {"requiredClips": ["open"], "loop": True, "maxDuration": 3, "maxRootMotion": 0.001, "boundsWithin": True},
        "gltf": {"validator": {"maxErrors": 0, "maxWarnings": 0}},
        "views": ["front", "right", "three-quarter"],
    },
}
FRAMES = {
    "hero": [("walk", (1, 4, 7, 10, 13, 16, 19, 22)), ("idle", (1, 37))],
    "fox": [("trot", (1, 4, 7, 10, 13, 16)), ("idle", (1, 37))],
    "chest": [("open", (1, 12, 24, 36))],
}
SHOT_DIRECTIONS = {"side": [1.0, 0.0, 0.0], "front": [0.0, -1.0, 0.0], "three-quarter": [1.0, -1.0, 0.6]}


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    entry = {"cmd": name, "seconds": round(time.perf_counter() - started, 3)}
    if name in ("rig_template", "skin_bind", "animation_preset", "export"):
        entry.update({key: result[key] for key in SUMMARY_KEYS if key in result})
    if name == "skin_bind":
        entry["meshes"] = [{key: mesh[key] for key in ("name", "vertices", "parts", "unweighted_after_bind", "filled", "unweighted", "rigid_vertices")} for mesh in result["meshes"]]
    LOG.append(entry)
    return result


def shots(asset, focus, width):
    if not SHOTS:
        return
    for clip, frames in FRAMES[asset]:
        for frame in frames:
            cmd("clip_pose", clip=clip, frame=frame)
            views = ("side", "front") if clip != "idle" else ("three-quarter",)
            for view in views:
                result = cmd("render_preview", focus={"point": focus, "width": width, "direction": SHOT_DIRECTIONS[view]}, shading="shaded", resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
                with open(os.path.join(OUT, f"{asset}-{clip}-{frame:03d}-{view}.png"), "wb") as handle:
                    handle.write(base64.b64decode(result["images"][0]["data"]))
    cmd("clip_pose", rest=True)


def write_spec(asset):
    with open(os.path.join(OUT, f"{asset}.spec.json"), "w", encoding="utf-8") as handle:
        json.dump(SPECS[asset], handle, indent=2)


def hero():
    meshes, _ = character_models.hero(cmd)
    cmd("animation_preset", armature="HeroRig", preset="walk")
    cmd("animation_preset", armature="HeroRig", preset="idle")
    cmd("export", path="hero.glb", names=meshes)
    cmd("save_blend", path="hero.blend")
    shots("hero", [0.0, -0.1, 0.9], 2.1)


def fox():
    meshes, _ = character_models.fox(cmd)
    cmd("animation_preset", armature="FoxRig", preset="trot")
    cmd("animation_preset", armature="FoxRig", preset="idle")
    cmd("export", path="fox.glb", names=meshes)
    cmd("save_blend", path="fox.blend")
    shots("fox", [0.0, 0.0, 0.42], 1.5)


def chest():
    character_models.chest(cmd)
    cmd("animation_preset", armature="ChestRig", preset="open", angle=105.0, frames=48)
    cmd("export", path="chest.glb", names=["Chest"])
    cmd("save_blend", path="chest.blend")
    shots("chest", [0.0, 0.1, 0.45], 1.6)


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    for asset, build in (("hero", hero), ("fox", fox), ("chest", chest)):
        if asset not in ASSETS:
            continue
        cmd("new_scene")
        build()
        write_spec(asset)
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


if __name__ == "__main__":
    main()
