import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run

import bpy
import numpy

from blendworks_bridge.noise_stack import stack_field
from noise_helpers import grid_plane, world_points

AMPLITUDE = 0.4
STACK = {"basis": "perlin", "scale": 3.0, "octaves": 4, "lacunarity": 2.0, "hurst": 0.7, "mode": "fbm", "ridge_offset": 1.0, "warp": 0.0, "warp_octaves": 2}


def heights_on_grid(name, spacing):
    points = world_points(name)
    order = numpy.lexsort((points[:, 1], points[:, 0]))
    side = int(round(math.sqrt(len(points))))
    return points[order][:, 2].reshape(side, side)


def structure_slope(bridge, hurst, seeds):
    scale = 1024.0
    octaves = math.ceil(math.log2(scale / 1.0)) + 1
    lags = numpy.array([2, 3, 4, 6, 8, 12, 16, 24, 32])
    total = numpy.zeros(len(lags))
    for seed in seeds:
        name = f"Plane{hurst}_{seed}"
        grid_plane(name, 200.0, 200)
        bridge.ok("noise_displace", name=name, amplitude=1.0, seed=seed, scale=scale, octaves=octaves, hurst=hurst, direction="z")
        field = heights_on_grid(name, 1.0)
        for index, lag in enumerate(lags):
            total[index] += numpy.mean((field[lag:, :] - field[:-lag, :]) ** 2) + numpy.mean((field[:, lag:] - field[:, :-lag]) ** 2)
    return numpy.polyfit(numpy.log(lags), numpy.log(total), 1)[0]


def test_the_structure_function_grows_as_lag_to_the_two_hurst(bridge):
    for hurst in (0.5, 0.8):
        slope = structure_slope(bridge, hurst, range(1, 7))
        assert abs(slope - 2 * hurst) <= 0.15, (hurst, slope)


def test_the_slope_test_can_tell_two_hurst_exponents_apart(bridge):
    rough = structure_slope(bridge, 0.5, range(1, 4))
    smooth = structure_slope(bridge, 0.8, range(1, 4))
    assert smooth - rough > 0.4


def test_no_vertex_moves_more_than_the_amplitude_and_the_reply_reports_it(bridge):
    results = {}
    for index, mode in enumerate(("fbm", "ridged", "billow")):
        name = f"Sheet{index}"
        grid_plane(name, 40.0, 120)
        results[name] = bridge.ok("noise_displace", name=name, amplitude=AMPLITUDE, seed=3, mode=mode, octaves=6, warp=2.0, scale=5.0, ridge_offset=0.7)
        z = world_points(name)[:, 2]
        assert numpy.max(numpy.abs(z)) <= AMPLITUDE + 1e-7, mode
        reply = results[name]
        assert reply["displaced_vertices"] == 121 * 121
        close(reply["max_displacement"], float(numpy.max(numpy.abs(z))), 1e-8)
        close(reply["height_range"], [float(z.min()), float(z.max())], 1e-8)
        assert numpy.max(numpy.abs(z)) > AMPLITUDE * 0.3, mode
    assert results["Sheet0"]["height_range"][0] < 0 < results["Sheet0"]["height_range"][1]
    assert results["Sheet2"]["height_range"][0] >= 0.0


def test_the_same_seed_repeats_and_another_seed_differs(bridge):
    for name in ("A", "B", "C"):
        grid_plane(name, 10.0, 30)
    bridge.ok("noise_displace", name="A", amplitude=AMPLITUDE, seed=21, scale=2.0)
    bridge.ok("noise_displace", name="B", amplitude=AMPLITUDE, seed=21, scale=2.0)
    bridge.ok("noise_displace", name="C", amplitude=AMPLITUDE, seed=22, scale=2.0)
    first, again, other = (world_points(name) for name in "ABC")
    assert numpy.array_equal(first, again)
    assert numpy.max(numpy.abs(first[:, 2] - other[:, 2])) > 0.1


