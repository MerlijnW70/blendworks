import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ARGUMENTS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
USAGE = "blender -b --factory-startup -t <threads> --python bench/autosave/run.py -- <bridge folder> <out folder> <check|full> [on|off]"

if len(ARGUMENTS) < 3:
    raise SystemExit(USAGE)
BRIDGE, OUT, SIZE = (os.path.abspath(ARGUMENTS[0]), os.path.abspath(ARGUMENTS[1]), ARGUMENTS[2])
MODE = ARGUMENTS[3] if len(ARGUMENTS) > 3 else "on"
if MODE == "off":
    os.environ["BLENDWORKS_AUTOSAVE_SECONDS"] = "off"
sys.path.insert(0, BRIDGE)
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, HERE)

import bpy

import measures
import scene
from driver import Driver, folder_bytes


def blender_threads():
    for flag in ("-t", "--threads"):
        if flag in sys.argv:
            return int(sys.argv[sys.argv.index(flag) + 1])
    return 0


def main():
    os.makedirs(OUT, exist_ok=True)
    driver = Driver(OUT, SIZE)
    started = time.perf_counter()
    scene.build(driver)
    wall = time.perf_counter() - started
    autosave = driver.handler.autosave
    geometry = measures.geometry(bpy.context.scene)
    path = os.path.join(OUT, "scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, compress=False)
    summary = {
        "size": SIZE,
        "mode": MODE,
        "bridge": BRIDGE,
        "environment": measures.environment(),
        "threads": blender_threads(),
        "build_wall": round(wall, 3),
        "autosave_seconds": round(driver.autosave_seconds(), 3),
        "autosave_share": round(driver.autosave_seconds() / wall, 5),
        "snapshots": getattr(autosave, "saves", None),
        "blend_bytes": os.path.getsize(path),
        "folder_peak_bytes": driver.folder_peak,
        "folder_end_bytes": folder_bytes(driver.folder),
        "peak_memory": measures.peak_memory_bytes(),
        "calls": len(driver.calls),
        "snapshot_log": driver.snapshots,
        "geometry_sha256": hashlib.sha256(json.dumps(geometry, sort_keys=True).encode("utf-8")).hexdigest(),
        "geometry": geometry,
    }
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=1)
    print(json.dumps({key: value for key, value in summary.items() if key not in ("geometry", "snapshot_log")}), flush=True)


main()
