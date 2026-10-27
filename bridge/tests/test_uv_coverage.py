import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
import numpy

from harness import close, run

OUTER, INNER, DEPTH = 0.1, 0.085, 0.006
NOTCH = 0.0012


def notched_ring(bridge, ticks, name="Ring"):
    outline = []
    step = math.tau / ticks
    for tick in range(ticks):
        for fraction, radius in ((0.0, OUTER), (0.35, OUTER), (0.35, OUTER - NOTCH), (0.65, OUTER - NOTCH), (0.65, OUTER)):
            angle = (tick + fraction) * step
            outline.append([radius * math.cos(angle), radius * math.sin(angle)])
    hole = [[INNER * math.cos(math.tau * i / 180), INNER * math.sin(math.tau * i / 180)] for i in range(180)]
    bridge.ok("extrude_outline", name=name, outline=outline, holes=[hole], depth=DEPTH)


def islands(name):
    mesh = bpy.data.objects[name].data
    graph = bmesh.new()
    graph.from_mesh(mesh)
    layer = graph.loops.layers.uv.active
    graph.faces.ensure_lookup_table()
    parent = list(range(len(graph.faces)))

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for edge in graph.edges:
        if len(edge.link_faces) != 2:
            continue
        first, second = edge.link_faces
        joined = all(
            (next(l for l in first.loops if l.vert == v)[layer].uv - next(l for l in second.loops if l.vert == v)[layer].uv).length < 1e-6
            for v in edge.verts
        )
        if joined:
            parent[find(first.index)] = find(second.index)
    groups = {}
    for face in graph.faces:
        points = [loop[layer].uv.copy() for loop in face.loops]
        area = 0.5 * abs(sum(a.x * b.y - b.x * a.y for a, b in zip(points, points[1:] + points[:1])))
        entry = groups.setdefault(find(face.index), {"area": 0.0, "low": [1e9, 1e9], "high": [-1e9, -1e9]})
        entry["area"] += area
        for point in points:
            entry["low"] = [min(entry["low"][0], point.x), min(entry["low"][1], point.y)]
            entry["high"] = [max(entry["high"][0], point.x), max(entry["high"][1], point.y)]
    graph.free()
    return list(groups.values())


def box_ratio(name):
    groups = islands(name)
    boxes = sum((group["high"][0] - group["low"][0]) * (group["high"][1] - group["low"][1]) for group in groups)
    return sum(group["area"] for group in groups) / boxes, len(groups)


def uv_values(name):
    layer = bpy.data.objects[name].data.uv_layers.active
    flat = numpy.empty(len(layer.uv) * 2)
    layer.uv.foreach_get("vector", flat)
    return flat.reshape(-1, 2)


def set_uv_values(name, values):
    obj = bpy.data.objects[name]
    obj.data.uv_layers.active.uv.foreach_set("vector", values.reshape(-1))
    obj.data.update()


def test_a_notched_ring_goes_from_a_collapsed_baseline_to_the_coverage_worked_out_from_its_islands(bridge):
    notched_ring(bridge, 360)
    baseline = bridge.ok("uv_smart_project", name="Ring")
    assert baseline["uv_area"] < 0.01 and baseline["coverage"] < 0.01
    start = bridge.ok("uv_smart_project", name="Ring", island_margin=0.002, min_island_area=0.002)
    assert start["islands"]["before"] == 1380 and start["islands"]["after"] < 100
    assert start["islands"]["merged"] == 1380 - start["islands"]["after"]
    assert start["coverage"] > 0.15 and start["overlap"] < 0.01 and start["outside"] is False
    ratio, count = box_ratio("Ring")
    stated = 0.7 * ratio
    assert count == start["islands"]["after"] and 0.25 < ratio < 0.4
    result = bridge.ok("uv_pack", names=["Ring"], target="coverage", margin=0.004, texture_size=2048, time_limit=300)
    best = result["search"]["best"][0]
    assert best["coverage"] >= stated, (best, stated)
    assert result["coverage"] >= stated * 0.97 and result["objects"][0]["overlap"] < 0.01 and result["objects"][0]["outside"] is False
    assert best["coverage"] > baseline["coverage"] + 0.15 and best["inside"] is True
    density = result["texel_density"]
    assert density["max"] / density["min"] < 1.5 and density["texture_size"] == 2048
    assert result["target"] == "coverage" and result["search"]["islands"]["merged"] == 0
    stages = [(entry["shape"], entry["rotation"]) for entry in result["search"]["search"]]
    assert stages[:5] == [("aabb", "off"), ("convex", "off"), ("concave", "off"), ("convex", "cardinal"), ("concave", "cardinal")]
    assert {entry["margin"] for entry in result["search"]["search"][:5]} == {0.004}
    assert 6 <= len(stages) <= 7 and {entry["margin"] for entry in result["search"]["search"][5:]} <= {0.002, round(2 / 2048, 6)}


