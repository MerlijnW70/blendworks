import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "grow-trees"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "32"))
DETAIL = float(os.environ.get("BLENDWORKS_TREE_DETAIL", "1.0"))
SPACING = 16.0
SUMMARY_KEYS = ("method", "nodes", "tips", "branchings", "root_nodes", "max_order", "base_radius", "height", "spread", "root_depth", "pipe_error")


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    entry = {"cmd": name, "seconds": round(time.perf_counter() - started, 3)}
    if name == "grow_tree":
        entry.update({"name": result["name"], **{key: result.get(key) for key in SUMMARY_KEYS}, "growth": result["growth"]})
    if name == "export":
        entry["skeletons"] = result.get("skeletons", [])
    LOG.append(entry)
    return result


def count(value):
    return max(1, int(round(value * DETAIL)))


def trees():
    cmd(
        "grow_tree",
        name="oak",
        method="colonization",
        location=[-SPACING, 0.0, 0.0],
        envelope="hemispherical",
        height=10.0,
        trunk_height=2.6,
        crown_radius=5.5,
        points=count(4000),
        influence=1.6,
        kill=0.36,
        step=0.18,
        tropism=[0.0, 0.0, 0.08],
        tip_radius=0.012,
        seed=3,
        roots={"points": count(1800), "depth": 1.4, "radius": 3.2, "influence": 1.0, "kill": 0.3, "step": 0.16, "tropism": [0.0, 0.0, -0.25]},
        limit=0,
    )
    cmd(
        "grow_tree",
        name="conifer",
        method="levels",
        location=[0.0, 0.0, 0.0],
        envelope="conical",
        height=14.0,
        trunk_height=1.6,
        levels=3,
        branches=[count(70), count(16)],
        down_angle=[84.0, 55.0],
        rotate=[137.5, 137.5],
        length_ratio=[0.34, 0.3],
        curve=[0.0, 24.0, 12.0],
        segments=[40, 10, 4],
        taper=0.55,
        ratio_power=0.9,
        tip_radius=0.035,
        seed=5,
        roots={"points": count(900), "depth": 1.0, "radius": 2.2, "shape": "hemispherical", "tip_radius": 0.008},
        limit=0,
    )
    cmd("add_primitive", type="sphere", name="wind_crown", radius=1.0, segments=48, rings=24, location=[SPACING + 2.6, 0.0, 4.6])
    cmd("transform", name="wind_crown", scale=[4.2, 2.6, 1.9], rotation=[0.0, 12.0, 0.0])
    cmd(
        "grow_tree",
        name="windswept",
        method="colonization",
        location=[SPACING, 0.0, 0.0],
        envelope="wind_crown",
        trunk_height=1.4,
        points=count(3200),
        influence=1.4,
        kill=0.3,
        step=0.16,
        tropism=[0.45, 0.0, -0.08],
        tip_radius=0.011,
        seed=11,
        roots={"points": count(900), "depth": 1.0, "radius": 2.4, "tropism": [-0.25, 0.0, -0.35]},
        limit=0,
    )
    cmd("delete", names=["wind_crown"])


def materials():
    cmd("material_procedural", name="bark", bark={"grain": "z"})
    for name in ("oak", "conifer", "windswept"):
        cmd("assign_material", name=name, material="bark")


def shots():
    views = {
        "oak": ([-SPACING, 0.0, 4.4], 14.5, [0.0, -1.0, 0.08], "shaded"),
        "conifer": ([0.0, 0.0, 6.5], 15.5, [0.0, -1.0, 0.08], "shaded"),
        "windswept": ([SPACING + 2.2, 0.0, 3.4], 13.5, [0.0, -1.0, 0.08], "shaded"),
        "oak_top": ([-SPACING, 0.0, 6.0], 13.0, [0.0, -0.001, 1.0], "clay"),
        "conifer_top": ([0.0, 0.0, 7.0], 11.0, [0.0, -0.001, 1.0], "clay"),
        "oak_base": ([-SPACING, 0.0, 0.2], 6.0, [0.6, -1.0, 0.25], "shaded"),
        "row": ([1.5, 0.0, 5.5], 42.0, [0.25, -1.0, 0.12], "shaded"),
    }
    for name, (point, width, direction, shading) in views.items():
        result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading=shading, resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    trees()
    materials()
    cmd("save_blend", path="grow-trees.blend")
    cmd("export", path="grow-trees.glb")
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


main()
