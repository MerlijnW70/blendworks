import json
import math
import os
import sys
import tempfile
import time

arguments = sys.argv[sys.argv.index("--") + 1 :]
repo, out_path = arguments[0], arguments[1]
sys.path.insert(0, os.path.join(repo, "bridge"))

from blendworks_bridge import Handler
from blendworks_bridge import texel
from blendworks_bridge.uv_islands import UVGraph

import bpy
import numpy

OUTER, INNER, DEPTH, NOTCH = 0.1, 0.085, 0.006, 0.0012
packs = {"count": 0}
run_pack = getattr(texel, "run_pack", None)


def counted(*args):
    packs["count"] += 1
    return run_pack(*args)


if run_pack is not None:
    texel.run_pack = counted
handler = Handler(tempfile.mkdtemp(prefix="blendworks-uv-"), allow_python=False, desktop=False)


def call(command, **args):
    reply = handler.handle({"id": 1, "cmd": command, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{command}: {reply['error']}")
    return reply["result"]


def notched_ring(ticks):
    outline = []
    step = math.tau / ticks
    for tick in range(ticks):
        for fraction, radius in ((0.0, OUTER), (0.35, OUTER), (0.35, OUTER - NOTCH), (0.65, OUTER - NOTCH), (0.65, OUTER)):
            angle = (tick + fraction) * step
            outline.append([radius * math.cos(angle), radius * math.sin(angle)])
    hole = [[INNER * math.cos(math.tau * i / 180), INNER * math.sin(math.tau * i / 180)] for i in range(180)]
    call("extrude_outline", name="Ring", outline=outline, holes=[hole], depth=DEPTH)


notched_ring(360)
call("uv_smart_project", name="Ring", island_margin=0.002, min_island_area=0.002)
packs["count"] = 0
wall = time.perf_counter()
result = call("uv_pack", names=["Ring"], target="coverage", margin=0.004, texture_size=2048, time_limit=300)


def island_gap(name):
    obj = bpy.data.objects[name]
    graph = UVGraph(obj, obj.data.uv_layers.active)
    edges = {}
    for face, label in enumerate(graph.labels.tolist()):
        loops = numpy.arange(int(graph.start[face]), int(graph.start[face] + graph.total[face]))
        edges.setdefault(label, []).append((graph.uv[loops], graph.uv[numpy.roll(loops, -1)]))
    islands = {label: (numpy.concatenate([a for a, _ in parts]), numpy.concatenate([b for _, b in parts])) for label, parts in edges.items()}
    smallest = 1.0
    for label, (points, _) in islands.items():
        for other, (starts, ends) in islands.items():
            if other == label:
                continue
            reach = smallest
            low, high = numpy.minimum(starts, ends).min(axis=0) - reach, numpy.maximum(starts, ends).max(axis=0) + reach
            near = points[((points > low) & (points < high)).all(axis=1)]
            if len(near) == 0:
                continue
            direction = ends - starts
            length = numpy.maximum((direction * direction).sum(axis=1), 1e-30)
            along = numpy.clip(((near[:, None, :] - starts[None]) * direction[None]).sum(axis=2) / length[None], 0.0, 1.0)
            closest = starts[None] + along[..., None] * direction[None]
            smallest = min(smallest, float(numpy.sqrt(((near[:, None, :] - closest) ** 2).sum(axis=2)).min()))
    return smallest


report = {
    "seconds": time.perf_counter() - wall,
    "packs": packs["count"],
    "trials": len(result["search"]["search"]),
    "best": result["search"]["best"][0],
    "density": result["texel_density"],
    "overlap": result["objects"][0]["overlap"],
    "outside": result["objects"][0]["outside"],
    "gap": island_gap("Ring"),
}
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(report, handle)
