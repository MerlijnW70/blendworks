import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy

from blendworks_bridge.noise import GRADIENTS, PERLIN_BOUND, basis_value, feature_points, lattice_hash, perlin, perlin_raw, worley_distances
from blendworks_bridge.noise_stack import octave_point, stack_field, stack_value, warp_field

BASE = {"seed": 1, "basis": "perlin", "scale": 4.0, "octaves": 1, "lacunarity": 2.0, "hurst": 0.7, "mode": "fbm", "ridge_offset": 1.0, "warp": 0.0, "warp_octaves": 2}


def fade_reference(t):
    return 6 * t**5 - 15 * t**4 + 10 * t**3


def perlin_reference(point, seed):
    cell = [math.floor(c) for c in point]
    frac = [c - f for c, f in zip(point, cell)]
    total = 0.0
    for corner in itertools.product((0, 1), repeat=3):
        index = int(lattice_hash(*(numpy.array([cell[axis] + corner[axis]]) for axis in range(3)), seed)[0] >> numpy.uint64(32)) % 12
        gradient = GRADIENTS[index]
        weight = 1.0
        for axis in range(3):
            fade = fade_reference(frac[axis])
            weight *= fade if corner[axis] else 1.0 - fade
        total += weight * sum(gradient[axis] * (frac[axis] - corner[axis]) for axis in range(3))
    return total


def brute_force(point, seed, reach=4):
    base = numpy.floor(point).astype(numpy.int64)
    cells = numpy.array([base + offset for offset in itertools.product(range(-reach, reach + 1), repeat=3)])
    distances = numpy.sort(numpy.linalg.norm(feature_points(cells, seed) - point, axis=1))
    return distances[0], distances[1]


def test_perlin_matches_a_plain_scalar_implementation_of_the_paper(bridge):
    rng = numpy.random.default_rng(5)
    points = rng.uniform(-30, 30, (300, 3))
    expected = numpy.array([perlin_reference(point, 9) for point in points])
    assert numpy.max(numpy.abs(perlin_raw(points, 9) - expected)) < 1e-12


def test_perlin_is_zero_on_lattice_points_and_stays_inside_one(bridge):
    lattice = numpy.array(list(itertools.product(range(-3, 4), repeat=3)), dtype=float)
    assert numpy.max(numpy.abs(perlin(lattice, 4))) < 1e-12
    samples = numpy.random.default_rng(2).uniform(-500, 500, (400_000, 3))
    values = perlin(samples, 4)
    assert numpy.max(numpy.abs(values)) <= 1.0
    assert numpy.max(numpy.abs(values)) > 0.85
    assert PERLIN_BOUND >= 1.0363


def test_the_field_at_whole_wavelength_points_is_not_constant(bridge):
    wavelength = 4.0
    lattice = numpy.array(list(itertools.product(range(-4, 5), repeat=3)), dtype=float) * wavelength
    values = stack_field(lattice, BASE)
    assert numpy.std(values) > 0.15
    assert len(numpy.unique(numpy.round(values, 6))) > 100
    assert numpy.std(stack_field(lattice + 2 * wavelength, BASE) - values) > 0.1


def test_one_octave_ridged_and_billow_are_the_basis_evaluated_directly(bridge):
    rng = numpy.random.default_rng(3)
    points = rng.uniform(-20, 20, (500, 3))
    for basis in ("perlin", "worley_f1", "worley_f2_minus_f1"):
        lattice, lattice_seed = octave_point(points, BASE["scale"], 2.0, BASE["seed"], 0)
        direct = basis_value(basis, lattice, lattice_seed)
        ridged = stack_field(points, {**BASE, "basis": basis, "mode": "ridged", "ridge_offset": 0.8})
        billow = stack_field(points, {**BASE, "basis": basis, "mode": "billow"})
        fbm = stack_field(points, {**BASE, "basis": basis})
        assert numpy.max(numpy.abs(ridged - (0.8 - numpy.abs(direct)))) < 1e-12, basis
        assert numpy.max(numpy.abs(billow - numpy.abs(direct))) < 1e-12, basis
        assert numpy.max(numpy.abs(fbm - direct)) < 1e-12, basis
        assert numpy.std(direct) > 0.1, basis


def test_worley_f1_is_zero_at_feature_points_and_matches_a_brute_force_search(bridge):
    rng = numpy.random.default_rng(8)
    cells = rng.integers(-6, 6, (40, 3))
    features = feature_points(cells, 5)
    nearest, _ = worley_distances(features, 5)
    assert numpy.max(nearest) < 1e-9
    points = rng.uniform(-8, 8, (400, 3))
    first, second = worley_distances(points, 5)
    for index, point in enumerate(points):
        expected = brute_force(point, 5)
        assert abs(first[index] - expected[0]) < 1e-12 and abs(second[index] - expected[1]) < 1e-12


def test_worley_f2_minus_f1_is_zero_on_cell_borders(bridge):
    rng = numpy.random.default_rng(12)
    points = rng.uniform(-8, 8, (400, 3))
    borders = []
    for point in points:
        base = numpy.floor(point).astype(numpy.int64)
        cells = numpy.array([base + offset for offset in itertools.product(range(-3, 4), repeat=3)])
        sites = feature_points(cells, 6)
        order = numpy.argsort(numpy.linalg.norm(sites - point, axis=1))
        borders.append((sites[order[0]] + sites[order[1]]) / 2)
    borders = numpy.array(borders)
    first, second = worley_distances(borders, 6)
    kept = 0
    for index, border in enumerate(borders):
        expected = brute_force(border, 6)
        if expected[1] - expected[0] < 1e-9:
            kept += 1
            assert second[index] - first[index] < 1e-9
    assert kept > 200
    interior = worley_distances(points, 6)
    assert numpy.median(interior[1] - interior[0]) > 0.1


def test_every_basis_and_mode_stays_inside_the_unit_bound_with_warp(bridge):
    points = numpy.random.default_rng(1).uniform(-300, 300, (20_000, 3))
    for basis in ("perlin", "worley_f1", "worley_f2_minus_f1"):
        for mode in ("fbm", "ridged", "billow"):
            params = {**BASE, "basis": basis, "mode": mode, "octaves": 6, "warp": 3.0, "ridge_offset": 0.6}
            values = stack_field(points, params)
            assert numpy.max(numpy.abs(values)) <= 1.0, (basis, mode)
            assert numpy.std(values) > 0.05, (basis, mode)


def test_a_warp_moves_the_lookup_point_by_at_most_the_warp_in_metres(bridge):
    points = numpy.random.default_rng(4).uniform(-50, 50, (4_000, 3))
    params = {**BASE, "octaves": 3, "warp": 2.0}
    shift = warp_field(points, params)
    assert numpy.max(numpy.abs(shift)) <= 1.0
    assert numpy.std(shift) > 0.1
    assert all(numpy.std(shift[:, axis]) > 0.1 for axis in range(3))
    expected = stack_value(points + 2.0 * shift, params)
    assert numpy.max(numpy.abs(stack_field(points, params) - expected)) < 1e-12
    plain = stack_field(points, {**params, "warp": 0.0})
    assert numpy.std(stack_field(points, params) - plain) > 0.05


run(globals())
