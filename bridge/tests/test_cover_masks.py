import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy

from cover_helpers import make_plane, points_of, slope_at, world_tree

AREA = 400.0


def population(name, element, density, **extra):
    return {"name": name, "element": element, "density": density, "variants": 1, "form": "cards", **extra}


def test_each_population_keeps_its_density_per_square_metre(bridge):
    make_plane(bridge, size=20.0)
    result = bridge.ok("ground_cover", target="Ground", seed=3, populations=[
        population("even", "grass", 4.0),
        population("clumped", "flower", 3.0, clumping={"radius": 0.3, "per_clump": 6.0}),
        population("sparse", "pebble", 0.5, form="geometry"),
    ])
    reports = {entry["name"]: entry for entry in result["populations"]}
    for name, density, tolerance in (("even", 4.0, 0.08), ("clumped", 3.0, 0.25), ("sparse", 0.5, 0.25)):
        count = len(points_of(f"GroundCover_{name}"))
        assert count == reports[name]["count"], name
        measured = count / AREA
        assert abs(measured - density) <= tolerance * density, (name, measured, density)
        assert abs(reports[name]["mean_density"] - measured) < 1e-6
    clumped = points_of("GroundCover_clumped")[:, :2]
    even = points_of("GroundCover_even")[:, :2]
    assert nearest_gap(clumped) < 0.6 * nearest_gap(even[: len(clumped)])


def nearest_gap(points):
    gaps = numpy.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    gaps[numpy.arange(len(points)), numpy.arange(len(points))] = numpy.inf
    return float(numpy.median(gaps.min(axis=1)))


def make_ramp(bridge):
    rise = 10.0 * math.tan(math.radians(60.0))
    vertices = [[-10.0, -5.0, 0.0], [0.0, -5.0, 0.0], [0.0, 5.0, 0.0], [-10.0, 5.0, 0.0], [10.0, -5.0, rise], [10.0, 5.0, rise]]
    bridge.ok("mesh_from_data", name="Ramp", vertices=vertices, faces=[[0, 1, 2, 3], [1, 4, 5, 2]])


def test_no_grass_grows_on_faces_steeper_than_the_slope_limit(bridge):
    make_ramp(bridge)
    bridge.ok("ground_cover", target="Ramp", seed=1, populations=[population("grass", "grass", 6.0, slope=[0.0, 40.0])])
    tree = world_tree("Ramp")
    points = points_of("GroundCover_grass")
    slopes = numpy.array([slope_at(tree, point) for point in points])
    assert len(points) > 300
    assert slopes.max() <= 40.0, slopes.max()
    assert points[:, 0].max() < 0.05
    steep = bridge.ok("ground_cover", target="Ramp", name="Steep", seed=1, populations=[population("moss", "tuft", 6.0, slope=[50.0, 90.0])])
    assert points_of("Steep_moss")[:, 0].min() > -0.05 and steep["count"] > 300


def test_nothing_grows_inside_a_trunk_radius_and_litter_stays_under_the_tree(bridge):
    make_plane(bridge, size=10.0)
    bridge.ok("add_primitive", type="cylinder", name="Trunk", radius=0.3, depth=3.0, segments=32, location=[1.0, 1.0, 1.0])
    bridge.ok("ground_cover", target="Ground", seed=2, obstacles=["Trunk"], trees=["Trunk"], populations=[
        population("grass", "grass", 20.0, avoid=0.2),
        population("litter", "leaf", 10.0, under=2.0, form="geometry"),
        population("bare", "pebble", 20.0, form="geometry"),
    ])
    inscribed = 0.3 * math.cos(math.pi / 32)
    grass = numpy.linalg.norm(points_of("GroundCover_grass")[:, :2] - [1.0, 1.0], axis=1)
    litter = numpy.linalg.norm(points_of("GroundCover_litter")[:, :2] - [1.0, 1.0], axis=1)
    bare = numpy.linalg.norm(points_of("GroundCover_bare")[:, :2] - [1.0, 1.0], axis=1)
    assert len(grass) > 1000 and grass.min() >= inscribed + 0.2 - 0.01, grass.min()
    assert numpy.sum(grass < 0.8) > 5
    assert len(litter) > 50 and litter.max() <= 0.3 + 2.0 + 1e-3 and litter.min() >= inscribed - 1e-3
    assert bare.min() < inscribed, "a population without avoid ignores the trunk"


def test_height_and_attribute_masks_keep_elements_where_they_claim(bridge):
    bridge.ok("heightfield", name="Hill", size=[20.0, 20.0], resolution=41, height=4.0, scale=12.0, octaves=3, seed=5, attributes=["slope", "height"])
    heights = points_of("Hill")[:, 2]
    ceiling, floor, top = (float(numpy.quantile(heights, share)) for share in (0.4, 0.6, 0.8))
    bridge.ok("ground_cover", target="Hill", seed=4, populations=[
        population("low", "grass", 6.0, height_range=[-100.0, ceiling], height_edge=0.2),
        population("high", "tuft", 6.0, attribute={"name": "height", "range": [floor, top]}),
    ])
    low = points_of("GroundCover_low")
    assert len(low) > 100 and low[:, 2].max() <= ceiling + 0.05
    high = points_of("GroundCover_high")
    assert len(high) > 100 and high[:, 2].min() >= floor - 0.05, (high[:, 2].min(), floor)
    assert numpy.mean(high[:, 2] < top) < 0.5


def test_noise_makes_patches_and_masks_that_remove_everything_are_refused(bridge):
    make_plane(bridge, size=20.0)
    result = bridge.ok("ground_cover", target="Ground", seed=1, populations=[population("patchy", "grass", 4.0, noise={"scale": 6.0, "threshold": 0.5, "softness": 0.1})])
    assert 0.2 * 4.0 * AREA < result["count"] < 0.8 * 4.0 * AREA
    message = bridge.refuse("ground_cover", "bad_args", target="Ground", name="None", populations=[population("cliff", "grass", 4.0, slope=[60.0, 90.0])])
    assert "no element fits" in message


run(globals())
