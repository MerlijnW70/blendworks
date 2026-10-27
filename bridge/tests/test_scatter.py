import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from scatter_helpers import (
    clearance_ratio,
    copies,
    jittered_grid,
    locations,
    make_bolt,
    make_ground,
    make_terrain,
    repetition_peak,
    scales,
    smallest_distance,
    splat,
    steepest_face,
)

SLACK = 1e-6
PLANE_AREA = 100.0
JAMMING_COVERAGE = 0.5470
COVER_BOUND = PLANE_AREA / (math.pi * 0.5**2)
EXPECTED_JAMMED = JAMMING_COVERAGE * PLANE_AREA / (math.pi * 0.25**2)
PINNED_COUNT = {1: 278, 2: 279, 3: 276}


def scatter_plane(bridge, seed=1, **extra):
    make_ground(bridge)
    make_bolt(bridge)
    return bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.5, seed=seed, **extra)


def test_instances_on_a_plane_keep_the_minimum_distance_for_every_pair(bridge):
    result = scatter_plane(bridge)
    points = locations("Scatter")
    assert len(points) == result["count"] > 200
    assert smallest_distance(points) >= 0.5 - SLACK
    assert abs(result["min_pair_distance"] - smallest_distance(points)) < 1e-6
    assert numpy.all(numpy.abs(points[:, :2]) <= 5.0 + SLACK) and numpy.allclose(points[:, 2], 0.0)


def test_spacing_holds_on_a_steep_ramp_and_on_a_terrain_tile(bridge):
    flat = scatter_plane(bridge)["count"]
    bridge.ok("add_primitive", type="plane", name="Ramp", size=10.0)
    bridge.ok("transform", name="Ramp", rotation=[60.0, 0.0, 0.0])
    ramp = bridge.ok("scatter", target="Ramp", source="Bolt", min_distance=0.5, seed=1, name="OnRamp")
    assert ramp["surface_area"] > 99.9
    assert ramp["count"] >= 0.9 * flat
    ramp_points = locations("OnRamp")
    assert smallest_distance(ramp_points) >= 0.5 - SLACK
    assert numpy.ptp(ramp_points[:, 2]) > 8.0
    make_terrain(bridge)
    assert steepest_face("Terrain") > 45.0
    tile = bridge.ok("scatter", target="Terrain", source="Bolt", min_distance=1.0, seed=3, name="OnTile")
    assert smallest_distance(locations("OnTile")) >= 1.0 - SLACK
    assert tile["count"] >= 0.85 * JAMMING_COVERAGE * tile["surface_area"] / (math.pi * 0.25)


def test_a_variable_radius_keeps_the_sum_of_the_scaled_radii_between_instances(bridge):
    make_ground(bridge)
    make_bolt(bridge)
    low, high = 0.5, 4.0
    result = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.3, scale_range=[low, high], scale_distribution="power", seed=5, align="up")
    points, sizes = locations("Scatter"), scales("Scatter")
    assert result["count"] > 20 and sizes.min() >= low - SLACK and sizes.max() <= high + SLACK and sizes.max() > 2.0 * sizes.min()
    assert clearance_ratio(points, sizes, low, 0.3) >= 1.0 - SLACK
    assert smallest_distance(points) >= 0.3 - SLACK
    assert result["min_spacing_ratio"] >= 1.0 - SLACK


def test_the_count_on_a_plane_reaches_the_maximal_packing_density_and_is_pinned(bridge):
    result = scatter_plane(bridge)
    assert result["count"] >= math.ceil(COVER_BOUND)
    assert result["count"] >= 0.95 * EXPECTED_JAMMED
    assert result["count"] == PINNED_COUNT[1]
    points = locations("Scatter")
    axis = numpy.linspace(-5.0, 5.0, 201)
    probes = numpy.array([(x, y) for x in axis for y in axis])
    nearest = numpy.min(numpy.linalg.norm(probes[:, None, :] - points[None, :, :2], axis=2), axis=1)
    assert numpy.mean(nearest > 0.5) < 0.005


def test_pinned_counts_for_other_seeds(bridge):
    make_ground(bridge)
    make_bolt(bridge)
    for seed in (2, 3):
        result = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.5, seed=seed, name=f"Seed{seed}", group=False)
        assert result["count"] == PINNED_COUNT[seed]


