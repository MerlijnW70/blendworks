import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "engraved-rings"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

RADIUS = 0.15
TOP = 0.003
SIGNS = ("aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces")


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3), "manifold": result.get("manifold"), "solver": result.get("solver"), "quality": result.get("quality")})
    return result


def horizon():
    cmd("sweep", name="horizon", preset="rounded_rectangle", width=0.056, height=2 * TOP, corner_radius=0.0009, segments=2, circle={"centre": [0, 0, 0], "radius": RADIUS, "tolerance": 0.00006}, shading="auto", smooth_angle=40)
    face = {"centre": [0, 0, TOP]}
    cmd("engrave_scale", name="horizon", ring={**face, "radius": 0.168}, start=0, end=360, step=1, depth=0.0004, length=0.0035, width=0.0004, classes=[{"every": 5, "length": 0.005}, {"every": 10, "length": 0.0075, "depth": 0.0007}])
    for index in range(24):
        cmd("engrave", name="horizon", text=str(15 * index), ring={**face, "radius": 0.1605, "angle": 15 * index}, size=0.0048, depth=0.0005)
    for index, sign in enumerate(SIGNS):
        cmd("engrave", name="horizon", text="{" + sign + "}", ring={**face, "radius": 0.137, "angle": 30 * index + 15, "up": "inward"}, size=0.008, depth=0.0005)


def meridian():
    cmd("sweep", name="meridian", preset="rounded_rectangle", width=0.02, height=2 * TOP, corner_radius=0.0009, segments=2, circle={"centre": [0, 0, 0], "axis": [0, 1, 0], "radius": RADIUS + 0.006, "tolerance": 0.00006}, shading="auto", smooth_angle=40)
    face = {"centre": [0, TOP, 0], "axis": [0, 1, 0]}
    cmd("engrave_scale", name="meridian", ring={**face, "radius": RADIUS + 0.011}, start=0, end=90, step=2, mirror="quadrants", depth=0.0004, length=0.0035, width=0.0004, classes=[{"every": 5, "length": 0.006, "depth": 0.0006}])
    for value in range(0, 91, 10):
        for angle in sorted({value, 180 - value, 180 + value, 360 - value}):
            cmd("engrave", name="meridian", text=str(value), ring={**face, "radius": RADIUS + 0.0035, "angle": angle}, size=0.004, depth=0.0004)


def plinth():
    profile = [[0, -0.2], [0.132, -0.2], [0.134, -0.198], [0.134, -0.186], [0.126, -0.18], [0.118, -0.165], [0.1, -0.162], [0, -0.162]]
    cmd("lathe", name="plinth", profile=profile, segments=128)
    cmd("uv_smart_project", name="plinth", island_margin=0.002)


def materials():
    cmd("material_procedural", name="aged_brass", brass={"age": "aged", "color": [0.5, 0.36, 0.13], "scratch_direction": "around_z", "seed": 4})
    cmd("material_procedural", name="marble", marble={"seed": 3})
    cmd("assign_material", name="rings", material="aged_brass")
    cmd("assign_material", name="plinth", material="marble")


def close_ups():
    shots = {
        "ticks-and-numbers": ([0.0, -0.163, TOP], 0.05, [0.0, -0.5, 1.0]),
        "zodiac-recesses": ([0.095, -0.095, TOP], 0.04, [0.4, -0.5, 1.0]),
        "union-joint": ([RADIUS, 0.0, 0.0], 0.06, [1.0, -0.8, 0.6]),
        "meridian-scale": ([-0.1, 0.0, 0.12], 0.07, [-0.3, -1.0, 0.4]),
        "marble-plinth": ([0.0, -0.09, -0.17], 0.16, [0.3, -1.0, 0.5]),
        "whole": ([0.0, 0.0, -0.03], 0.42, [0.6, -1.0, 0.6]),
    }
    for name, (point, width, direction) in shots.items():
        result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, resolution=900, samples=48, device=DEVICE)
        with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    horizon()
    meridian()
    union = cmd("boolean", name="horizon", cutter="meridian", operation="union", solver="exact", manifold=True, cutter_action="delete")
    cmd("rename", name="horizon", new_name="rings")
    plinth()
    materials()
    cmd("save_blend", path="engraved-rings.blend")
    close_ups()
    cuts = [entry for entry in LOG if entry["cmd"] in ("engrave", "engrave_scale")]
    summary = {
        "cuts": len(cuts),
        "all_manifold": all(entry["manifold"] for entry in cuts),
        "slivers_after_each_cut": [entry["quality"]["slivers"] for entry in cuts],
        "union": {"solver": union["solver"], "manifold": union["manifold"], "quality": union.get("quality")},
        "seconds": round(sum(entry["seconds"] for entry in LOG), 1),
    }
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "log": LOG}, handle, indent=1)
    print(json.dumps(summary))


main()
