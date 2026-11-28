import base64
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))
sys.path.insert(0, HERE)

import grow_trees
from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "tree-meshes"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "32"))
DETAIL = float(os.environ.get("BLENDWORKS_TREE_DETAIL", "1.0"))
SPACING = grow_trees.SPACING
HANDLER = None
LOG = []

BARK = {"bark_material": "bark", "root_material": "roots", "wood_material": "fresh_wood"}
MESH = {
    "oak": {**BARK, "flare": {"amount": 0.55, "lobes": 0.7}, "root_flare": {"amount": 1.6}},
    "conifer": {**BARK, "min_radius": 0.004, "flare": {"amount": 0.4, "lobes": 0.5}, "root_flare": {"amount": 1.2}},
    "windswept": {**BARK, "flare": {"amount": 0.6, "lobes": 0.8}, "root_flare": {"amount": 1.8}},
}
LEAVES = {
    "oak": {"material": "leaf", "size": 0.09, "seed": 3},
    "conifer": {"material": "needles", "layout": "single", "source": "needle_cluster", "size": 2.2, "density": 10.0, "tip_leaves": 2, "orders": 2, "angle": 40.0, "align": {"factor": 0.2}, "seed": 5},
    "windswept": {"material": "leaf", "size": 0.08, "align": {"sun": [0.3, 0.0, 1.0], "factor": 0.8}, "seed": 11},
}
SUMMARY_KEYS = ("name", "junction", "triangles", "manifold", "volume", "shells", "materials", "axes", "cut_ends", "self_intersections", "flare", "root_flare", "bark_noise", "skeleton", "leaves", "tip_leaves", "twigs", "count", "mesh")


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    entry = {"cmd": name, "seconds": round(time.perf_counter() - started, 3)}
    if name in ("tree_mesh", "tree_leaves"):
        entry.update({key: result[key] for key in SUMMARY_KEYS if key in result})
    if name == "export":
        entry["skeletons"] = result.get("skeletons", [])
    LOG.append(entry)
    return result


def needle_cluster():
    vertices = []
    faces = []
    uvs = []
    count = 9
    for index in range(count):
        turn = math.radians(index * 137.5)
        base = 0.12 * index / count
        lean = math.radians(45.0)
        direction = [math.cos(lean), math.sin(lean) * math.cos(turn), math.sin(lean) * math.sin(turn)]
        across = [0.0, -math.sin(turn), math.cos(turn)]
        length = 0.08
        half = 0.0022
        start = len(vertices)
        for along, side in ((0.0, -1.0), (0.0, 1.0), (1.0, 1.0), (1.0, -1.0)):
            vertices.append([base + direction[0] * length * along + across[0] * half * side, direction[1] * length * along + across[1] * half * side, direction[2] * length * along + across[2] * half * side])
        faces.append([start, start + 1, start + 2, start + 3])
        uvs.extend([[0.47, 0.0], [0.53, 0.0], [0.53, 1.0], [0.47, 1.0]])
    cmd("mesh_from_data", name="needle_cluster", vertices=vertices, faces=faces, uvs=uvs, smooth=True)


def materials():
    cmd("material_procedural", name="bark", bark={"grain": "y", "coordinates": "uv", "fissure_spacing": 0.035, "bump": 12.0})
    cmd("material_procedural", name="roots", bark={"grain": "y", "coordinates": "uv", "color": [0.11, 0.08, 0.06], "lichen_color": [0.09, 0.07, 0.05], "fissure_depth": 0.3})
    cmd("material_procedural", name="fresh_wood", wood={"grain": "z", "coordinates": "uv", "light_color": [0.6, 0.45, 0.27], "dark_color": [0.42, 0.29, 0.16], "ring_density": 160.0})
    cmd("material_procedural", name="leaf", leaf={"cutout": True})
    cmd("material_procedural", name="needles", leaf={"color": [0.02, 0.07, 0.025], "dark_color": [0.01, 0.03, 0.012], "vein_contrast": 0.1})
    cmd("material_procedural", name="soil", soil={"moisture": 0.4})


def meshes():
    for tree in ("oak", "conifer", "windswept"):
        cmd("tree_mesh", name=tree, **MESH[tree])


def foliage():
    needle_cluster()
    for tree in ("oak", "conifer", "windswept"):
        cmd("tree_leaves", name=f"{tree}_bark", leaves_name=f"{tree}_leaves", **LEAVES[tree])
    cmd("delete", names=["needle_cluster"])


def ground():
    cmd("add_primitive", type="plane", name="ground", size=3.0 * SPACING, location=[0.0, 0.0, 0.0])
    cmd("assign_material", name="ground", material="soil")


def shots():
    views = {
        "oak": ([-SPACING, 0.0, 4.8], 14.5, [0.0, -1.0, 0.1]),
        "conifer": ([0.0, 0.0, 7.0], 15.5, [0.0, -1.0, 0.1]),
        "windswept": ([SPACING + 2.2, 0.0, 3.6], 13.5, [0.0, -1.0, 0.1]),
        "row": ([1.5, 0.0, 5.5], 44.0, [0.25, -1.0, 0.12]),
        "oak_base": ([-SPACING, 0.0, 0.5], 2.6, [0.4, -1.0, 0.25]),
        "oak_bark": ([-SPACING, -0.25, 1.4], 0.7, [0.1, -1.0, 0.05]),
        "oak_fork": ([-SPACING, 0.0, 3.1], 2.4, [0.3, -1.0, 0.2]),
        "conifer_bark": ([0.0, -0.15, 1.5], 0.9, [0.2, -1.0, 0.1]),
        "windswept_base": ([SPACING, 0.0, 0.5], 2.6, [-0.4, -1.0, 0.25]),
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
    grow_trees.trees(cmd, DETAIL)
    materials()
    meshes()
    foliage()
    cmd("save_blend", path="tree-meshes.blend")
    cmd("export", path="tree-meshes.glb")
    ground()
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


if __name__ == "__main__":
    main()