def scattered(bridge, name="Scatter"):
    vertices, faces, uvs = [], [], []
    for index in range(12):
        x = index * 1.5
        vertices += [[x, 0, 0], [x + 1, 0, 0], [x + 1, 1, 0], [x, 1, 0]]
        faces.append([4 * index + k for k in range(4)])
        size = 0.05 + 0.02 * (index % 5)
        uvs += [[0.1 * (index % 4), 0.2 * (index // 4)], [0.1 * (index % 4) + size, 0.2 * (index // 4)], [0.1 * (index % 4) + size, 0.2 * (index // 4) + size * 1.5], [0.1 * (index % 4), 0.2 * (index // 4) + size * 1.5]]
    bridge.ok("mesh_from_data", name=name, vertices=vertices, faces=faces, uvs=uvs)


def test_the_packing_search_is_deterministic(bridge):
    scattered(bridge)
    start = uv_values("Scatter")
    first = bridge.ok("uv_pack", names=["Scatter"], target="coverage", margin=0.01, texture_size=256, rotate=False, time_limit=300)
    layout = uv_values("Scatter")
    set_uv_values("Scatter", start)
    second = bridge.ok("uv_pack", names=["Scatter"], target="coverage", margin=0.01, texture_size=256, rotate=False, time_limit=300)
    assert first["search"]["search"] == second["search"]["search"]
    assert first["search"]["best"] == second["search"]["best"]
    close(uv_values("Scatter").reshape(-1).tolist(), layout.reshape(-1).tolist(), 1e-12)
    log = first["search"]["search"]
    assert [(entry["shape"], entry["rotation"], entry["margin"]) for entry in log[:3]] == [("aabb", "off", 0.01), ("convex", "off", 0.01), ("concave", "off", 0.01)]
    assert [entry["margin"] for entry in log[3:]] == [round(2 / 256, 6)] and len(log) == 4
    best = first["search"]["best"][0]
    assert best["coverage"] == max(entry["coverage"] for entry in log if entry["inside"]) and first["coverage"] > 0.15


def test_the_search_stops_after_the_trial_that_passes_the_time_limit(bridge):
    notched_ring(bridge, 36)
    bridge.ok("uv_smart_project", name="Ring", island_margin=0.002, min_island_area=0.002)
    quick = bridge.ok("uv_pack", names=["Ring"], target="coverage", margin=0.004, time_limit=1.0)
    assert 1 <= len(quick["search"]["search"]) < 5


def flat_pair(bridge, scale_b=1.0, offset_b=(2.0, 0.0), seam=False):
    vertices = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0]]
    faces = [[0, 1, 2, 3], [1, 4, 5, 2]]
    uvs = [[0, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]]
    second = [[0, 0], [0, 0.2 * scale_b], [-0.2 * scale_b, 0.2 * scale_b], [-0.2 * scale_b, 0]]
    second = [[u + offset_b[0], v + offset_b[1]] for u, v in second]
    bridge.ok("mesh_from_data", name="Pair", vertices=vertices, faces=faces, uvs=uvs + second)
    if seam:
        mesh = bpy.data.objects["Pair"].data
        for edge in mesh.edges:
            if set(edge.vertices) == {1, 2}:
                edge.use_seam = True


def test_islands_merge_across_an_edge_that_is_not_a_seam(bridge):
    flat_pair(bridge, offset_b=(0.5, 0.5))
    before = islands("Pair")
    assert len(before) == 2
    result = bridge.ok("uv_pack", names=["Pair"], target="coverage", min_island_area=0.9, margin=0.01, time_limit=1.0)
    assert result["search"]["islands"] == {"before": 2, "after": 1, "merged": 1}
    assert len(islands("Pair")) == 1


def test_a_marked_seam_keeps_islands_apart(bridge):
    flat_pair(bridge, offset_b=(0.5, 0.5), seam=True)
    result = bridge.ok("uv_pack", names=["Pair"], target="coverage", min_island_area=0.9, margin=0.01, time_limit=1.0)
    assert result["search"]["islands"] == {"before": 2, "after": 2, "merged": 0}


def test_merging_never_creates_overlap_and_leaves_big_islands_alone(bridge):
    vertices = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    faces = [[0, 3, 2, 1], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7], [4, 5, 6, 7]]
    bridge.ok("mesh_from_data", name="Cube", vertices=vertices, faces=faces)
    bridge.ok("uv_smart_project", name="Cube", island_margin=0.0)
    count = len(islands("Cube"))
    kept = bridge.ok("uv_smart_project", name="Cube", island_margin=0.0, min_island_area=0.05)
    assert kept["islands"] == {"before": count, "after": count, "merged": 0}
    everything = bridge.ok("uv_smart_project", name="Cube", island_margin=0.0, min_island_area=1.0)
    assert everything["islands"]["after"] + everything["islands"]["merged"] == count and everything["overlap"] == 0.0


def test_an_atlas_of_unlike_islands_gets_one_texel_density(bridge):
    flat_pair(bridge, scale_b=4.0, offset_b=(0.6, 0.0), seam=True)
    before = bridge.ok("uv_info", name="Pair", texture_size=1024)["texel_density"]
    assert before["max"] > 3 * before["min"]
    result = bridge.ok("uv_pack", names=["Pair"], target="coverage", margin=0.01, texture_size=1024, time_limit=1.0)
    density = result["texel_density"]
    close(density["max"], density["min"], 0.02 * density["max"])
    assert result["coverage"] > 0.2


def test_coverage_packing_refuses_what_belongs_to_the_other_target(bridge):
    flat_pair(bridge)
    bridge.refuse("uv_pack", "bad_args", names=["Pair"], target="coverage", texel_density=100.0)
    bridge.refuse("uv_pack", "bad_args", names=["Pair"], min_island_area=0.01)
    bridge.refuse("uv_pack", "bad_args", names=["Pair"], time_limit=5.0)
    bridge.refuse("uv_pack", "bad_args", names=["Pair"], target="coverage", min_island_area=0.9, time_limit=0.1)
    bridge.refuse("uv_pack", "bad_args", names=["Pair"], target="best")
    bridge.refuse("uv_smart_project", "bad_args", name="Pair", min_island_area=1.5)
    fit = bridge.ok("uv_pack", names=["Pair"], margin=0.01)
    assert fit["target"] == "fit" and "search" not in fit and fit["coverage"] > 0 and fit["texel_density"]["mean"] > 0


run(globals())
