import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from blendworks_bridge import land_stats
from blendworks_bridge.limits_land import BORDER_TOLERANCE, LAND_TRIANGLE_BYTES, MAX_LAND_MEMORY
from land_helpers import REGION, attribute_at, boundary_edges, drop, grid, heights, region, surface, vertices

FAST = {"detail": 16, "behind": 1.0}
RELIEF_RATIO = (0.7, 1.4)
SLOPE_MEDIAN = 2.0
SLOPE_HIGH = 4.0
WATER_SHARE = 0.07
FLAT_SHARE = 0.1
CURVATURE_TOLERANCE = 0.05
WINDOW_CELLS = 60


def land(bridge, name="DistantLand", **extra):
    return bridge.ok("distant_land", name=name, terrain=["land"], **dict(FAST, **extra))


def test_border_heights_match_within_the_tolerance(bridge):
    region(bridge)
    result = land(bridge)
    assert result["border"]["within"], result["border"]
    region_tree, _, _ = surface("land")
    land_tree, _, _ = surface("DistantLand")
    half = REGION / 2.0
    along = numpy.linspace(-half + 0.37, half - 0.41, 257)
    for inside, outside, make in ((half - 1e-3, half + 1e-3, lambda a, b: numpy.column_stack([b, a])),
                                  (-half + 1e-3, -half - 1e-3, lambda a, b: numpy.column_stack([a, b]))):
        inner = heights(region_tree, make(along, numpy.full_like(along, inside)))
        outer = heights(land_tree, make(along, numpy.full_like(along, outside)))
        gap = numpy.abs(inner - outer)
        assert numpy.nanmax(gap) <= BORDER_TOLERANCE, numpy.nanmax(gap)
        assert numpy.isnan(gap).sum() == 0
    step = 2.0
    inner = heights(region_tree, numpy.column_stack([numpy.full_like(along, half - step), along]))
    edge = heights(region_tree, numpy.column_stack([numpy.full_like(along, half - 1e-3), along]))
    outer = heights(land_tree, numpy.column_stack([numpy.full_like(along, half + step), along]))
    bend = numpy.abs((outer - edge) - (edge - inner))
    assert numpy.median(bend) < 0.25, numpy.median(bend)


def window_statistics(tree, faces, values, centre, spacing):
    points, cell = grid(centre, REGION, WINDOW_CELLS)
    z = heights(tree, points).reshape(WINDOW_CELLS, WINDOW_CELLS)
    water = attribute_at(tree, faces, values["dl_water"], points).reshape(WINDOW_CELLS, WINDOW_CELLS) >= 0.5
    return land_stats.statistics(z, cell, water)


def test_land_statistics_match_the_region(bridge):
    region(bridge, height=18.0, seed=8, scale=90.0)
    z = vertices("land")[:, 2]
    level = float(numpy.quantile(z, 0.12))
    land(bridge, water_level=level, detail=96)
    region_tree, _, _ = surface("land")
    points, cell = grid((0.0, 0.0), REGION, WINDOW_CELLS)
    region_z = heights(region_tree, points).reshape(WINDOW_CELLS, WINDOW_CELLS)
    expected = land_stats.statistics(region_z, cell, region_z < level)
    tree, faces, values = surface("DistantLand")
    reach = 1.5 * REGION
    found = [window_statistics(tree, faces, values, centre, cell)
             for centre in ((reach, 0.0), (-reach, 0.0), (0.0, reach), (0.0, -reach), (reach, reach), (-reach, -reach))]
    relief = numpy.mean([entry["relief"] for entry in found]) / expected["relief"]
    assert RELIEF_RATIO[0] <= relief <= RELIEF_RATIO[1], (relief, expected["relief"])
    median = numpy.mean([entry["slope"][1] for entry in found])
    assert abs(median - expected["slope"][1]) <= SLOPE_MEDIAN, (median, expected["slope"])
    high = numpy.mean([entry["slope"][2] for entry in found])
    assert abs(high - expected["slope"][2]) <= SLOPE_HIGH, (high, expected["slope"])
    dominant = numpy.exp(numpy.mean([numpy.log(entry["dominant_wavelength"]) for entry in found]))
    assert 0.5 <= dominant / expected["dominant_wavelength"] <= 2.0, (dominant, expected["dominant_wavelength"])
    water = numpy.mean([entry["water_share"] for entry in found])
    assert abs(water - expected["water_share"]) <= WATER_SHARE, (water, expected["water_share"])
    assert water > 0.02
    flat = numpy.mean([entry["flat_share"] for entry in found])
    assert abs(flat - expected["flat_share"]) <= FLAT_SHARE, (flat, expected["flat_share"])