def test_the_top_view_splat_has_no_repetition_where_a_jittered_grid_has(bridge):
    make_ground(bridge)
    make_bolt(bridge)
    rng = numpy.random.default_rng(0)
    peaks, grid_peaks = [], []
    for seed in range(1, 5):
        bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.75, seed=seed, name=f"S{seed}", group=False)
        points = locations(f"S{seed}")
        peaks.append(repetition_peak(splat(points[:, :2], 10.0)))
        grid_peaks.append(repetition_peak(splat(jittered_grid(len(points), 10.0, 0.2, rng), 10.0)))
    assert max(peaks) <= 0.2
    assert min(grid_peaks) > 0.2
    assert repetition_peak(splat(jittered_grid(100, 10.0, 0.0, rng), 10.0)) > 0.99


def fitted_exponent(sizes, low, high):
    edges = numpy.geomspace(low, high, 9)
    counts, _ = numpy.histogram(sizes, bins=edges)
    centres = numpy.sqrt(edges[:-1] * edges[1:])
    density = counts / numpy.diff(edges)
    kept = counts > 0
    return numpy.polyfit(numpy.log(centres[kept]), numpy.log(density[kept]), 1)[0]


def test_the_power_distribution_has_the_requested_exponent(bridge):
    make_ground(bridge, size=100.0)
    make_bolt(bridge)
    for exponent in (-2.0, -1.0, -3.0):
        name = f"E{abs(int(exponent))}"
        result = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.05, density=0.22, scale_range=[1.0, 8.0], scale_distribution="power", scale_exponent=exponent, seed=7, name=name, group=False)
        sizes = scales(name)
        assert 1800 <= len(sizes) <= 2300
        assert abs(fitted_exponent(sizes, 1.0, 8.0) - exponent) <= 0.2, (exponent, fitted_exponent(sizes, 1.0, 8.0))
        assert abs(result["fitted_exponent"] - exponent) <= 0.2
    default = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.05, density=0.22, scale_range=[1.0, 8.0], scale_distribution="power", seed=8, name="D", group=False)
    assert abs(fitted_exponent(scales("D"), 1.0, 8.0) + 2.0) <= 0.2 and abs(default["fitted_exponent"] + 2.0) <= 0.2
    assert sum(entry["count"] for entry in default["size_histogram"]) == default["count"]


def instance_state(prefix):
    return numpy.array([[value for row in obj.matrix_world for value in row] for obj in copies(prefix)])


def shuffled_copy(source_name, name, seed):
    source = bpy.data.objects[source_name]
    vertices = [tuple(vertex.co) for vertex in source.data.vertices]
    faces = [tuple(polygon.vertices) for polygon in source.data.polygons]
    rng = numpy.random.default_rng(seed)
    face_order = rng.permutation(len(faces))
    vertex_order = rng.permutation(len(vertices))
    new_index = numpy.empty(len(vertices), dtype=int)
    new_index[vertex_order] = numpy.arange(len(vertices))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([vertices[index] for index in vertex_order], [], [tuple(int(new_index[v]) for v in faces[index]) for index in face_order])
    mesh.polygons.foreach_set("use_smooth", [source.data.polygons[int(index)].use_smooth for index in face_order])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = source.matrix_world
    return obj


def test_the_seed_is_deterministic_and_the_face_order_changes_nothing(bridge):
    make_terrain(bridge)
    make_bolt(bridge)
    shuffled_copy("Terrain", "Shuffled", 11)
    shuffled_copy("Terrain", "Shuffled2", 12)
    settings = dict(source="Bolt", min_distance=1.0, seed=9, density_mask=["slope"], slope_range=[0.0, 40.0], scale_range=[0.5, 2.0], scale_distribution="lognormal", tilt=10.0, group=False)
    bridge.ok("scatter", target="Terrain", name="A", **settings)
    bridge.ok("scatter", target="Terrain", name="B", **settings)
    bridge.ok("scatter", target="Shuffled", name="C", **settings)
    bridge.ok("scatter", target="Shuffled2", name="D", **settings)
    bridge.ok("scatter", target="Terrain", name="E", **{**settings, "seed": 10})
    first = instance_state("A")
    assert len(first) > 100
    for other in ("B", "C", "D"):
        assert numpy.array_equal(first, instance_state(other)), other
    assert instance_state("E").shape != first.shape or not numpy.allclose(instance_state("E"), first)


run(globals())
