import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy

from cover_helpers import attribute_of, make_plane, points_of

BUDGET = 20_000
SHORT = 110.0


def meadow_field(bridge, **extra):
    make_plane(bridge, size=100.0, cuts=4)
    bridge.ok("add_camera", name="Eye", location=[0.0, -50.0, 1.6])
    bridge.ok("look_at", name="Eye", point=[0.0, 0.0, 0.0])
    return bridge.ok("ground_cover", target="Ground", preset="meadow", camera="Eye", near=12.0, budget=BUDGET, seed=5, **extra)


def test_a_100_m_meadow_stays_within_its_instance_budget_and_keeps_full_density_near_the_camera(bridge):
    result = meadow_field(bridge)
    total = sum(len(points_of(name)) for name in result["objects"])
    assert total == result["count"] <= BUDGET
    assert total >= 0.95 * BUDGET
    assert result["surface_area"] > 9999.0
    assert result["budget_factor"] < 1.0 and result["falloff"]["near"] < 12.0
    near = result["falloff"]["near"]
    grass = points_of("GroundCover_short_grass")
    distances = numpy.linalg.norm(grass - [0.0, -50.0, 0.0], axis=1)
    inside = distances < 0.8 * near
    area = 0.5 * math.pi * (0.8 * near) ** 2
    assert abs(inside.sum() / area - SHORT) <= 0.15 * SHORT, inside.sum() / area
    ring = (distances > 4.0 * near) & (distances < 5.0 * near)
    ring_area = 0.5 * math.pi * ((5.0 * near) ** 2 - (4.0 * near) ** 2)
    expected = SHORT * (near / (4.5 * near)) ** 2
    assert abs(ring.sum() / ring_area - expected) <= 0.35 * expected, (ring.sum() / ring_area, expected)
    assert distances.max() > 60.0


def test_without_a_camera_the_budget_thins_every_population_evenly(bridge):
    make_plane(bridge, size=100.0)
    populations = [{"name": "grass", "element": "grass", "density": 40.0, "form": "cards", "variants": 1}, {"name": "stones", "element": "pebble", "density": 4.0, "form": "cards", "variants": 1}]
    result = bridge.ok("ground_cover", target="Ground", populations=populations, budget=BUDGET, seed=1)
    counts = {entry["name"]: entry["count"] for entry in result["populations"]}
    assert result["count"] <= BUDGET and result["count"] >= 0.95 * BUDGET
    assert abs(counts["grass"] / counts["stones"] - 10.0) < 1.0, counts
    assert "falloff" not in result


def test_the_same_seed_repeats_the_cover_and_another_seed_changes_it(bridge):
    make_plane(bridge, size=12.0, cuts=3)
    bridge.ok("add_primitive", type="cube", name="Rock", size=1.0, location=[2.0, 2.0, 0.3])
    settings = dict(target="Ground", preset="meadow", obstacles=["Rock"], density_scale=0.2, point=[0.0, -6.0, 1.0], near=4.0)
    bridge.ok("ground_cover", name="A", seed=3, **settings)
    bridge.ok("ground_cover", name="B", seed=3, **settings)
    bridge.ok("ground_cover", name="C", seed=4, **settings)
    for population in ("short_grass", "tall_grass", "daisies", "pebbles"):
        first, again, other = (points_of(f"{name}_{population}") for name in ("A", "B", "C"))
        assert numpy.array_equal(first, again), population
        assert numpy.array_equal(attribute_of(f"A_{population}", "gc_pick"), attribute_of(f"B_{population}", "gc_pick"))
        assert numpy.array_equal(attribute_of(f"A_{population}", "gc_transform", 16), attribute_of(f"B_{population}", "gc_transform", 16))
        assert first.shape != other.shape or not numpy.allclose(first, other), population


def test_several_cameras_keep_full_density_near_each_of_them(bridge):
    make_plane(bridge, size=60.0)
    for name, x in (("Left", -25.0), ("Right", 25.0)):
        bridge.ok("add_camera", name=name, location=[x, 0.0, 1.0])
    populations = [{"name": "grass", "element": "grass", "density": 20.0, "form": "cards", "variants": 1}]
    result = bridge.ok("ground_cover", target="Ground", populations=populations, cameras=["Left", "Right"], near=3.0, seed=2)
    assert len(result["falloff"]["centres"]) == 2
    points = points_of("GroundCover_grass")
    for x in (-25.0, 25.0):
        close = numpy.linalg.norm(points[:, :2] - [x, 0.0], axis=1) < 2.0
        assert abs(close.sum() / (math.pi * 4.0) - 20.0) < 0.2 * 20.0, (x, close.sum())
    middle = numpy.linalg.norm(points[:, :2], axis=1) < 2.0
    assert middle.sum() < 0.1 * 20.0 * math.pi * 4.0


def test_ground_cover_refuses_conflicting_or_unknown_settings(bridge):
    make_plane(bridge)
    assert "one of camera, cameras or point" in bridge.refuse("ground_cover", "bad_args", target="Ground", preset="lawn", camera="Nope", point=[0.0, 0.0, 1.0])
    assert "needs a camera" in bridge.refuse("ground_cover", "bad_args", target="Ground", preset="lawn", view_only=True)
    assert "used twice" in bridge.refuse("ground_cover", "bad_args", target="Ground", populations=[{"name": "a", "element": "grass", "density": 1.0}, {"name": "a", "element": "leaf", "density": 1.0}])
    assert "needs element and density" in bridge.refuse("ground_cover", "bad_args", target="Ground", populations=[{"name": "a", "element": "grass"}])
    assert "not a camera" in bridge.refuse("ground_cover", "bad_args", target="Ground", preset="lawn", camera="Ground")
    assert "need trees or obstacles" in bridge.refuse("ground_cover", "bad_args", target="Ground", populations=[{"name": "litter", "element": "leaf", "density": 5.0, "under": 2.0}])


run(globals())
