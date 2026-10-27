import time

import numpy

from .texel import pack
from .uv_islands import UVGraph, equalize_density, merge_small_islands

STAGES = (("AABB", None), ("CONVEX", None), ("CONCAVE", None), ("CONVEX", "CARDINAL"), ("CONCAVE", "CARDINAL"))
OUTSIDE = 1e-5


def merge_islands(obj, minimum_share):
    layer = obj.data.uv_layers.active
    graph = UVGraph(obj, layer)
    before = len(set(graph.labels.tolist()))
    merged = merge_small_islands(graph, minimum_share)
    graph.write()
    return {"before": before, "merged": merged, "after": before - merged}


class Layout:
    def __init__(self, obj, graph):
        self.obj = obj
        self.triangles = graph.triangle_loops
        self.initial = graph.uv.copy()

    def restore(self):
        self.set(self.initial)

    def rebase(self, uv):
        self.initial = uv

    def set(self, uv):
        self.obj.data.uv_layers.active.uv.foreach_set("vector", uv.reshape(-1))
        self.obj.data.update()

    def read(self):
        data = self.obj.data.uv_layers.active.uv
        flat = numpy.empty(len(data) * 2, dtype=numpy.float64)
        data.foreach_get("vector", flat)
        return flat.reshape(-1, 2)

    def area_and_bounds(self, uv):
        corners = uv[self.triangles]
        first, second = corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]
        area = 0.5 * numpy.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]).sum()
        return float(area), float(uv.min()), float(uv.max())


def tighter_margins(margin, floor):
    values = []
    for value in (margin * 0.5, floor):
        value = max(floor, value)
        if value < margin and value not in values:
            values.append(value)
    return values


def search_packing(view_layer, group, layouts, margin, floor, rotate, deadline):
    best = None
    log = []
    cost = 0.0

    def affordable(stage, value):
        shape, rotation = stage
        predicted = 0.0 if shape == "AABB" else cost * (2.0 if rotation else 1.0) / (value * value)
        return best is None or time.monotonic() + predicted <= deadline

    def attempt(stage, value):
        nonlocal best, cost
        shape, rotation = stage
        for layout in layouts:
            layout.restore()
        started = time.monotonic()
        pack(view_layer, group, value, rotation is not None, True, rotation or "ANY", shape)
        if shape != "AABB":
            cost = max(cost, (time.monotonic() - started) * value * value / (2.0 if rotation else 1.0))
        uvs = [layout.read() for layout in layouts]
        measured = [layout.area_and_bounds(uv) for layout, uv in zip(layouts, uvs)]
        covered = sum(item[0] for item in measured)
        inside = all(item[1] >= -OUTSIDE and item[2] <= 1.0 + OUTSIDE for item in measured)
        log.append({"shape": shape.lower(), "rotation": rotation.lower() if rotation else "off", "margin": round(value, 6), "coverage": round(covered, 6), "inside": inside})
        if inside and (best is None or covered > best[0] + 1e-12):
            best = (covered, uvs, log[-1], stage)
        return uvs, inside

    for stage in STAGES:
        if (stage[1] is None or rotate) and affordable(stage, margin):
            uvs, inside = attempt(stage, margin)
            if stage[0] == "AABB" and inside:
                for layout, rebased in zip(layouts, uvs):
                    layout.rebase(rebased)
    if best is not None:
        for value in tighter_margins(margin, floor):
            if affordable(best[3], value):
                attempt(best[3], value)
    return best, log


def pack_for_coverage(ctx, groups, args, texture_size):
    started = time.monotonic()
    deadline = started + args.get("time_limit", 30.0)
    floor = 2.0 / texture_size
    reports = {"islands": {"before": 0, "after": 0, "merged": 0}, "search": [], "best": []}
    for group in groups:
        graphs = [UVGraph(obj, obj.data.uv_layers.active) for obj in group]
        reports["islands"]["before"] += sum(len(set(graph.labels.tolist())) for graph in graphs)
        merged = sum(merge_small_islands(graph, args.get("min_island_area", 0.002)) for graph in graphs)
        reports["islands"]["merged"] += merged
        equalize_density(graphs)
        layouts = []
        for obj, graph in zip(group, graphs):
            graph.write()
            layouts.append(Layout(obj, graph))
        reports["islands"]["after"] += sum(len(set(graph.labels.tolist())) for graph in graphs)
        best, log = search_packing(ctx.view_layer, group, layouts, args["margin"], floor, args["rotate"], deadline)
        reports["search"].extend(log)
        if best is None:
            for layout in layouts:
                layout.restore()
            continue
        for layout, uv in zip(layouts, best[1]):
            layout.set(uv)
        reports["best"].append(best[2])
    reports["seconds"] = round(time.monotonic() - started, 3)
    return reports
