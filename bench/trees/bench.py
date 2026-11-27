"""Tree batch benchmark: build a tree set with grow_trees in this session (serial) or in child sessions (parallel), and
write the wall time and the exact digest of the result (objects, names, collections, geometry with every attribute,
material contents) to <out>/<mode>.json, so the two modes can be compared.

blender --background --factory-startup --python bench/trees/bench.py -- <out folder> serial|parallel [--size check|full] [--workers n]"""
import json
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))
sys.path.insert(0, os.path.join(HERE, ".."))

from blendworks_bridge import Handler  # noqa: E402
from scene_digest import material_digest, scene_digest  # noqa: E402

SPECIES = ("oak", "birch", "pine")
SIZES = {"check": {"count": 6, "detail": "low"}, "full": {"count": 9, "detail": "high"}}


def option(name, default):
    args = sys.argv[sys.argv.index("--") + 1:]
    return args[args.index(name) + 1] if name in args else default


def tree_set(size):
    settings = SIZES[size]
    trees = []
    for index in range(settings["count"]):
        location = [12.0 * (index % 3), 12.0 * (index // 3), 0.0]
        trees.append({
            "grow": {"name": f"tree_{index}", "preset": SPECIES[index % 3], "seed": 10 + index, "location": location, "limit": 0},
            "mesh": {},
            "leaves": {"seed": 10 + index, "detail": settings["detail"]},
        })
    return trees


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out, mode = os.path.abspath(args[0]), args[1]
    size = option("--size", "check")
    os.makedirs(out, exist_ok=True)
    handler = Handler(out, allow_python=False, autosave_seconds=None)
    handler.handle({"cmd": "new_scene", "args": {}})
    request = {"trees": tree_set(size), "parallel": mode == "parallel"}
    if option("--workers", None):
        request["workers"] = int(option("--workers", None))
    started = time.perf_counter()
    reply = handler.handle({"cmd": "grow_trees", "args": request})
    wall = time.perf_counter() - started
    if not reply["ok"]:
        raise RuntimeError(reply["error"]["message"])
    result = reply["result"]
    bpy.context.view_layer.update()
    record = {"mode": mode, "size": size, "wall": round(wall, 3), "report": {key: value for key, value in result.items() if key != "trees"},
              "trees": [{"name": tree["name"], "built": tree["built"], "results": tree["results"]} for tree in result["trees"]],
              "objects": scene_digest(), "materials": material_digest(), "images": sorted(image.name for image in bpy.data.images),
              "node_groups": sorted(group.name for group in bpy.data.node_groups)}
    with open(os.path.join(out, f"{mode}.json"), "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=1, sort_keys=True, default=str)
    print(f"TREES {mode} {size} wall {wall:.1f} s workers {result['workers']} fallbacks {len(result['fallbacks'])}", flush=True)


main()
