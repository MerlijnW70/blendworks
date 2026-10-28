import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy

from harness import run
from kit_helpers import euler, is_closed_manifold, volume
from shell_helpers import build, main_ring, mesh_ring, middle, pairs, peaks, radius, ring_coordinates, spiral_for

STEPS = 32
POINTS_PROFILE = [[0.0, 0.0], [0.04, -0.02], [0.08, 0.0], [0.07, 0.05], [0.01, 0.06]]


def test_radius_ratio_one_whorl_apart_is_W_to_1e_9(bridge):
    for growth in (1.1, 1.7, 3.0):
        spiral = spiral_for(W=growth, D=0.3, T=0.8, turns=4.0, steps=STEPS, profile="ellipse", aspect=0.7)
        for k in range(spiral.tail, spiral.tail + 2 * STEPS, 5):
            now, later = ring_coordinates(spiral, k), ring_coordinates(spiral, k + STEPS)
            (_, z_now), (_, z_later) = middle(now), middle(later)
            for (r0, z0), (r1, z1) in zip(now, later):
                assert abs(r1 / r0 - growth) < 1e-9
                if abs(z0 - z_now) > 1e-6:
                    assert abs((z1 - z_later) / (z0 - z_now) - growth) < 1e-9
    result = build(bridge, W=1.7, D=0.3, T=0.8, turns=4.0, steps=STEPS)
    for k in (3, 20, 41):
        ratios = [radius(b) / radius(a) for a, b in zip(main_ring("S", result, k), main_ring("S", result, k + STEPS))]
        assert all(abs(ratio - 1.7) < 1e-5 for ratio in ratios), ratios


def test_D_is_the_inner_over_outer_distance_of_the_generating_curve(bridge):
    for profile, extra in (("circle", {}), ("ellipse", {"aspect": 1.8}), ("points", {"points": POINTS_PROFILE})):
        for distance in (0.1, 0.5, 0.9):
            spiral = spiral_for(W=1.5, D=distance, turns=3.0, steps=STEPS, profile=profile, **extra)
            for k in (spiral.tail, spiral.tail + 40, spiral.tail + 90):
                radials = [r for r, _ in ring_coordinates(spiral, k)]
                assert abs(min(radials) / max(radials) - distance) < 1e-9, (profile, distance)
            name = f"S{profile}{distance}"
            result = build(bridge, name=name, W=1.5, D=distance, turns=3.0, steps=STEPS, profile=profile, **extra)
            radials = [radius(p) for p in main_ring(name, result, 50)]
            assert abs(min(radials) / max(radials) - distance) < 1e-5


def test_translation_per_whorl_is_T_times_the_centre_radius(bridge):
    for drop in (0.0, 0.5, 2.0):
        spiral = spiral_for(W=1.6, D=0.25, T=drop, turns=4.0, steps=STEPS)
        for k in (spiral.tail, spiral.tail + 17, spiral.tail + 60):
            (r0, z0), (_, z1) = (middle(ring_coordinates(spiral, index)) for index in (k, k + STEPS))
            assert abs((z0 - z1) - drop * r0) < 1e-9
    result = build(bridge, W=1.6, D=0.25, T=2.0, turns=4.0, steps=STEPS)
    for k in (4, 30):
        (r0, z0), (_, z1) = (middle(pairs(main_ring("S", result, index))) for index in (k, k + STEPS))
        assert abs((z0 - z1) / r0 - 2.0) < 1e-4
        assert z1 < z0
    flat = build(bridge, name="Flat", W=1.6, D=0.25, T=0.0, turns=3.0, steps=STEPS)
    assert max(abs(middle(pairs(main_ring("Flat", flat, k)))[1]) for k in range(0, 90, 7)) < 1e-6


def test_size_is_the_final_aperture_extent(bridge):
    result = build(bridge, size=0.25, W=1.5, D=0.3, turns=3.0, steps=STEPS, profile="ellipse", aspect=0.5)
    last = mesh_ring("S", result, result["rings"] - 1)
    width = max(radius(p) for p in last) - min(radius(p) for p in last)
    height = max(p.z for p in last) - min(p.z for p in last)
    assert abs(width - 0.25) < 1e-5 and abs(height - 0.125) < 1e-5


def connected_pieces(bm):
    seen, pieces = set(), 0
    for start in bm.verts:
        if start.index in seen:
            continue
        pieces += 1
        stack = [start]
        while stack:
            vertex = stack.pop()
            if vertex.index in seen:
                continue
            seen.add(vertex.index)
            stack.extend(edge.other_vert(vertex) for edge in vertex.link_edges)
    return pieces


def test_one_closed_manifold_solid_closed_at_the_apex(bridge):
    result = build(bridge, W=1.5, D=0.3, T=1.5, turns=5.0, steps=48)
    assert result["manifold"] is True
    assert is_closed_manifold("S")
    assert euler("S") == 2
    assert volume("S") > 0
    assert abs(volume("S") - result["volume"]) < 1e-9
    bm = bmesh.new()
    bm.from_mesh(bpy.data.objects["S"].data)
    try:
        on_axis = [vertex.index for vertex in bm.verts if math.hypot(vertex.co.x, vertex.co.y) < 1e-9]
        assert connected_pieces(bm) == 1
    finally:
        bm.free()
    assert len(on_axis) == 1 and on_axis[0] < result["points_per_ring"]


def test_volume_matches_the_sum_of_wedges_about_the_axis(bridge):
    result = build(bridge, W=1.4, D=0.4, T=1.8, turns=4.0, steps=96)
    total = 0.0
    for k in range(result["rings"]):
        points = pairs(mesh_ring("S", result, k))
        for i, (x0, y0) in enumerate(points):
            x1, y1 = points[(i + 1) % len(points)]
            total += (x0 + x1) * (x0 * y1 - x1 * y0) / 6.0 * math.tau / 96
    assert abs(volume("S") / total - 1.0) < 0.02, (volume("S"), total)


