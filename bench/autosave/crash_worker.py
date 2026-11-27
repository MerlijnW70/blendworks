import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARGUMENTS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(ARGUMENTS) < 3:
    raise SystemExit("blender -b --factory-startup -t <threads> --python bench/autosave/crash_worker.py -- <bridge folder> <out folder> <check|full>")
BRIDGE, OUT, SIZE = os.path.abspath(ARGUMENTS[0]), os.path.abspath(ARGUMENTS[1]), ARGUMENTS[2]
sys.path.insert(0, BRIDGE)
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, HERE)

import bpy
import numpy

import measures
import scene
from driver import Driver

REPLIES = os.path.join(OUT, "replies.jsonl")


class Resuming(Driver):
    def __init__(self, out, size, served):
        super().__init__(out, size)
        self.served = served
        self.index = 0
        self.log = open(REPLIES, "a", encoding="utf-8")

    def call(self, name, required, args):
        index = self.index
        self.index += 1
        if index < len(self.served):
            reply = self.served[index]
            if reply["cmd"] != name:
                raise RuntimeError(f"call {index} is {name}, but the earlier run made {reply['cmd']}")
        else:
            print(f"CALL {index} {name}", flush=True)
            reply = dict(self.handler.handle({"cmd": name, "args": args}), cmd=name)
            self.log.write(json.dumps({key: reply.get(key) for key in ("cmd", "ok", "result", "error")}) + "\n")
            self.log.flush()
        if not reply["ok"]:
            if required:
                raise RuntimeError(f"{name}: {reply['error']['message']}")
            return None
        return reply["result"]


def serve_scene_reads():
    read_points = scene.land_points
    reads = {"count": 0}

    def land_points():
        path = os.path.join(OUT, f"land-points-{reads['count']}.npy")
        reads["count"] += 1
        if os.path.isfile(path):
            return numpy.load(path)
        points = read_points()
        numpy.save(path, points)
        return points

    scene.land_points = land_points


def main():
    os.makedirs(OUT, exist_ok=True)
    served = []
    if os.path.isfile(REPLIES):
        with open(REPLIES, encoding="utf-8") as handle:
            served = [json.loads(line) for line in handle if line.strip()]
    serve_scene_reads()
    driver = Resuming(OUT, SIZE, served)
    if served:
        reply = driver.handler.handle({"cmd": "recover", "args": {}})
        result = reply.get("result") or {}
        print("RECOVERED " + json.dumps({"ok": reply["ok"], "served": len(served), "replayed": result.get("replayed"), "not_replayed": result.get("not_replayed"),
                                         "reason": result.get("reason"), "error": reply.get("error")}), flush=True)
    scene.build(driver)
    geometry = measures.geometry(bpy.context.scene)
    digest = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode("utf-8")).hexdigest()
    with open(os.path.join(OUT, "geometry.json"), "w", encoding="utf-8") as handle:
        json.dump(geometry, handle, indent=1)
    print(f"DONE {digest}", flush=True)


main()
