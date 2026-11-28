import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "tree-shapes"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "32"))
DETAIL = float(os.environ.get("BLENDWORKS_TREE_DETAIL", "1.0"))
SPACING = 18.0
HANDLER = None
LOG = []

TREES = ("willow", "oak", "coastal")
PLACES = {"willow": [-SPACING, 0.0, 0.0], "oak": [0.0, 0.0, 0.0], "coastal": [SPACING, 0.0, 0.0]}
GROW = {
    "willow": {"preset": "weeping_willow", "seed": 7, "roots": {"points": 700, "depth": 1.0, "radius": 2.4}},
    "oak": {"preset": "gnarled_oak", "seed": 3, "points": 4000, "roots": {"points": 1200, "depth": 1.3, "radius": 3.4, "influence": 1.0, "kill": 0.3, "step": 0.16}},
    "coastal": {"preset": "windswept_coastal", "seed": 11, "points": 2800, "roots": {"points": 800, "depth": 1.0, "radius": 2.4, "tropism": [-0.25, 0.0, -0.35]}},
}
BARK = {"bark_material": "bark", "root_material": "roots", "wood_material": "fresh_wood"}
MESH = {
    "willow": {**BARK, "min_radius": 0.004, "twigs": "cards", "flare": {"amount": 0.5, "lobes": 0.6}, "root_flare": {"amount": 1.4}},
    "oak": {**BARK, "flare": {"amount": 0.7, "lobes": 0.8}, "root_flare": {"amount": 1.8}},
    "coastal": {**BARK, "flare": {"amount": 0.6, "lobes": 0.8}, "root_flare": {"amount": 1.8}},
}
LEAVES = {
    "willow": {"seed": 7},
    "oak": {"seed": 3},
    "coastal": {"material": "leaf", "size": 0.07, "clusters": {"leaves": [4, 8], "spacing": 0.09}, "align": {"sun": [0.4, 0.0, 1.0], "factor": 0.8}, "seed": 11},
}
GROW_KEYS = ("name", "method", "preset", "nodes", "tips", "branchings", "max_order", "base_radius", "height", "spread", "pipe_error", "growth")
MESH_KEYS = ("name", "triangles", "manifold", "volume", "shells", "self_intersections", "materials", "leaves", "count")


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    entry = {"cmd": name, "seconds": round(time.perf_counter() - started, 3)}
    keys = GROW_KEYS if name == "grow_tree" else MESH_KEYS if name in ("tree_mesh", "tree_leaves") else ()
    entry.update({key: result[key] for key in keys if key in result})
    if name == "export":
        entry["skeletons"] = result.get("skeletons", [])
    LOG.append(entry)
    return result


def scaled(points, detail):
    return max(1, int(round(points * detail)))


def grow(send=None, detail=None):
    send = send or cmd
    detail = DETAIL if detail is None else detail
    for tree in TREES:
        args = dict(GROW[tree])
        args["roots"] = {**args["roots"], "points": scaled(args["roots"]["points"], detail)}
        if "points" in args:
            args["points"] = scaled(args["points"], detail)
        send("grow_tree", name=tree, location=PLACES[tree], limit=0, **args)


def materials():
    cmd("material_procedural", name="bark", bark={"grain": "y", "coordinates": "uv", "fissure_spacing": 0.035, "bump": 12.0})
    cmd("material_procedural", name="roots", bark={"grain": "y", "coordinates": "uv", "color": [0.11, 0.08, 0.06], "lichen_color": [0.09, 0.07, 0.05], "fissure_depth": 0.3})
    cmd("material_procedural", name="fresh_wood", wood={"grain": "z", "coordinates": "uv", "light_color": [0.6, 0.45, 0.27], "dark_color": [0.42, 0.29, 0.16], "ring_density": 160.0})
    cmd("material_procedural", name="leaf", leaf={"cutout": True})
    cmd("material_procedural", name="willow_leaf", leaf={"cutout": True, "color": [0.24, 0.36, 0.1], "dark_color": [0.14, 0.24, 0.06]})
    cmd("material_procedural", name="soil", soil={"moisture": 0.4})


def dress():
    for tree in TREES:
        cmd("tree_mesh", name=tree, **MESH[tree])
    for tree in TREES:
        cmd("tree_leaves", name=f"{tree}_bark", leaves_name=f"{tree}_leaves", **LEAVES[tree], **({"detail": "low"} if DETAIL < 1.0 else {}))


def ground():
    cmd("add_primitive", type="plane", name="ground", size=3.5 * SPACING, location=[0.0, 0.0, 0.0])
    cmd("assign_material", name="ground", material="soil")


def shots():
    views = {
        "willow": ([-SPACING, 0.0, 4.6], 17.0, [0.0, -1.0, 0.08]),
        "oak": ([0.0, 0.0, 5.0], 21.0, [0.0, -1.0, 0.08]),
        "coastal": ([SPACING + 2.5, 0.0, 3.4], 15.0, [0.0, -1.0, 0.08]),
        "row": ([0.0, 0.0, 4.5], 54.0, [0.15, -1.0, 0.1]),
        "oak_trunk": ([0.0, 0.0, 2.0], 6.0, [0.4, -1.0, 0.15]),
    }
    for name, (point, width, direction) in views.items():
        result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading="shaded", resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    cmd("new_scene")
    grow()
    materials()
    dress()
    cmd("save_blend", path="tree-shapes.blend")
    cmd("export", path="tree-shapes.glb")
    ground()
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


if __name__ == "__main__":
    main()
