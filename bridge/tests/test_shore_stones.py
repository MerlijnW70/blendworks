import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from liquid_helpers import dimple, mesh_points

from blendworks_bridge import liquid_world, stone_plan, stone_shape
from blendworks_bridge.handler import Context

RADIUS, CURVATURE, SIZE = 3.0, 6.0, 40.0
SHORE, SHALLOWS = 2.0, 0.3
SIZE_RANGE = [0.06, 0.45]
GROUP = 0.4
CLUSTERED = 0.75
CONTROL_AT_LEAST = 0.9
SPACING_VARIATION = 0.25
ROUND_RANGE = (0.1, 0.85)
ROUND_GAIN = 0.06
SPHERE_AT_LEAST = 0.9
BOX_AT_MOST = 0.2
LOG_CENTRE_TOLERANCE = 0.2
LOG_DEVIATION = (0.3, 0.55)
SORTING_AT_MOST = 0.8


def pond(bridge, name="Ground"):
    dimple(name, SIZE, 200, RADIUS, CURVATURE)
    bridge.ok("add_material", name="Grey", base_color=[0.3, 0.3, 0.28], roughness=0.8)
    bridge.ok("assign_material", name=name, material="Grey")
    return bridge.ok("liquid_body", kind="pond", ground=[name], point=[0.0, 0.0, 0.0], name="Pond")


def band_area(water):
    """Plan area of the shore band, found on a grid of 0.1 m over the middle of the ground, point by point: where the ground
    lies within SHORE metres of the water above its line or SHALLOWS metres under it (the dimple's height is
    z = (r^2 - R^2) / (2 c) inside radius R and 0 outside)."""
    axis = np.arange(-9.0, 9.0, 0.1) + 0.05
    x, y = np.meshgrid(axis, axis)
    z = np.minimum((x**2 + y**2 - RADIUS**2) / (2.0 * CURVATURE), 0.0)
    points = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    depth = liquid_world.Water(liquid_world.liquid_objects(bpy.context.scene)).signed_depth(points, 6.0)
    return float(((depth >= -SHORE) & (depth <= SHALLOWS)).sum() * 0.01)


def nearest_distances(points):
    gaps = np.linalg.norm(points[:, None, :2] - points[None, :, :2], axis=2)
    np.fill_diagonal(gaps, np.inf)
    return gaps.min(axis=1)


def index_of(points, area):
    """Clark and Evans (1954), written out here from the definition: mean nearest-neighbour distance over 0.5 / sqrt(density)."""
    return nearest_distances(points).mean() / (0.5 / math.sqrt(len(points) / area))


def positions(result):
    return np.array([stone["position"] for stone in result["stones"]])


def test_shore_stones_lie_in_groups_with_irregular_spacing_not_in_rows(bridge):
    water = pond(bridge)
    result = bridge.ok("shore_stones", target="Ground", shore_width=SHORE, shore_depth=SHALLOWS, cluster_density=0.1, cluster_radius=GROUP, size_range=SIZE_RANGE, seed=3)
    assert result["count"] > 25 and result["clusters"] > 5
    area = band_area(water)
    assert abs(result["band_area"] - area) < 0.08 * area, (result["band_area"], area)
    points = positions(result)
    clustered = index_of(points, area)
    assert clustered < CLUSTERED, clustered
    assert abs(clustered - result["nearest_neighbour_index"]) < 0.08 * clustered
    nearest = nearest_distances(points)
    assert nearest.std() / nearest.mean() > SPACING_VARIATION, "spacing varies: no lattice, no string of pearls"
    sizes = np.array([stone["size"] for stone in result["stones"]])
    assert sizes.min() >= SIZE_RANGE[0] - 1e-6 and sizes.max() <= SIZE_RANGE[1] + 1e-6
    bridge.ok("delete", names=result["objects"])
    spread = bridge.ok("shore_stones", target="Ground", name="Spread", shore_width=SHORE, shore_depth=SHALLOWS, cluster_density=0.1, cluster_radius=40.0, size_range=SIZE_RANGE, seed=3)
    assert index_of(positions(spread), area) > CONTROL_AT_LEAST, "without groups the pattern is random or more regular, never clustered"