def test_shuffling_the_vertex_order_changes_nothing(bridge):
    points = numpy.array([(x, y, 0.0) for x in range(9) for y in range(9)], dtype=float)
    faces = [[x * 9 + y, (x + 1) * 9 + y, (x + 1) * 9 + y + 1, x * 9 + y + 1] for x in range(8) for y in range(8)]
    order = numpy.random.default_rng(1).permutation(len(points))
    position = numpy.empty(len(points), dtype=int)
    position[order] = numpy.arange(len(points))
    bridge.ok("mesh_from_data", name="Ordered", vertices=points.tolist(), faces=faces)
    bridge.ok("mesh_from_data", name="Shuffled", vertices=points[order].tolist(), faces=[[int(position[i]) for i in face] for face in faces])
    for name in ("Ordered", "Shuffled"):
        bridge.ok("noise_displace", name=name, amplitude=AMPLITUDE, seed=5, scale=3.0, direction="normal")
    ordered = world_points("Ordered")
    shuffled = world_points("Shuffled")
    assert numpy.max(numpy.abs(shuffled - ordered[order])) < 1e-9
    assert numpy.max(numpy.abs(ordered[:, 2])) > 0.05


def test_coincident_vertices_on_split_seams_move_together(bridge):
    quads = [[(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)], [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], [(1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1)], [(0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)]]
    vertices = [corner for quad in quads for corner in quad]
    faces = [list(range(4 * index, 4 * index + 4)) for index in range(6)]
    bridge.ok("mesh_from_data", name="Seams", vertices=[list(map(float, v)) for v in vertices], faces=faces)
    bridge.ok("subdivide", name="Seams", cuts=3)
    before = world_points("Seams")
    bridge.ok("noise_displace", name="Seams", amplitude=0.1, seed=2, scale=0.7, octaves=3, direction="normal")
    points = world_points("Seams")
    count = len(points)
    assert count > 24
    groups = {}
    for index, point in enumerate(points):
        groups.setdefault(tuple(numpy.round(point, 6)), []).append(index)
    assert len(groups) < count
    for members in groups.values():
        assert numpy.ptp(points[members], axis=0).max() < 1e-12
    assert numpy.max(numpy.abs(points - before)) > 0.02


def test_scaled_moved_and_touching_objects_share_one_world_field(bridge):
    grid_plane("Left", 4.0, 24, (-2.0, 0.0, 0.0))
    grid_plane("Right", 4.0, 24, (2.0, 0.0, 0.0))
    for name in ("Left", "Right"):
        bridge.ok("noise_displace", name=name, amplitude=AMPLITUDE, seed=4, scale=3.0, direction="z", octaves=3)
    left, right = world_points("Left"), world_points("Right")
    edge_left = left[numpy.isclose(left[:, 0], 0.0)]
    edge_right = right[numpy.isclose(right[:, 0], 0.0)]
    order_left, order_right = numpy.argsort(edge_left[:, 1]), numpy.argsort(edge_right[:, 1])
    assert len(edge_left) == 25
    assert numpy.max(numpy.abs(edge_left[order_left, 2] - edge_right[order_right, 2])) < 1e-9
    assert numpy.max(numpy.abs(edge_left[:, 2])) > 0.02
    grid_plane("Big", 2.0, 20)
    big = bpy.data.objects["Big"]
    big.scale = (3.0, 3.0, 3.0)
    big.location = (7.0, -3.0, 1.0)
    bpy.context.view_layer.update()
    flat = world_points("Big")
    bridge.ok("noise_displace", name="Big", amplitude=AMPLITUDE, seed=4, scale=3.0, direction="z", octaves=3)
    expected = AMPLITUDE * stack_field(flat, {**STACK, "seed": 4, "scale": 3.0, "octaves": 3})
    assert numpy.max(numpy.abs(world_points("Big")[:, 2] - flat[:, 2] - expected)) < 1e-6


