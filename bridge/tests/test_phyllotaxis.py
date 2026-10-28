import collections
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run

from blendworks_bridge.commands.placement import PHYLLOTAXIS
from blendworks_bridge.phyllotaxis import GOLDEN_DEGREES, curve_value, phyllotaxis_layout
from blendworks_bridge.schema import validate
from blendworks_bridge.util import get_mesh_object

GOLDEN_EXACT = 360.0 * (1.0 - 2.0 / (1.0 + math.sqrt(5.0)))


def layout(raw, align="frame", target=None):
    return phyllotaxis_layout(validate(PHYLLOTAXIS, raw), align, target)


def seed(bridge):
    bridge.ok("add_primitive", type="cube", name="Seed", size=0.01)


def copies(name):
    return sorted((obj for obj in bpy.data.objects if obj.name.startswith(f"{name}_")), key=lambda obj: obj.name)


def location(obj):
    return list(obj.matrix_world.translation)


def axis(obj, column):
    return list(obj.matrix_world.to_3x3().col[column].normalized())


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def wrapped(angle):
    return (angle + math.pi) % math.tau - math.pi


def nearest_differences(points, lo, hi, neighbours):
    found = collections.Counter()
    for n in range(lo, hi):
        ranked = sorted((math.dist(points[n], points[m]), m) for m in range(len(points)) if m != n)[:neighbours]
        for _, m in ranked:
            found[abs(m - n)] += 1
    return [difference for difference, _ in found.most_common(2)]


def test_disc_angles_and_radii_follow_vogel_to_1e_9(bridge):
    sites = layout({"count": 400, "c": 0.013, "divergence": 137.5}).sites
    for n, site in enumerate(sites):
        assert abs(site.r - 0.013 * math.sqrt(n)) < 1e-9
    for first, second in zip(sites[1:], sites[2:]):
        assert abs(wrapped(second.azimuth - first.azimuth - math.radians(137.5))) < 1e-9
    shifted = layout({"count": 5, "c": 0.5, "divergence": 100.0, "start": 7}).sites
    assert [round(site.r, 12) for site in shifted] == [round(0.5 * math.sqrt(n), 12) for n in range(7, 12)]
    assert abs(shifted[0].azimuth - math.radians(700.0)) < 1e-9


def test_disc_through_the_command_places_the_instances_there(bridge):
    seed(bridge)
    result = bridge.ok("instances", source="Seed", name="Head", phyllotaxis={"count": 50, "c": 0.02})
    assert result["count"] == 50 and result["phyllotaxis"]["divergence"] == 137.5
    for n, obj in enumerate(copies("Head")):
        radius, angle = 0.02 * math.sqrt(n), math.radians(137.5 * n)
        close(location(obj), [radius * math.cos(angle), radius * math.sin(angle), 0.0], 1e-5)
        close(axis(obj, 2), [0.0, 0.0, 1.0], 1e-6)


def test_golden_uses_the_exact_golden_angle(bridge):
    assert abs(GOLDEN_DEGREES - GOLDEN_EXACT) < 1e-12 and abs(GOLDEN_EXACT - 137.50776405003785) < 1e-9
    sites = layout({"count": 30, "c": 1.0, "golden": True}).sites
    for first, second in zip(sites, sites[1:]):
        assert abs(wrapped(second.azimuth - first.azimuth - math.radians(GOLDEN_EXACT))) < 1e-9
    plain = layout({"count": 30, "c": 1.0}).sites
    assert abs(plain[29].azimuth - sites[29].azimuth) > 1e-4
    seed(bridge)
    bridge.refuse("instances", "bad_args", source="Seed", name="X", phyllotaxis={"count": 3, "c": 1.0, "golden": True, "divergence": 137.5})