def test_left_and_right_are_mirror_images(bridge):
    kwargs = dict(W=1.5, D=0.3, T=1.2, turns=4.0, steps=40, ribs={"count": 6, "height": 0.04}, lip={}, thickness=0.002, size=0.1)
    right = build(bridge, name="Right", handedness="right", **kwargs)
    left = build(bridge, name="Left", handedness="left", **kwargs)
    first, second = bpy.data.objects["Right"].data.vertices, bpy.data.objects["Left"].data.vertices
    assert len(first) == len(second)
    worst = max(max(abs(a.co.x - b.co.x), abs(a.co.y + b.co.y), abs(a.co.z - b.co.z)) for a, b in zip(first, second))
    assert worst < 1e-7
    assert max(abs(a.co.y - b.co.y) for a, b in zip(first, second)) > 1e-3
    assert right["manifold"] and left["manifold"] and is_closed_manifold("Left")
    faces = list(zip(bpy.data.objects["Right"].data.polygons, bpy.data.objects["Left"].data.polygons))
    assert all(set(a.vertices) == set(b.vertices) for a, b in faces)
    assert max(max(abs(a.normal.x - b.normal.x), abs(a.normal.y + b.normal.y), abs(a.normal.z - b.normal.z)) for a, b in faces) < 1e-3
    assert abs(volume("Right") / volume("Left") - 1.0) < 0.03


def test_right_handed_shell_winds_like_a_right_hand_screw(bridge):
    for handedness, sign in (("right", 1.0), ("left", -1.0)):
        name = f"H{handedness}"
        result = build(bridge, name=name, W=1.3, D=0.3, T=1.5, turns=4.0, steps=48, handedness=handedness)
        turned = height = 0.0
        previous = None
        for k in range(result["rings"] - 40):
            points = main_ring(name, result, k)
            centre = sum((p for p in points), points[0] * 0) / len(points)
            angle = math.atan2(centre.y, centre.x)
            if previous is not None:
                turned += (angle - previous[0] + math.pi) % math.tau - math.pi
                height += centre.z - previous[1]
            previous = (angle, centre.z)
        assert height < 0
        assert sign * turned / height > 0


def test_ribs_ridges_and_lip_follow_their_counts_and_heights(bridge):
    shape = dict(W=1.5, D=0.4, T=1.5, turns=3.0, steps=48, size=0.1)
    plain = build(bridge, name="Plain", **shape)
    ribbed = build(bridge, name="Ribbed", ribs={"count": 7, "height": 0.05}, **shape)

    def outermost(name, result, k):
        return max(radius(p) for p in main_ring(name, result, k))

    def scale(k):
        return 0.1 * 1.5 ** (k / 48 - 3.0)

    swell = [(outermost("Ribbed", ribbed, k) - outermost("Plain", plain, k)) / scale(k) for k in range(48, 96)]
    assert peaks(swell) == 7
    assert abs(max(swell) - 0.05) < 2e-3 and min(swell) > -1e-3
    ridged = build(bridge, name="Ridged", spiral_ridges={"count": 5, "height": 0.04}, **shape)
    deviation = [(a - b).length / scale(100) for a, b in zip(main_ring("Ridged", ridged, 100), main_ring("Plain", plain, 100))]
    assert peaks(deviation) == 5
    assert abs(max(deviation) - 0.04) < 2e-3
    lipped = build(bridge, name="Lipped", lip={"flare": 0.4, "length": 0.2, "thicken": 0.0}, **shape)

    def extent(name, result, k):
        ring = main_ring(name, result, k)
        return max(p.z for p in ring) - min(p.z for p in ring)

    last = plain["rings"] - 1 - plain["tail_rings"]
    assert abs(extent("Lipped", lipped, last) / extent("Plain", plain, last) - 1.4) < 1e-4
    assert abs(extent("Lipped", lipped, 100) / extent("Plain", plain, 100) - 1.0) < 1e-6


def test_result_reports_the_mesh_and_how_it_was_built(bridge):
    result = bridge.ok("shell", name="Reported", W=1.5, turns=3.0, steps=24, size=0.1, location=[1.0, 2.0, 3.0])
    assert result["name"] == "Reported" and result["manifold"] is True
    assert result["rings"] == 3 * 24 + 12 + 1 and result["tail_rings"] == 12 and result["points_per_ring"] == 24
    assert result["mesh"]["vertices"] == result["rings"] * 24
    assert [round(c, 6) for c in bpy.data.objects["Reported"].location] == [1.0, 2.0, 3.0]
    assert "wall_min" not in result


def test_refuses_what_cannot_be_built(bridge):
    assert "points" in bridge.refuse("shell", "bad_args", name="A", profile="points")
    assert "aspect" in bridge.refuse("shell", "bad_args", name="B", profile="circle", aspect=0.5)
    assert "rib" in bridge.refuse("shell", "bad_args", name="C", steps=16, ribs={"count": 8, "height": 0.05})
    assert "turns" in bridge.refuse("shell", "bad_args", name="D", W=30.0, turns=20.0)
    assert "gap" in bridge.refuse("shell", "bad_args", name="E", D=0.02, ribs={"count": 2, "height": 0.3})
    assert "multiple of 4" in bridge.refuse("shell", "bad_args", name="F", profile_segments=18)
    assert "thickness" in bridge.refuse("shell", "failed", name="G", size=0.01, thickness=0.004)
    assert not [obj for obj in bpy.data.objects if obj.name in "ABCDEFG"]


run(globals())
