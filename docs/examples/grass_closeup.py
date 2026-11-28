"""A meadow close-up under a noon sun: the meadow preset on its own fields over a gently rolling patch, a camera at eye
height looking towards the sun (the backs of the blades, lit through them) and one looking away, the far ground in the
grass_ground canopy colour beyond the cover. Every render setting is the default.

Run: blender -b --factory-startup --python docs/examples/grass_closeup.py -- <out dir> [shots]"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "grass-closeup"))
SHOTS = (ARGS[1] if len(ARGS) > 1 else "into_sun,with_sun").split(",")
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
WIDTH = int(os.environ.get("BLENDWORKS_SHOT_WIDTH", "1600"))
HEIGHT = int(os.environ.get("BLENDWORKS_SHOT_HEIGHT", "900"))
SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "256"))
SECONDS = float(os.environ.get("BLENDWORKS_SHOT_SECONDS", "300"))
TIME_OF_DAY = os.environ.get("BLENDWORKS_TIME", "noon")
SIZE = 3000.0
NEAR = 25.0
CAMERAS = {"into_sun": ([0.0, 6.0, 1.4], [0.0, -30.0, 0.0]), "with_sun": ([0.0, -6.0, 1.4], [0.0, 30.0, 0.0])}
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


def build():
    cmd("new_scene")
    cmd("heightfield", name="field", size=[SIZE, SIZE], resolution=301, height=1.5, seed=4, scale=60.0, octaves=4, hurst=0.7)
    cmd("transform", name="field", location=[-SIZE / 2.0, -SIZE / 2.0, 0.0])
    cmd("material_procedural", name="meadow", grass_ground={"density": 0.85, "dryness": 0.2})
    cmd("assign_material", name="field", material="meadow")
    for shot, (location, target) in CAMERAS.items():
        cmd("add_camera", name=shot, location=location, target=target, lens=30.0)
    cmd("weather", preset="fair_cumulus", time_of_day=TIME_OF_DAY, seed=2)
    fields = cmd("meadow_fields", targets=["field"], seed=5)
    cover = cmd("ground_cover", target="field", preset="meadow", cameras=list(CAMERAS), near=NEAR, view_only=True, seed=5)
    return fields, cover


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    fields, cover = build()
    renders = {}
    for shot in SHOTS:
        final = cmd("render_final", path=f"{shot}.png", camera=shot, width=WIDTH, height=HEIGHT, samples=SAMPLES, time_limit=SECONDS, device=DEVICE, preview=False)
        renders[shot] = {key: final[key] for key in ("exposure", "white_balance", "samples", "time_budget")}
    summary = {"fields": {key: fields[key] for key in ("moisture",) if key in fields}, "cover": cover.get("counts", cover.get("populations")),
               "renders": renders, "commands": LOG}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=1, default=str)


if __name__ == "__main__":
    main()