def test_golden_disc_shows_consecutive_fibonacci_parastichies(bridge):
    sites = layout({"count": 1000, "c": 1.0, "golden": True}).sites
    points = [(site.r * math.cos(site.azimuth), site.r * math.sin(site.azimuth)) for site in sites]
    fibonacci = {21, 34, 55, 89}
    assert sorted(nearest_differences(points, 100, 200, 4)) == [21, 34]
    assert sorted(nearest_differences(points, 300, 400, 4)) == [34, 55]
    assert sorted(nearest_differences(points, 700, 800, 4)) == [55, 89]
    for lo in (150, 350, 750):
        assert set(nearest_differences(points, lo, lo + 50, 4)) <= fibonacci
    rotated = layout({"count": 1000, "c": 1.0, "divergence": 99.5}).sites
    rotated_points = [(site.r * math.cos(site.azimuth), site.r * math.sin(site.azimuth)) for site in rotated]
    assert not set(nearest_differences(rotated_points, 300, 400, 4)) <= fibonacci
    rough = layout({"count": 1000, "c": 1.0, "divergence": 137.5}).sites
    rough_points = [(site.r * math.cos(site.azimuth), site.r * math.sin(site.azimuth)) for site in rough]
    assert sorted(nearest_differences(rough_points, 300, 400, 4)) == [34, 55]


def test_expected_parastichy_pair_brackets_the_square_lattice_index(bridge):
    sites = layout({"count": 1000, "c": 1.0, "golden": True}).sites
    points = [(site.r * math.cos(site.azimuth), site.r * math.sin(site.azimuth)) for site in sites]
    fibonacci = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]
    for lo in (120, 330, 560, 760):
        middle = lo + 25
        square = math.sqrt(4.0 * math.pi * middle / math.sqrt(5.0))
        below = max(f for f in fibonacci if f <= square)
        above = min(f for f in fibonacci if f > square)
        assert sorted(nearest_differences(points, lo, lo + 50, 4)) == [below, above], (lo, square)


def test_cone_organs_have_the_same_area_each(bridge):
    spec = {"count": 300, "mode": "cone", "radius": 0.5, "height": 1.2, "golden": True}
    result = layout(spec)
    slant = math.hypot(0.5, 1.2)
    sector = math.tau * 0.5 / slant
    distances = [math.hypot(site.r, site.z - 1.2) for site in result.sites]
    areas = [sector / 2.0 * (b * b - a * a) for a, b in zip(distances, distances[1:])]
    for area in areas:
        assert abs(area / result.summary["area_per_organ"] - 1.0) < 1e-9
    assert distances[-1] < slant and distances[-1] > 0.99 * slant
    for site in result.sites:
        assert abs(site.r / 0.5 - (1.2 - site.z) / 1.2) < 1e-9
        assert abs(site.normal[0] * site.tangent[0] + site.normal[1] * site.tangent[1]) < 1e-12
    seed(bridge)
    bridge.refuse("instances", "bad_args", source="Seed", name="X", phyllotaxis={"count": 400, "mode": "cone", "radius": 0.5, "height": 1.2, "c": 0.1})


def test_sphere_organs_have_the_same_area_each(bridge):
    for extent in (180.0, 120.0):
        result = layout({"count": 500, "mode": "sphere", "radius": 2.0, "golden": True, "polar_extent": extent})
        drops = [2.0 * math.pi * 2.0 * (a.z - b.z) for a, b in zip(result.sites, result.sites[1:])]
        for area in drops:
            assert abs(area / result.summary["area_per_organ"] - 1.0) < 1e-9
        total = 2.0 * math.pi * 4.0 * (1.0 - math.cos(math.radians(extent)))
        assert abs(result.summary["area_per_organ"] * 500 - total) < 1e-9
        assert all(abs(math.hypot(site.r, site.z) - 2.0) < 1e-9 for site in result.sites)
    points = [(site.r * math.cos(site.azimuth), site.r * math.sin(site.azimuth), site.z) for site in layout({"count": 500, "mode": "sphere", "radius": 1.0, "golden": True}).sites]
    nearest = [min(math.dist(a, b) for b in points if b is not a) for a in points]
    ideal = math.sqrt(4.0 * math.pi / 500)
    assert min(nearest) > 0.7 * ideal and max(nearest) < 1.35 * ideal


def test_cylinder_has_constant_radius_and_height_growing_linearly(bridge):
    result = layout({"count": 11, "mode": "cylinder", "radius": 0.3, "height": 2.0})
    for n, site in enumerate(result.sites):
        assert site.r == 0.3 and abs(site.z - 0.2 * n) < 1e-12
    assert abs(result.summary["area_per_organ"] - math.tau * 0.3 * 0.2) < 1e-12
    seed_start = layout({"count": 3, "mode": "cylinder", "radius": 0.3, "height": 1.0, "start": 40}).sites
    assert [site.z for site in seed_start] == [0.0, 0.5, 1.0]
    assert abs(seed_start[1].azimuth - math.radians(137.5 * 41)) < 1e-9


