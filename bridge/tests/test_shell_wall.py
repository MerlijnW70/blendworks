import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

from harness import run
from kit_helpers import euler, is_closed_manifold, volume
from shell_helpers import build, mesh_ring, radius

THICKNESS = 0.003
SAMPLES = 4000
WHORLS = dict(W=1.5, D=0.3, T=2.2, turns=5.0, steps=48, size=0.1)


def split_surfaces(name, result):
    outer_vertices = result["rings"] * result["points_per_ring"]
    mesh = bpy.data.objects[name].data
    points = [vertex.co.copy() for vertex in mesh.vertices]
    outer = [polygon for polygon in mesh.polygons if all(v < outer_vertices for v in polygon.vertices)]
    inner = [polygon for polygon in mesh.polygons if all(v >= outer_vertices for v in polygon.vertices)]
    return points, outer, inner


def triangles(polygons):
    out = []
    for polygon in polygons:
        corners = list(polygon.vertices)
        out.extend((corners[0], corners[i], corners[i + 1]) for i in range(1, len(corners) - 1))
    return out


def sampled_points(points, polygons, count, seed):
    chosen = triangles(polygons)
    areas = []
    for a, b, c in chosen:
        areas.append(((points[b] - points[a]).cross(points[c] - points[a])).length / 2.0)
    generator = random.Random(seed)
    picked = generator.choices(range(len(chosen)), weights=areas, k=count)
    samples = []
    for index in picked:
        a, b, c = (points[i] for i in chosen[index])
        r1, r2 = math.sqrt(generator.random()), generator.random()
        samples.append(a * (1 - r1) + b * (r1 * (1 - r2)) + c * (r1 * r2))
    return samples


def thinnest_wall(name, result, seed=1):
    points, outer, inner = split_surfaces(name, result)
    assert outer and inner
    inner_tree = BVHTree.FromPolygons(points, [tuple(polygon.vertices) for polygon in inner])
    outer_tree = BVHTree.FromPolygons(points, [tuple(polygon.vertices) for polygon in outer])
    from_outer = min(inner_tree.find_nearest(p)[3] for p in sampled_points(points, outer, SAMPLES, seed))
    from_inner = min(outer_tree.find_nearest(p)[3] for p in sampled_points(points, inner, SAMPLES, seed + 1))
    return min(from_outer, from_inner)


def test_wall_is_at_least_the_thickness_everywhere_sampled(bridge):
    result = build(bridge, thickness=THICKNESS, **WHORLS)
    assert result["manifold"] is True and is_closed_manifold("S") and euler("S") == 2
    assert result["wall_min"] >= THICKNESS
    assert thinnest_wall("S", result) >= THICKNESS * (1 - 1e-4)
    assert thinnest_wall("S", result, seed=7) < THICKNESS * 2.5


def test_hollow_shell_has_a_smaller_positive_volume_and_an_open_aperture(bridge):
    solid = build(bridge, name="Solid", **WHORLS)
    hollow = build(bridge, name="Hollow", thickness=THICKNESS, **WHORLS)
    assert 0 < volume("Hollow") < volume("Solid") * 0.9
    assert hollow["mesh"]["faces"] > solid["mesh"]["faces"]
    points, outer, inner = split_surfaces("Hollow", hollow)
    last = hollow["rings"] - 1
    aperture = {last * hollow["points_per_ring"] + j for j in range(hollow["points_per_ring"])}
    assert not [polygon for polygon in bpy.data.objects["Hollow"].data.polygons if len(polygon.vertices) > 4 and aperture & set(polygon.vertices)]
    assert [polygon for polygon in bpy.data.objects["Solid"].data.polygons if len(polygon.vertices) > 4 and aperture & set(polygon.vertices)]
    capped = [polygon for polygon in bpy.data.objects["Solid"].data.polygons if len(polygon.vertices) == hollow["points_per_ring"]]
    assert len(capped) == 2
    inner_caps = [polygon for polygon in bpy.data.objects["Hollow"].data.polygons if len(polygon.vertices) == hollow["points_per_ring"]]
    assert len(inner_caps) == 2


def test_earliest_whorls_too_narrow_to_hollow_stay_solid(bridge):
    result = build(bridge, thickness=2 * THICKNESS, **WHORLS)
    start = result["cavity_from_ring"]
    assert result["tail_rings"] + 20 < start < result["rings"] - 100
    points, outer, inner = split_surfaces("S", result)
    inner_vertices = {v for polygon in inner for v in polygon.vertices}
    assert min(inner_vertices) >= result["rings"] * result["points_per_ring"]
    size = max(radius(p) for p in mesh_ring("S", result, start)) - min(radius(p) for p in mesh_ring("S", result, start))
    assert size >= 3.0 * 2 * THICKNESS


def test_lip_flares_and_thickens_the_rim(bridge):
    plain = build(bridge, name="Plain", thickness=THICKNESS, **WHORLS)
    lipped = build(bridge, name="Lipped", thickness=THICKNESS, lip={"flare": 0.3, "length": 0.15, "thicken": 1.0}, **WHORLS)
    count = plain["points_per_ring"]

    def rim_gap(name, result):
        mesh = bpy.data.objects[name].data
        outer_ring = (result["rings"] - 1) * count
        inner_start = result["rings"] * count
        inner_rim = inner_start + (result["rings"] - result["cavity_from_ring"] - 1) * count
        return min((mesh.vertices[outer_ring + j].co - mesh.vertices[inner_rim + j].co).length for j in range(count))

    assert rim_gap("Plain", plain) >= THICKNESS
    assert rim_gap("Lipped", lipped) >= 2.0 * THICKNESS * 0.98
    assert thinnest_wall("Lipped", lipped) >= THICKNESS * (1 - 1e-4)
    assert max(radius(p) for p in mesh_ring("Lipped", lipped, lipped["rings"] - 1)) > max(radius(p) for p in mesh_ring("Plain", plain, plain["rings"] - 1))


def test_wall_holds_with_ribs_ridges_and_a_flat_coil(bridge):
    ribbed = build(bridge, name="Ribbed", thickness=THICKNESS, ribs={"count": 10, "height": 0.04}, **WHORLS)
    assert ribbed["manifold"] and thinnest_wall("Ribbed", ribbed) >= THICKNESS * (1 - 1e-4)
    coil = build(bridge, name="Coil", W=2.2, D=0.55, T=0.0, turns=4.0, steps=64, size=0.12, profile="ellipse", aspect=1.3, thickness=0.004)
    assert coil["manifold"] and thinnest_wall("Coil", coil) >= 0.004 * (1 - 1e-4)


def test_hollow_mesh_has_no_loose_geometry(bridge):
    result = build(bridge, thickness=THICKNESS, **WHORLS)
    bm = bmesh.new()
    bm.from_mesh(bpy.data.objects["S"].data)
    try:
        assert all(len(edge.link_faces) == 2 for edge in bm.edges)
        assert not [vertex for vertex in bm.verts if not vertex.link_faces]
        assert abs(bm.calc_volume(signed=True) - result["volume"]) < 1e-9
    finally:
        bm.free()


run(globals())