def test_land_drops_by_the_curvature_of_the_earth(bridge):
    region(bridge)
    curved = land(bridge, name="Curved", earth_radius=6_371_000.0)
    land(bridge, name="Flat", curvature=False)
    bent, flat = vertices("Curved"), vertices("Flat")
    assert bent.shape == flat.shape
    reach = numpy.hypot(bent[:, 0], bent[:, 1])
    far = reach > 2000.0
    expected = numpy.array([drop(6_371_000.0, value) for value in reach[far]])
    assert numpy.abs((flat[far, 2] - bent[far, 2]) - expected).max() < CURVATURE_TOLERANCE
    at = numpy.argmin(numpy.abs(reach - 80_000.0))
    assert abs(reach[at] - 80_000.0) < 10_000.0
    assert abs((flat[at, 2] - bent[at, 2]) - drop(6_371_000.0, reach[at])) < CURVATURE_TOLERANCE
    assert curved["curvature"]["radius"] == 6_371_000.0


def test_rings_have_no_cracks_and_detail_falls_with_distance(bridge):
    region(bridge)
    result = land(bridge, detail=24)
    counts = boundary_edges("DistantLand")
    assert max(counts.values()) == 2
    open_edges = [edge for edge, count in counts.items() if count == 1]
    points = vertices("DistantLand")
    half = REGION / 2.0
    far = 100_000.0 + half
    for a, b in open_edges:
        for point in (points[a], points[b]):
            on_border = abs(max(abs(point[0]), abs(point[1])) - half) < 1e-3
            on_outside = abs(max(abs(point[0]), abs(point[1])) - far) < 0.05
            assert on_border or on_outside, point
    spacings = result["rings"]["spacings"]
    assert result["rings"]["count"] >= 8
    ratios = [later / earlier for earlier, later in zip(spacings, spacings[1:])]
    assert all(1.5 < ratio < 2.5 for ratio in ratios), spacings


def test_budgets_hold(bridge):
    region(bridge)
    small = land(bridge, name="Small", detail=64, budget=60_000)
    assert small["triangles"] <= 60_000
    assert small["budget"]["detail"] < 64
    assert small["budget"]["memory_bytes"] == small["triangles"] * LAND_TRIANGLE_BYTES
    assert len(bpy.data.objects["Small"].data.polygons) == small["triangles"]
    bridge.refuse("distant_land", "bad_args", name="Tiny", terrain=["land"], budget=2_000)
    assert "Tiny" not in bpy.data.objects
    assert MAX_LAND_MEMORY < 8 * 1024 ** 3 / 8


def test_same_seed_repeats_and_another_differs(bridge):
    region(bridge)
    land(bridge, name="First", seed=5)
    land(bridge, name="Second", seed=5)
    land(bridge, name="Other", seed=6)
    first, second, other = vertices("First"), vertices("Second"), vertices("Other")
    assert numpy.array_equal(first, second)
    assert numpy.abs(first[:, 2] - other[:, 2]).max() > 0.5


def test_ranges_rise_behind_each_other(bridge):
    region(bridge)
    result = land(bridge, name="Ranges", style="ranges", curvature=False, detail=32)
    points = vertices("Ranges")
    reach = numpy.maximum(numpy.abs(points[:, 0]), numpy.abs(points[:, 1])) - REGION / 2.0
    tops = [numpy.quantile(points[(reach > low) & (reach < high), 2], 0.95) for low, high in ((200, 1000), (3000, 6000), (12_000, 30_000))]
    assert tops[0] < tops[1] < tops[2], tops
    assert tops[2] > 400.0
    assert result["field"]["range_height"] >= 800.0


def test_ground_material_continues_the_region(bridge):
    region(bridge)
    bridge.ok("material_procedural", name="ground", grass_ground={"density": 0.7})
    bridge.ok("assign_material", name="land", material="ground")
    result = land(bridge)
    assert result["continues_material"]
    material = bpy.data.materials[result["material"]]
    names = {node.bl_idname for node in material.node_tree.nodes}
    original = {node.bl_idname for node in bpy.data.materials["ground"].node_tree.nodes}
    assert original <= names
    attributes = {node.attribute_name for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeAttribute"}
    assert {"dl_far", "dl_water"} <= attributes
    _, _, values = surface("DistantLand")
    count = result["vertices"]
    assert values["dl_far"][: count // 1000].max() < 1e-6


def test_distant_land_refuses_bad_regions(bridge):
    region(bridge)
    bridge.refuse("distant_land", "bad_args", name="A")
    bridge.refuse("distant_land", "bad_args", name="A", terrain=["land"], ground="land")
    bridge.refuse("distant_land", "bad_args", name="A", bounds={"min": [0.0, 0.0], "max": [10.0, 10.0]})
    bridge.refuse("distant_land", "bad_args", name="A", bounds={"min": [0.0, 0.0], "max": [-10.0, 10.0]}, ground="land")
    bridge.refuse("distant_land", "bad_args", name="A", terrain=["land"], distance=50_000.0)
    bridge.refuse("distant_land", "bad_args", name="A", terrain=["land"], distance=199_900.0, **FAST)


run(globals())
