import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run
from blendworks_bridge.profiles import rounded_rectangle
from shell_helpers import build

SHAPE = dict(W=1.6, D=0.5, T=1.0, turns=6.0, steps=48, size=0.1)
BAND = (0.5, 2.0)
SQUARE = [[0.0, -0.03], [0.06, -0.03], [0.06, 0.03], [0.0, 0.03]]
FILLET_STEPS = 6
PLANK = [[u + 0.03, v] for u, v in rounded_rectangle(0.06, 0.03, 0.004, FILLET_STEPS)]


def edge_stretch(name, result):
    mesh = bpy.data.objects[name].data
    layer = mesh.uv_layers.active
    count = result["points_per_ring"]
    outer_vertices = result["rings"] * count
    along, around = {}, []
    for polygon in mesh.polygons:
        if not all(v < outer_vertices for v in polygon.vertices) or len(polygon.vertices) != 4:
            continue
        corners = list(zip(polygon.vertices, polygon.loop_indices))
        for (a, la), (b, lb) in zip(corners, corners[1:] + corners[:1]):
            world = (mesh.vertices[a].co - mesh.vertices[b].co).length
            flat = (layer.uv[la].vector - layer.uv[lb].vector).length
            ring_a, ring_b = a // count, b // count
            if ring_a == ring_b:
                around.append(flat / world)
            elif a % count == b % count:
                along.setdefault(min(ring_a, ring_b), []).append(flat / world)
    return along, around


def test_uv_along_the_spiral_stays_within_a_band_over_all_turns(bridge):
    result = build(bridge, **SHAPE)
    along, around = edge_stretch("S", result)
    scale = statistics.median(value for values in along.values() for value in values)
    tail = result["tail_rings"]
    rings = [k for k in along if k >= tail]
    assert len(rings) > 6 * SHAPE["steps"] - 2
    for k in rings:
        for value in along[k]:
            assert BAND[0] <= value / scale <= BAND[1], (k, value / scale)
    per_turn = [statistics.mean(value for k in rings if tail + turn * 48 <= k < tail + (turn + 1) * 48 for value in along[k]) for turn in range(6)]
    assert max(per_turn) / min(per_turn) < 1.02, per_turn
    assert max(around) / min(around) < 1.0001


def test_uv_u_is_the_arc_length_around_the_profile(bridge):
    result = build(bridge, **SHAPE)
    along, around = edge_stretch("S", result)
    assert max(around) / min(around) < 1.0 + 1e-4
    assert len(around) > 6 * 48 * result["points_per_ring"] * 0.9


def test_a_material_in_metres_does_not_stretch_towards_the_aperture(bridge):
    result = build(bridge, **SHAPE)
    mesh = bpy.data.objects["S"].data
    layer = mesh.uv_layers.active
    count = result["points_per_ring"]
    early, late = [], []
    for polygon in mesh.polygons:
        if len(polygon.vertices) != 4 or not all(v < result["rings"] * count for v in polygon.vertices):
            continue
        ring = polygon.vertices[0] // count - result["tail_rings"]
        area = polygon.area
        flat = abs(sum(layer.uv[a].vector.x * layer.uv[b].vector.y - layer.uv[b].vector.x * layer.uv[a].vector.y for a, b in zip(polygon.loop_indices, list(polygon.loop_indices)[1:] + list(polygon.loop_indices)[:1]))) / 2.0
        if 0 <= ring < 48:
            early.append(flat / area)
        elif ring >= 5 * 48:
            late.append(flat / area)
    assert abs(statistics.mean(late) / statistics.mean(early) - 1.0) < 0.02


def corner_normals(name):
    mesh = bpy.data.objects[name].data
    return mesh, [normal.vector.copy() for normal in mesh.corner_normals]


def vertex_spread(name, vertex):
    mesh, normals = corner_normals(name)
    around = [normals[loop] for loop in range(len(mesh.loops)) if mesh.loops[loop].vertex_index == vertex]
    return math.degrees(max(a.angle(b) for a in around for b in around))


def test_default_shading_flat_caps_hard_profile_corners_and_smooth_elsewhere(bridge):
    smooth = build(bridge, name="Round", W=1.4, D=0.4, T=1.5, turns=3.0, steps=48, profile_segments=32)
    count = smooth["points_per_ring"]
    middle = smooth["tail_rings"] + 70
    assert all(vertex_spread("Round", middle * count + j) < 0.01 for j in range(count))
    mesh, normals = corner_normals("Round")
    caps = [polygon for polygon in mesh.polygons if len(polygon.vertices) == count]
    assert len(caps) == 2
    for polygon in caps:
        assert max(polygon.normal.angle(normals[loop]) for loop in polygon.loop_indices) < math.radians(0.01)
    build(bridge, name="Boxy", W=1.4, D=0.4, T=1.5, turns=3.0, steps=48, profile="points", points=SQUARE)
    boxy = bpy.data.objects["Boxy"].data
    corner = (smooth["tail_rings"] + 70) * 4
    assert vertex_spread("Boxy", corner) > 80.0
    flat_side = [polygon for polygon in boxy.polygons if len(polygon.vertices) == 4 and {v % 4 for v in polygon.vertices} == {0, 1}]
    assert flat_side


def test_a_long_flat_side_stays_hard_against_its_rounded_corners(bridge):
    result = build(bridge, name="Plank", W=1.4, D=0.4, T=1.5, turns=3.0, steps=48, profile="points", points=PLANK)
    count = result["points_per_ring"]
    assert count == 4 * (FILLET_STEPS + 1)
    ring = (result["tail_rings"] + 70) * count
    junctions = [ring + j for j in range(count) if j % (FILLET_STEPS + 1) in (0, FILLET_STEPS)]
    rounded = [ring + j for j in range(count) if j % (FILLET_STEPS + 1) not in (0, FILLET_STEPS)]
    assert all(vertex_spread("Plank", vertex) > 5.0 for vertex in junctions)
    assert all(vertex_spread("Plank", vertex) < 0.01 for vertex in rounded)


def test_flat_shading_and_smooth_shading_are_honoured(bridge):
    build(bridge, name="Faceted", W=1.4, D=0.4, T=1.5, turns=2.0, steps=24, shading="flat")
    assert not any(polygon.use_smooth for polygon in bpy.data.objects["Faceted"].data.polygons)
    build(bridge, name="Soft", W=1.4, D=0.4, T=1.5, turns=2.0, steps=24, shading="smooth")
    assert sum(polygon.use_smooth for polygon in bpy.data.objects["Soft"].data.polygons) > 0.9 * len(bpy.data.objects["Soft"].data.polygons)


run(globals())
