import json
import os
import shutil
import sys
import tempfile
import time

USAGE = (
    "blender --background --factory-startup --python scripts/uv-pack-bench.py -- <repo> <scene.blend> <out.json> [margin] [texture size]\n"
    "Packs every mesh of the scene as one atlas with uv_pack target coverage, as the armillary-v2 build does, with the bridge of <repo>,\n"
    "and writes the wall time, the coverage, the texel density and every trial. Run it with the old and the new repository to compare."
)

arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
if len(arguments) < 3:
    print(USAGE, file=sys.stderr)
    sys.exit(2)
repo, scene, out_path = arguments[:3]
margin = float(arguments[3]) if len(arguments) > 3 else 0.0015
texture_size = int(arguments[4]) if len(arguments) > 4 else 2048
sys.path.insert(0, os.path.join(os.path.abspath(repo), "bridge"))

import bpy

from blendworks_bridge import Handler

workspace = tempfile.mkdtemp(prefix="blendworks-uv-bench-")
shutil.copy(scene, os.path.join(workspace, "scene.blend"))
handler = Handler(workspace, allow_python=False, desktop=False)


def call(command, **args):
    reply = handler.handle({"id": 1, "cmd": command, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{command}: {reply['error']}")
    return reply["result"]


call("load_blend", path="scene.blend")
names = sorted(obj.name for obj in bpy.context.scene.objects if obj.type == "MESH")
started = time.perf_counter()
result = call("uv_pack", names=names, target="coverage", margin=margin, rotate=True, shared=True, uniform_density=True, texture_size=texture_size, time_limit=60)
seconds = time.perf_counter() - started
report = {
    "seconds": round(seconds, 3),
    "objects": len(names),
    "islands": result["search"]["islands"],
    "best": result["search"]["best"],
    "trials": result["search"]["search"],
    "texelDensity": result["texel_density"],
    "overlap": max(entry["overlap"] for entry in result["objects"]),
    "outside": any(entry["outside"] for entry in result["objects"]),
}
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=1)
print(json.dumps({key: report[key] for key in ("seconds", "best", "overlap", "outside")}))
shutil.rmtree(workspace, ignore_errors=True)
