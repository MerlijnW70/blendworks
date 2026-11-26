import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "bridge"))

import bpy
import numpy

from blendworks_bridge.tree_crown import crown_fill, world_bounds

ARGS = sys.argv[sys.argv.index("--") + 1 :]
MODELS = os.path.abspath(ARGS[0])
OUT = os.path.abspath(ARGS[1])


MIN_HEIGHT = 2.0


def whole_trees(objects):
    found = []
    for obj in sorted(objects, key=lambda item: item.name):
        low, high = world_bounds([obj])
        if high[2] - low[2] >= MIN_HEIGHT:
            found.append([obj.name])
    return found


def is_foliage(material):
    """The scans name their leaf cards `*_leaves`, and the conifers' needle cards `*_twig`."""
    name = material.name if material is not None else ""
    return name.endswith("_leaves") or name.endswith("_twig")


def measure(asset):
    folder = os.path.join(MODELS, asset)
    blend = next(name for name in sorted(os.listdir(folder)) if name.endswith(".blend"))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(folder, blend), load_ui=False, use_scripts=False)
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj.visible_get()]
    if any("LOD" in obj.name for obj in objects):
        objects = [obj for obj in objects if "LOD0" in obj.name]
    with open(os.path.join(folder, "source.json"), encoding="utf-8") as handle:
        source = json.load(handle)
    return [{**source, "objects": names, **crown_fill(names, is_foliage)} for names in whole_trees(objects)]


def main():
    results = [tree for asset in sorted(os.listdir(MODELS)) if os.path.isdir(os.path.join(MODELS, asset)) for tree in measure(asset)]
    summary = {}
    for key in ("fill", "foliage_fill"):
        values = numpy.array([entry[key] for entry in results])
        summary[key] = {"trees": len(results), "mean": round(float(values.mean()), 4), "min": round(float(values.min()), 4), "max": round(float(values.max()), 4), "std": round(float(values.std()), 4)}
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "trees": results}, handle, indent=1)
    for entry in results:
        print(entry["asset"], entry["objects"], entry["fill"], entry["foliage_fill"], {view: item["foliage_fill"] for view, item in entry["views"].items()})
    print(summary)


main()