def test_a_poisson_disk_scatter_of_stones_is_regular_where_shore_stones_cluster(bridge):
    """What the old rows were: the index of a Poisson-disk scatter over the same band sits above 1, clustered stones far below."""
    water = pond(bridge)
    area = band_area(water)
    bridge.ok("add_primitive", type="ico_sphere", name="Rock", radius=0.1, subdivisions=1)
    scattered = bridge.ok("scatter", target="Ground", source="Rock", min_distance=0.8, density_mask=["shore"], shore_width=SHORE, shore_depth=SHALLOWS, name="Rows", realize=True, seed=2, shore_wet=0.0)
    count = scattered["count"]
    assert count > 60
    rows = mesh_points("Rows")
    owner = np.repeat(np.arange(count), len(rows) // count)
    centres = np.array([rows[owner == index].mean(axis=0) for index in range(count)])
    assert index_of(centres, area) > 1.0
    result = bridge.ok("shore_stones", target="Ground", shore_width=SHORE, shore_depth=SHALLOWS, cluster_density=0.1, cluster_radius=GROUP, size_range=SIZE_RANGE, seed=3)
    assert result["nearest_neighbour_index"] < CLUSTERED


def test_stone_sizes_follow_the_stated_lognormal_and_groups_are_sorted(bridge):
    pond(bridge)
    result = bridge.ok("shore_stones", target="Ground", shore_width=SHORE, shore_depth=SHALLOWS, cluster_density=0.25, cluster_radius=GROUP, size_range=SIZE_RANGE, sorting=0.7, seed=5)
    sizes = np.array([stone["size"] for stone in result["stones"]])
    groups = np.array([stone["group"] for stone in result["stones"]])
    logs = np.log(sizes)
    centre = 0.5 * (math.log(SIZE_RANGE[0]) + math.log(SIZE_RANGE[1]))
    assert abs(logs.mean() - centre) < LOG_CENTRE_TOLERANCE, (logs.mean(), centre)
    assert LOG_DEVIATION[0] < logs.std() < LOG_DEVIATION[1], logs.std()
    assert result["size"]["distribution"] == "lognormal"
    within = np.mean([logs[groups == group].var() for group in np.unique(groups) if (groups == group).sum() > 2])
    assert within < SORTING_AT_MOST * logs.var(), (within, logs.var())
    unsorted = bridge.ok("shore_stones", target="Ground", name="Mixed", shore_width=SHORE, shore_depth=SHALLOWS, cluster_density=0.25, cluster_radius=GROUP, size_range=SIZE_RANGE, sorting=0.0, seed=5)
    mixed = np.log([stone["size"] for stone in unsorted["stones"]])
    mixed_groups = np.array([stone["group"] for stone in unsorted["stones"]])
    mixed_within = np.mean([mixed[mixed_groups == group].var() for group in np.unique(mixed_groups) if (mixed_groups == group).sum() > 2])
    assert mixed_within > within, "sorting=0 mixes sizes within a group"


def test_stones_stand_partly_buried_and_partly_in_the_shallows(bridge):
    pond(bridge)
    result = bridge.ok("shore_stones", target="Ground", shore_width=SHORE, shore_depth=SHALLOWS, cluster_density=0.2, cluster_radius=GROUP, burial=[0.2, 0.5], seed=7)
    stones = result["stones"]
    assert 0.2 <= result["burial"][0] and result["burial"][1] <= 0.5
    levels = np.array([stone["height_above_water"] for stone in stones])
    assert (levels < 0.0).sum() >= 3 and (levels > 0.5).sum() >= 10, "some stones stand in the shallows, others on the bank"
    water = liquid_world.Water(liquid_world.liquid_objects(bpy.context.scene))
    ground = bpy.data.objects["Ground"]
    under, sunk = 0, 0
    for name in result["objects"]:
        points = mesh_points(name)
        depth = water.signed_depth(points, 5.0)
        under += int(((depth > 0.0).any()) and ((depth < 0.0).any()))
        floor = np.array([ground_height(ground, point) for point in points[::7]])
        sunk += int((points[::7, 2] < floor - 0.005).sum())
    assert under >= 1, "a mesh of stones holds some that stand half in the water"
    assert sunk > 50, "vertices lie below the ground: the stones are partly buried"


def ground_height(obj, point):
    from mathutils import Vector

    local = obj.matrix_world.inverted() @ Vector((point[0], point[1], 100.0))
    hit = obj.ray_cast(local, Vector((0.0, 0.0, -1.0)))
    return hit[1][2] if hit[0] else -math.inf


def test_stones_run_from_angular_to_round_by_how_far_water_moved_them(bridge):
    pond(bridge)
    result = bridge.ok("shore_stones", target="Ground", shore_width=SHORE, shore_depth=SHALLOWS, cluster_density=0.25, cluster_radius=GROUP, size_range=SIZE_RANGE, classes=4, variants=2, worked_distance=0.8, seed=11)
    roundness = result["roundness"]
    assert ROUND_RANGE[0] < min(roundness) and max(roundness) < ROUND_RANGE[1], roundness
    classes = result["class_roundness"]
    assert classes[1] - classes[0] > ROUND_GAIN and max(classes[1:]) - classes[0] > 1.5 * ROUND_GAIN, classes
    stones = result["stones"]
    near = [stone["class"] for stone in stones if stone["height_above_water"] < 0.3]
    far = [stone["class"] for stone in stones if stone["height_above_water"] > 1.2]
    assert len(near) > 10 and len(far) > 10
    assert np.mean(near) - np.mean(far) > 0.8, (np.mean(near), np.mean(far))
    assert max(result["class_counts"]) < 0.8 * result["count"], "every class is used"


def test_the_roundness_measure_reads_a_sphere_round_and_a_box_angular(bridge):
    context = Context(bridge.handler, None)
    for name, kind, expected in (("Disc", "cylinder", "round"), ("Box", "cube", "angular")):
        bridge.ok("add_primitive", type=kind, name=name, **({"segments": 256} if kind == "cylinder" else {}))
        points, _ = stone_shape.mesh_arrays(bpy.data.objects[name])
        value = stone_shape.roundness(points)
        assert (value > SPHERE_AT_LEAST) if expected == "round" else (value < BOX_AT_MOST), (name, value)
    fresh, _, _ = stone_shape.build_stone(context, "Fresh", 0.0, 4)
    worked, _, _ = stone_shape.build_stone(context, "Worked", 1.0, 4)
    fresh_value = stone_shape.roundness(stone_shape.mesh_arrays(fresh)[0])
    worked_value = stone_shape.roundness(stone_shape.mesh_arrays(worked)[0])
    assert worked_value - fresh_value > ROUND_GAIN, (fresh_value, worked_value)
    assert fresh_value > 0.0 and fresh.data.vertices and len(fresh.data.polygons) > 20
    ratio = [float(value) for value in worked.dimensions]
    assert max(ratio) == 1.0 or abs(max(ratio) - 1.0) < 1e-5, "a stone's longest side is one metre before it is sized"


def test_stones_are_not_eggs_their_shapes_differ_in_proportion(bridge):
    context = Context(bridge.handler, None)
    flatness = []
    for seed in range(8):
        stone, _, _ = stone_shape.build_stone(context, f"Stone{seed}", 0.5, seed)
        flatness.append(sorted(float(value) for value in stone.dimensions))
    ratios = np.array([[row[0] / row[2], row[1] / row[2]] for row in flatness])
    assert np.ptp(ratios[:, 0]) > 0.15 and np.ptp(ratios[:, 1]) > 0.08, ratios


def test_shore_stones_refuse_what_cannot_be_placed(bridge):
    dimple("Ground", SIZE, 40, RADIUS, CURVATURE)
    assert "needs water" in bridge.refuse("shore_stones", "bad_args", target="Ground")
    bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[0.0, 0.0, 0.0], name="Pond")
    assert "smallest, largest" in bridge.refuse("shore_stones", "bad_args", target="Ground", size_range=[0.5, 0.1])
    assert "32 times" in bridge.refuse("shore_stones", "bad_args", target="Ground", size_distribution="power", size_range=[0.01, 1.0])
    assert "meshes" in bridge.refuse("shore_stones", "bad_args", target="Ground", classes=8, variants=8)
    bridge.refuse("shore_stones", "not_found", target="Nowhere")
    assert not [name for name in bpy.data.objects.keys() if name.startswith("ShoreStones")]


def test_clark_evans_reads_random_one_a_lattice_high_and_clumps_low(bridge):
    rng = np.random.default_rng(1)
    area = 100.0
    random = rng.uniform(0.0, 10.0, (400, 2))
    assert 0.85 < stone_plan.clark_evans(random, area) < 1.15
    lattice = np.array([(x + 0.5, y + 0.5) for x in range(20) for y in range(20)]) * 0.5
    assert stone_plan.clark_evans(lattice, 100.0) > 1.9
    centres = rng.uniform(0.0, 10.0, (20, 2))
    clumps = np.repeat(centres, 20, axis=0) + rng.normal(0.0, 0.2, (400, 2))
    assert stone_plan.clark_evans(clumps, area) < 0.4


run(globals())
