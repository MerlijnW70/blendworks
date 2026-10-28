import base64
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "shells"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

def arched_plate(count=40, rise=0.3, thickness=0.05):
    top = [[i / count, rise * math.sin(math.pi * i / count) ** 0.8] for i in range(count + 1)]
    bottom = [[i / count, rise * math.sin(math.pi * i / count) ** 0.8 - thickness] for i in range(count, -1, -1)]
    return top + bottom


SHELLS = {
    "conch": {
        "args": dict(W=1.42, D=0.15, T=0.9, turns=6.5, size=0.11, steps=64, profile="ellipse", aspect=0.85, ribs={"count": 14, "height": 0.035}, lip={"flare": 0.2, "length": 0.3, "thicken": 0.3}, thickness=0.002),
        "x": -0.4,
        "rotation": [0.0, 0.0, 0.0],
        "material": {"name": "conch_shell", "stone": {"color": [0.86, 0.52, 0.3], "secondary_color": [0.95, 0.82, 0.62], "cell_scale": 1.2, "cracks": False, "roughness": 0.35}},
    },
    "ammonite": {
        "args": dict(W=1.9, D=0.5, T=0.0, turns=4.0, size=0.14, steps=96, profile="ellipse", aspect=1.35, ribs={"count": 18, "height": 0.05}, thickness=0.003),
        "x": 0.0,
        "rotation": [90.0, 0.0, 0.0],
        "material": {"name": "ammonite_shell", "marble": {"color": [0.55, 0.42, 0.28], "secondary_color": [0.34, 0.25, 0.17], "vein_color": [0.12, 0.08, 0.05], "roughness": 0.4}},
    },
    "ribbed_fan": {
        "args": dict(W=3.0, D=0.08, T=0.0, turns=0.5, size=0.2, steps=180, profile="points", points=arched_plate(), ribs={"count": 28, "height": 0.03}),
        "x": 0.4,
        "rotation": [0.0, 0.0, 0.0],
        "material": {"name": "ribbed_fan_shell", "stone": {"color": [0.93, 0.52, 0.42], "secondary_color": [0.98, 0.84, 0.72], "cell_scale": 6.0, "cracks": False, "roughness": 0.3}},
    },
}


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3), "name": args.get("name"), "manifold": result.get("manifold"), "volume": result.get("volume"), "wall_min": result.get("wall_min")})
    return result


def lighting():
    cmd("set_world", color=[0.62, 0.68, 0.78], strength=0.9)
    cmd("add_light", type="sun", name="sun", energy=4.5, rotation=[50.0, 0.0, 35.0])


def floor():
    cmd("add_primitive", type="plane", name="floor", size=2.4, location=[0.0, 0.0, 0.0])
    cmd("material_procedural", name="floor", concrete={"color": [0.34, 0.33, 0.31], "variation": 0.25, "pores": 0.2})
    cmd("assign_material", name="floor", material="floor")


def build(name, spec):
    cmd("shell", name=name, rotation=spec["rotation"], **spec["args"])
    cmd("material_procedural", **spec["material"])
    cmd("assign_material", name=name, material=spec["material"]["name"])
    cmd("set_origin", name=name, to="bottom_centre")
    cmd("transform", name=name, location=[spec["x"], 0.0, 0.0])


def shots():
    views = {
        "overview": {"point": [0.0, 0.0, 0.1], "width": 1.25, "direction": [0.0, -1.0, 0.45]},
        "conch": {"object": "conch", "direction": [-1.0, 0.25, 0.3]},
        "ammonite": {"object": "ammonite", "direction": [0.0, -1.0, 0.35]},
        "ribbed_fan": {"object": "ribbed_fan", "direction": [0.4, -1.0, 0.6]},
    }
    for name, focus in views.items():
        result = cmd("render_preview", focus=focus, shading="shaded", resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    lighting()
    floor()
    for name, spec in SHELLS.items():
        build(name, spec)
    cmd("save_blend", path="shells.blend")
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


main()