def test_surface_places_organs_on_a_mesh_of_revolution_in_equal_areas(bridge):
    bridge.ok("add_primitive", type="sphere", name="Bud", radius=1.0, segments=64, rings=48, location=[2.0, 1.0, 0.5])
    seed(bridge)
    result = bridge.ok("instances", source="Seed", name="Scales", phyllotaxis={"mode": "surface", "target": "Bud", "count": 200, "golden": True})
    assert abs(result["phyllotaxis"]["area_per_organ"] * 200 / (4.0 * math.pi) - 1.0) < 0.01
    scales = copies("Scales")
    assert len(scales) == 200
    for obj in scales:
        offset = [a - b for a, b in zip(location(obj), [2.0, 1.0, 0.5])]
        assert abs(math.sqrt(dot(offset, offset)) - 1.0) < 0.01
        assert dot(axis(obj, 2), [v / math.sqrt(dot(offset, offset)) for v in offset]) > 0.99
    heights = [location(obj)[2] - 0.5 for obj in scales]
    assert all(a > b for a, b in zip(heights, heights[1:]))
    close(heights, [1.0 - 2.0 * (index + 0.5) / 200 for index in range(200)], 0.01)
    bridge.ok("transform", name="Bud", scale=[1.0, 1.0, 2.0])
    bridge.refuse("instances", "bad_args", source="Seed", name="Squashed", phyllotaxis={"mode": "surface", "target": "Bud", "count": 5})


def test_surface_follows_a_turned_target_in_the_world(bridge):
    bridge.ok("add_primitive", type="cone", name="Spire", radius=0.5, depth=1.0, segments=48, location=[0, 0, 0])
    bridge.ok("transform", name="Spire", rotation=[90.0, 0.0, 0.0])
    seed(bridge)
    bridge.ok("instances", source="Seed", name="Studs", phyllotaxis={"mode": "surface", "target": "Spire", "count": 60})
    for obj in copies("Studs"):
        x, y, z = location(obj)
        assert abs(math.hypot(x, z) - 0.5 * (y + 0.5)) < 0.01
        assert -0.5 - 1e-4 <= y <= 0.5 + 1e-4


def test_scale_and_tilt_by_age_follow_their_curves(bridge):
    seed(bridge)
    count = 21
    for curve in ("linear", "ease_in", "ease_out", "smooth"):
        name = f"Age{curve}"
        bridge.ok(
            "instances",
            source="Seed",
            name=name,
            phyllotaxis={
                "count": count,
                "c": 0.03,
                "scale_by_age": {"from": 0.5, "to": 2.5, "curve": curve},
                "tilt_by_age": {"from": 0.0, "to": 80.0, "curve": curve},
            },
        )
        for index, obj in enumerate(copies(name)):
            fraction = curve_value(curve, index / (count - 1))
            close(obj.matrix_world.to_scale()[0], 0.5 + 2.0 * fraction, 1e-5)
            tilt = math.degrees(math.acos(max(-1.0, min(1.0, axis(obj, 2)[2]))))
            close(tilt, 80.0 * fraction, 1e-3)
            radial = [math.cos(math.radians(137.5 * index)), math.sin(math.radians(137.5 * index))]
            if index:
                assert dot(axis(obj, 2)[:2], radial) < 0
    assert curve_value("linear", 0.5) == 0.5 and curve_value("ease_in", 0.5) == 0.25
    assert curve_value("ease_out", 0.5) == 0.75 and curve_value("smooth", 0.5) == 0.5


def test_tilt_lifts_the_x_axis_towards_the_normal_on_a_cone(bridge):
    seed(bridge)
    bridge.ok("instances", source="Seed", name="Scales", phyllotaxis={"count": 12, "mode": "cone", "radius": 0.4, "height": 0.9, "tilt_by_age": {"from": 0.0, "to": 60.0}})
    slant = math.hypot(0.4, 0.9)
    for index, obj in enumerate(copies("Scales")):
        x, y, z = location(obj)
        angle = math.atan2(y, x)
        slope = [0.4 / slant * math.cos(angle), 0.4 / slant * math.sin(angle), -0.9 / slant]
        normal = [0.9 / slant * math.cos(angle), 0.9 / slant * math.sin(angle), 0.4 / slant]
        lift = math.radians(60.0 * index / 11)
        close(dot(axis(obj, 0), slope), math.cos(lift), 1e-5)
        close(dot(axis(obj, 0), normal), math.sin(lift), 1e-5)


