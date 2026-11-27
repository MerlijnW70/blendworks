"""A landscape at world scale, built only with Blendworks commands.

The camera stands 15 km from the origin on a ridge; mountains in nested rings of terrain tiles reach 108 km in every
direction, and haze fills the whole view, so the far ranges fade into the sky. The scene first goes through
validate as one plan, then runs and renders with render_final.

Run: blender --background --factory-startup --python docs/examples/world_scale.py -- <out dir>
Environment: BLENDWORKS_WORLD_DETAIL scales every tile resolution (1.0 full), BLENDWORKS_SHOT_WIDTH, _HEIGHT,
_SAMPLES and _SECONDS set the render, BLENDWORKS_DEVICE the render device.
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

import bpy
from mathutils import Vector

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "world-scale"))
DETAIL = float(os.environ.get("BLENDWORKS_WORLD_DETAIL", "1.0"))
WIDTH = int(os.environ.get("BLENDWORKS_SHOT_WIDTH", "1600"))
HEIGHT = int(os.environ.get("BLENDWORKS_SHOT_HEIGHT", "900"))
SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "128"))
SECONDS = float(os.environ.get("BLENDWORKS_SHOT_SECONDS", "300"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")

STANDING = 15_000.0
HEADING = math.radians(55.0)
EYE_ABOVE_GROUND = 30.0
VISIBILITY = 70_000.0
SEED = 11
LAND = {"mode": "ridged", "base_height": -1200.0, "height": 3600.0, "scale": 14_000.0, "octaves": 9, "hurst": 0.55,
        "warp": 1500.0, "warp_octaves": 3, "seed": SEED, "attributes": ["slope", "height"]}
# Nested rings of tiles: each ring's tiles are larger than the ring inside it and leave out the block the inner ring
# covers, so the land is one surface from the camera to 108 km out. The camera stands in the middle of the finest
# ring, at a heading chosen once from the land: a ridge 15 km from the origin with the view open to the north-east.
# (tile size m, i range, j range, left-out i range, left-out j range, resolution at full detail)
RINGS = ((2_000.0, range(3, 6), range(6, 9), range(0, 0), range(0, 0), 201),
         (6_000.0, range(0, 3), range(0, 3), range(1, 2), range(2, 3), 121),
         (18_000.0, range(-2, 2), range(-2, 2), range(0, 1), range(0, 1), 121),
         (36_000.0, range(-3, 3), range(-3, 3), range(-1, 1), range(-1, 1), 61))
HANDLER = None
LOG = []


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3)})
    print(f"ok {name} {LOG[-1]['seconds']} s", flush=True)
    return reply["result"]


def tiles():
    for size, i_range, j_range, i_out, j_out, resolution in RINGS:
        for i in i_range:
            for j in j_range:
                if i in i_out and j in j_out:
                    continue
                yield f"land_{int(size)}_{i}_{j}", size, (i, j), max(3, int(round(resolution * DETAIL)))


def plan():
    calls = [{"cmd": "new_scene", "args": {}},
             {"cmd": "weather", "args": {"preset": "clear", "time_of_day": "golden_hour", "haze": False}},
             {"cmd": "material_procedural", "args": {"name": "ground", "grass_ground": {"density": 0.7, "dryness": 0.4}}},
             {"cmd": "material_layer", "args": {"material": "ground", "mask": "slope", "angle_min": 30.0, "angle_edge": 12.0,
                                                "softness": 0.8, "seed": 3, "stone": {"color": [0.24, 0.22, 0.2],
                                                                                        "secondary_color": [0.12, 0.11, 0.1],
                                                                                        "cracks": False}}}]
    for name, size, index, resolution in tiles():
        calls.append({"cmd": "heightfield", "args": {"name": name, "size": [size, size], "tile": list(index),
                                                     "resolution": resolution, **LAND}})
        calls.append({"cmd": "assign_material", "args": {"name": name, "material": "ground"}})
        calls.append({"cmd": "shade_smooth", "args": {"name": name}})
    return calls


def ground(x, y):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, *_ = bpy.context.scene.ray_cast(depsgraph, Vector((x, y, 30_000.0)), Vector((0.0, 0.0, -1.0)))
    if not hit:
        raise RuntimeError(f"no land under {x}, {y}")
    return location.z


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    workspace = os.path.join(OUT, "workspace")
    os.makedirs(workspace, exist_ok=True)
    HANDLER = Handler(workspace)
    calls = plan()
    checked = cmd("validate", calls=calls)
    if not checked["valid"]:
        raise RuntimeError(json.dumps(checked["problems"], indent=1))
    for call in calls:
        cmd(call["cmd"], **call["args"])
    heading = HEADING
    x, y = STANDING * math.cos(heading), STANDING * math.sin(heading)
    eye = [x, y, ground(x, y) + EYE_ABOVE_GROUND]
    ahead = 20_000.0
    target_xy = (x + ahead * math.cos(heading), y + ahead * math.sin(heading))
    target = [target_xy[0], target_xy[1], eye[2] - 600.0]
    cmd("add_camera", name="view", location=eye, target=target, lens=35.0)
    cmd("camera_setup", name="view", clip_start=0.5, clip_end=300_000.0, view_transform="AgX", look="base_contrast")
    haze = cmd("atmosphere", visibility=VISIBILITY, height_falloff=2500.0, base_height=0.0)
    shot = cmd("render_final", path="world-scale.png", camera="view", width=WIDTH, height=HEIGHT, samples=SAMPLES,
               time_limit=SECONDS, device=DEVICE, preview=False)
    land = [o for o in bpy.data.objects if o.name.startswith("land_")]
    reach = max(max(abs(c) for corner in o.bound_box for c in (o.matrix_world @ Vector(corner))[:2]) for o in land)
    summary = {
        "camera": {"location": eye, "distance_from_origin": math.hypot(eye[0], eye[1])},
        "land": {"tiles": len(land), "reach": reach},
        "haze": haze,
        "render": shot,
        "validated_calls": len(calls),
        "commands": LOG,
    }
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=1, default=str)
    os.replace(os.path.join(workspace, "world-scale.png"), os.path.join(OUT, "world-scale.png"))


main()