def test_moving_the_object_by_whole_wavelengths_does_not_repeat_the_field(bridge):
    scale = 2.0
    grid_plane("Home", 8.0, 16)
    grid_plane("Shifted", 8.0, 16, (3 * scale, 2 * scale, 0.0))
    for name in ("Home", "Shifted"):
        bridge.ok("noise_displace", name=name, amplitude=AMPLITUDE, seed=6, scale=scale, octaves=1, direction="z")
    home, shifted = world_points("Home")[:, 2], world_points("Shifted")[:, 2]
    assert numpy.std(home) > 0.03
    assert numpy.max(numpy.abs(home - shifted)) > 0.05
    on_lattice = [point for point in world_points("Home") if abs(point[0] / scale - round(point[0] / scale)) < 1e-9 and abs(point[1] / scale - round(point[1] / scale)) < 1e-9]
    assert len(on_lattice) >= 9
    assert numpy.std([point[2] for point in on_lattice]) > 0.02


def test_a_face_selection_and_a_vertex_group_mask_and_weight_the_noise(bridge):
    grid_plane("Full", 10.0, 20)
    grid_plane("Masked", 10.0, 20)
    grid_plane("Weighted", 10.0, 20)
    bridge.ok("noise_displace", name="Full", amplitude=AMPLITUDE, seed=8, scale=3.0, direction="z")
    result = bridge.ok("noise_displace", name="Masked", amplitude=AMPLITUDE, seed=8, scale=3.0, direction="z", box={"min": [0.0, -6, -1], "max": [6, 6, 1]})
    full, masked = world_points("Full"), world_points("Masked")
    inside = masked[:, 0] > 0.6
    outside = masked[:, 0] < -0.01
    assert numpy.max(numpy.abs(masked[outside, 2])) == 0.0
    assert numpy.max(numpy.abs(masked[inside, 2] - full[inside, 2])) < 1e-9
    assert 0 < result["displaced_vertices"] < 441
    group = bpy.data.objects["Weighted"].vertex_groups.new(name="Soft")
    group.add(list(range(0, 441, 2)), 0.5, "REPLACE")
    bridge.ok("noise_displace", name="Weighted", amplitude=AMPLITUDE, seed=8, scale=3.0, direction="z", vertex_group="Soft")
    weighted = world_points("Weighted")
    assert numpy.max(numpy.abs(weighted[1::2, 2])) == 0.0
    assert numpy.max(numpy.abs(weighted[0::2, 2] - 0.5 * full[0::2, 2])) < 1e-9


def test_normal_direction_follows_the_surface_and_z_stays_vertical(bridge):
    bridge.ok("add_primitive", type="ico_sphere", name="Ball", radius=2.0, subdivisions=4)
    bridge.ok("add_primitive", type="ico_sphere", name="Pole", radius=2.0, subdivisions=4)
    before = world_points("Ball")
    bridge.ok("noise_displace", name="Ball", amplitude=0.2, seed=2, scale=1.5, direction="normal")
    bridge.ok("noise_displace", name="Pole", amplitude=0.2, seed=2, scale=1.5, direction="z")
    moved = world_points("Ball") - before
    radial = before / numpy.linalg.norm(before, axis=1)[:, None]
    along = numpy.einsum("ij,ij->i", moved, radial)
    assert numpy.max(numpy.linalg.norm(moved - along[:, None] * radial, axis=1)) < 0.02
    vertical = world_points("Pole") - before
    assert numpy.max(numpy.abs(vertical[:, :2])) < 1e-9 and numpy.max(numpy.abs(vertical[:, 2])) > 0.05


def test_noise_displace_refuses_bad_arguments(bridge):
    grid_plane("Sheet", 4.0, 4)
    for bad in ({"octaves": 13}, {"octaves": 0}, {"hurst": 1.5}, {"basis": "simplex"}, {"mode": "melt"}, {"lacunarity": 0.5}, {"scale": 0.0}, {"amplitude": -1.0}, {"seed": -1}, {"ridge_offset": 1.5}, {"warp": -1.0}):
        bridge.refuse("noise_displace", "bad_args", **{"name": "Sheet", "amplitude": 0.1, **bad})
    bridge.refuse("noise_displace", "bad_args", name="Sheet")
    bridge.refuse("noise_displace", "not_found", name="Sheet", amplitude=0.1, vertex_group="Ghost")
    bridge.refuse("noise_displace", "not_found", name="Ghost", amplitude=0.1)


run(globals())
