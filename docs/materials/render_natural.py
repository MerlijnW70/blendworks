import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.getcwd())
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "700"))
SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
HANDLER = Handler(OUT, allow_python=False, desktop=False)
SWATCHES = {"bark": {"grain": "y"}, "moss": {}, "soil": {}, "sand": {}, "grass_ground": {}}


def cmd(name, /, **args):
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    return reply["result"]


def shoot(name, point, width, direction):
    result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading="shaded", resolution=SIZE, samples=SAMPLES, device=DEVICE)
    with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
        handle.write(base64.b64decode(result["images"][0]["data"]))


def boulder(label, stone):
    cmd("new_scene")
    cmd("add_primitive", type="ico_sphere", name="rock", radius=0.8, subdivisions=6)
    cmd("noise_displace", name="rock", amplitude=0.1, seed=3, mode="billow", scale=1.2, octaves=3, hurst=0.9)
    cmd("shade_smooth", name="rock")
    cmd("material_procedural", name="stone", stone=dict({"color": [0.4, 0.38, 0.35], "cracks": False}, **stone))
    cmd("assign_material", name="rock", material="stone")
    shoot(label, [0.0, 0.0, 0.0], 2.2, [0.4, -1.0, 0.4])


def swatch(name, params):
    cmd("new_scene")
    cmd("add_primitive", type="plane", name="tile", size=1.0)
    cmd("transform", name="tile", rotation=[55.0, 0.0, 0.0])
    cmd("material_procedural", name="m", **{name: params})
    cmd("assign_material", name="tile", material="m")
    shoot(name, [0.0, 0.0, 0.0], 1.1, [0.0, -1.0, 0.0])


def leaf():
    cmd("new_scene")
    cmd("add_primitive", type="plane", name="card", size=1.0)
    cmd("transform", name="card", scale=[0.7, 1.0, 1.0], rotation=[75.0, 0.0, 0.0])
    cmd("material_procedural", name="m", leaf={"cutout": True, "translucency": 0.4})
    cmd("assign_material", name="card", material="m")
    shoot("leaf", [0.0, 0.0, 0.0], 1.1, [0.0, -1.0, 0.15])


def main():
    boulder("stone-before", {"hard_cells": True})
    boulder("stone-after", {})
    for name, params in SWATCHES.items():
        swatch(name, params)
    leaf()


main()