def test_align_radial_keeps_z_up_and_x_away_from_the_axis(bridge):
    seed(bridge)
    bridge.ok("instances", source="Seed", name="Leaves", phyllotaxis={"count": 9, "mode": "cylinder", "radius": 0.2, "height": 1.0}, align="radial")
    for obj in copies("Leaves"):
        x, y, _ = location(obj)
        close(axis(obj, 2), [0.0, 0.0, 1.0], 1e-6)
        close(axis(obj, 0), [x / 0.2, y / 0.2, 0.0], 1e-5)
    bridge.ok("instances", source="Seed", name="Plain", phyllotaxis={"count": 4, "c": 0.1}, align="none")
    close(axis(copies("Plain")[2], 0), [1.0, 0.0, 0.0], 1e-6)
    bridge.refuse("instances", "bad_args", source="Seed", name="Flat", phyllotaxis={"count": 4, "c": 0.1, "tilt_by_age": {"from": 0, "to": 30}}, align="none")
    bridge.refuse("instances", "bad_args", source="Seed", name="Bad", points=[[0, 0, 0]], align="radial")


def test_without_jitter_every_run_is_identical_and_with_a_seed_it_repeats(bridge):
    seed(bridge)
    spec = {"count": 80, "mode": "sphere", "radius": 0.5, "golden": True, "scale_by_age": {"from": 0.4, "to": 1.0}, "tilt_by_age": {"from": 5.0, "to": 70.0}}

    def positions(name, raw):
        bridge.ok("instances", source="Seed", name=name, phyllotaxis=raw)
        return [[round(value, 7) for row in obj.matrix_world for value in row] for obj in copies(name)]

    assert positions("A", spec) == positions("B", spec)
    jittered = {**spec, "jitter": {"amount": 0.4, "rotation": 30.0, "scale": 0.2, "seed": 5}}
    first = positions("C", jittered)
    assert first == positions("D", jittered)
    assert first != positions("E", spec)
    assert first != positions("F", {**spec, "jitter": {**jittered["jitter"], "seed": 6}})
    plain = layout(spec).sites
    shifted = layout(jittered)
    spacing = math.sqrt(shifted.summary["area_per_organ"])
    for index, matrix in enumerate(shifted.placements):
        site = plain[index]
        home = [site.r * math.cos(site.azimuth), site.r * math.sin(site.azimuth), site.z]
        assert math.dist(list(matrix.translation), home) <= 0.4 * spacing * math.sqrt(2.0) + 1e-6


def test_phyllotaxis_respects_the_mode_rules_and_the_instance_limit(bridge):
    seed(bridge)
    for spec in (
        {"count": 5},
        {"count": 5, "c": 0.1, "radius": 0.1},
        {"count": 5, "mode": "cylinder", "radius": 0.1},
        {"count": 5, "mode": "sphere", "radius": 0.1, "c": 0.1},
        {"count": 5, "mode": "surface"},
        {"count": 5, "c": 0.1, "target": "Seed"},
    ):
        bridge.refuse("instances", "bad_args", source="Seed", name="Bad", phyllotaxis=spec)
    bridge.refuse("instances", "bad_args", source="Seed", name="Bad", phyllotaxis={"count": 20001, "c": 0.1})
    bridge.refuse("instances", "bad_args", source="Seed", name="Bad", phyllotaxis={"count": 5, "c": 0.1}, count=3)
    bridge.refuse("instances", "bad_args", source="Seed", name="Bad", phyllotaxis={"count": 5, "c": 0.1}, points=[[0, 0, 0]])
    merged = bridge.ok("instances", source="Seed", name="Merged", phyllotaxis={"count": 100, "c": 0.01}, realize=True)
    assert merged["realized"] is True and merged["mesh"]["vertices"] == 800
    assert get_mesh_object("Merged") is not None


run(globals())
