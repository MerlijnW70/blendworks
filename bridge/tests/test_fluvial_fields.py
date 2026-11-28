import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from harness import run

import numpy

from blendworks_bridge import fluvial_fields, fluvial_measure, fluvial_model, fluvial_presets, fluvial_spinup
from blendworks_bridge.terrain_grid import EDGE_NORTH, EDGE_SOUTH

SHAPE = (65, 81)
SPACING = (100.0, 100.0)
K_DEFAULT = 2e-5


def test_world_sides_map_to_the_kernel_edges_and_hold_the_outlets(bridge):
    assert fluvial_model.edge_mask(["north"]) == EDGE_SOUTH and fluvial_model.edge_mask(["south"]) == EDGE_NORTH
    outlets = fluvial_model.outlet_cells(SHAPE, fluvial_model.edge_mask(["south", "east"]))
    assert outlets[0, :].all() and outlets[:, -1].all() and not outlets[1:, :-1].any()


def test_a_range_rises_from_the_base_level_to_its_crest_and_falls_behind_it(bridge):
    edges = fluvial_model.edge_mask(["south"])
    field = fluvial_fields.uplift_field(SHAPE, SPACING, 2e-3, "range", edges=edges, crest=0.625, behind=0.3)
    column = field[:, 40]
    crest_row = 40
    assert column[0] == 0.0 and math.isclose(column[crest_row], 2e-3, rel_tol=1e-9)
    assert (numpy.diff(column[: crest_row + 1]) >= 0.0).all() and (numpy.diff(column[crest_row:]) <= 0.0).all()
    assert math.isclose(column[-1], 0.3 * 2e-3, rel_tol=1e-9)
    varied = fluvial_fields.uplift_field(SHAPE, SPACING, 2e-3, "range", edges=edges, crest=0.625, behind=0.3, along=0.3, seed=4)
    ratio = varied[1:] / field[1:]
    assert ratio.min() >= 0.7 - 1e-9 and ratio.max() <= 1.3 + 1e-9 and numpy.ptp(ratio) > 0.2, (ratio.min(), ratio.max())


def test_block_dome_tilt_array_and_margin_shapes(bridge):
    block = fluvial_fields.uplift_field(SHAPE, SPACING, 1e-3, "block", margin=1000.0)
    assert block[0, 0] == 0.0 and math.isclose(block[32, 40], 1e-3)
    dome = fluvial_fields.uplift_field(SHAPE, SPACING, 1e-3, "dome", width=2000.0)
    assert math.isclose(dome[32, 40], 1e-3) and dome[0, 0] == 0.0
    tilted = fluvial_fields.uplift_field(SHAPE, SPACING, 1e-3, "tilted")
    assert tilted[:, 0].max() == 0.0 and math.isclose(tilted[:, -1].min(), 1e-3)
    grid = numpy.outer(numpy.linspace(0.0, 1e-3, 5), numpy.ones(4))
    array = fluvial_fields.uplift_field(SHAPE, SPACING, 1.0, "array", values=grid)
    assert array.shape == SHAPE and math.isclose(array[-1, 0], 1e-3) and array[0, 0] == 0.0


def test_lithology_bands_repeat_their_factors(bridge):
    field = fluvial_fields.lithology_bands(SHAPE, SPACING, 1e-5, [0.5, 1.0, 2.0], 1000.0)
    assert set(numpy.round(numpy.unique(field) / 1e-5, 9)) == {0.5, 1.0, 2.0}
    assert (field[:, :10] == 0.5e-5).all() and (field[:, 10:20] == 1e-5).all()


def test_every_preset_parameter_lies_in_its_cited_range(bridge):
    for name in fluvial_presets.PRESETS:
        assert fluvial_presets.out_of_range(name) == [], name
    for low, high, sources in list(fluvial_presets.RANGES.values()) + list(fluvial_presets.SETTING_UPLIFT.values()) + list(fluvial_presets.LIST_RANGES.values()):
        assert low < high and sources and all(source in fluvial_presets.SOURCES for source in sources)


def test_the_stated_time_step_follows_the_knickpoint_rule(bridge):
    law = fluvial_model.Law(erodibility=2e-5, area_exponent=0.45)
    schedule = fluvial_spinup.default_schedule(2048)
    assert schedule.levels == [512, 1024, 2048] and schedule.steps[0] > schedule.steps[-1]
    area = numpy.array([1e9])
    dt = fluvial_spinup.stable_dt(law, (30.0, 30.0), area, 0.1, schedule, numpy.array([2e-5]), 4.0)
    assert math.isclose(dt, 4.0 * 30.0 / (2e-5 * 1e9 ** 0.45), rel_tol=1e-12)


def test_coarse_levels_raise_the_diffusivity_to_space_valleys_by_cells(bridge):
    law = fluvial_model.Law(erodibility=2e-5, area_exponent=0.45, diffusivity=0.005)
    coarse = fluvial_spinup.level_diffusivity(law, (480.0, 480.0), 2e-5)
    assert math.isclose((coarse / 2e-5) ** (1.0 / 0.9), fluvial_spinup.VALLEY_CELLS * 480.0, rel_tol=1e-9)
    assert fluvial_spinup.level_diffusivity(law, (30.0, 30.0), 2e-5) == 0.005


def test_strahler_orders_a_known_tree(bridge):
    """0 is the outlet; 1 and 2 join at 3 (order 2); 4 and 5 join at 6 (order 2); 3 and 6 join at 7 (order 3); 8 joins 7 alone."""
    from blendworks_bridge import terrain_kernels as kernels

    receivers = -numpy.ones(12, dtype=numpy.int32)
    links = {1: 3, 2: 3, 3: 7, 4: 6, 5: 6, 6: 7, 8: 7, 7: 0}
    for cell, target in links.items():
        receivers[cell] = target
    ordering = kernels.order(receivers, (3, 4), 1, 1, "core")
    channel = numpy.ones((3, 4), dtype=bool)
    channel.ravel()[[9, 10, 11]] = False
    order = fluvial_measure.strahler(ordering, channel).ravel()
    assert order[[1, 2, 4, 5, 8]].tolist() == [1, 1, 1, 1, 1]
    assert order[3] == 2 and order[6] == 2 and order[7] == 3 and order[0] == 3


def test_hack_fit_recovers_a_known_exponent(bridge):
    area = numpy.logspace(5, 9, 400)
    length = 1.4 * area ** 0.55
    exponent, decades = fluvial_measure.hack_fit(area, length, numpy.ones(400, dtype=bool), 1e5)
    assert abs(exponent - 0.55) < 1e-6 and decades > 3.5


def test_aspect_shares_count_the_downslope_half_planes(bridge):
    x, y = numpy.meshgrid(numpy.arange(40.0), numpy.arange(40.0))
    east, north = fluvial_measure.aspect_shares(-x * 10.0, SPACING)
    assert east == 1.0 and north == 0.0
    east, north = fluvial_measure.aspect_shares(numpy.abs(x - 19.5) * 10.0, SPACING)
    assert east == 0.5

def test_grid_bias_flags_ridges_along_the_grid_and_passes_isotropic_relief(bridge):
    x, y = numpy.meshgrid(numpy.arange(256.0), numpy.arange(256.0))
    aligned = numpy.where(y < 128.0, numpy.abs((x % 16.0) - 8.0) * 20.0, numpy.abs((y % 22.0) - 11.0) * 20.0)
    rng = numpy.random.default_rng(1)
    waves = sum(40.0 * numpy.cos(2.0 * numpy.pi * (x * math.cos(t) + y * math.sin(t)) / length + phase)
                for t, length, phase in zip(rng.uniform(0.0, math.pi, 60), rng.uniform(20.0, 200.0, 60), rng.uniform(0.0, 6.3, 60)))
    assert fluvial_measure.grid_bias(aligned, (30.0, 30.0)) > 2.0
    assert fluvial_measure.grid_bias(waves, (30.0, 30.0)) < 1.15, fluvial_measure.grid_bias(waves, (30.0, 30.0))


def test_the_main_receiver_takes_the_larger_share(bridge):
    table = numpy.full((3, 8), -1, dtype=numpy.int32)
    shares = numpy.zeros((3, 8))
    table[0, [0, 1]], shares[0, [0, 1]] = [5, 6], [0.3, 0.7]
    table[1, 2], shares[1, 2] = 9, 1.0
    assert fluvial_measure.dominant_receivers(table, shares).tolist() == [6, 9, -1]


def test_hillslope_length_and_drainage_density_on_a_known_tree(bridge):
    from blendworks_bridge import terrain_kernels as kernels

    receivers = -numpy.ones(12, dtype=numpy.int32)
    receivers[[1, 2, 3, 5, 6, 7, 9, 10, 11]] = [0, 1, 2, 1, 2, 3, 5, 6, 7]
    ordering = kernels.order(receivers, (3, 4), 1, 1, "core")
    channel = numpy.zeros((3, 4), dtype=bool)
    channel.ravel()[[1, 2, 3]] = True
    outlets = numpy.zeros((3, 4), dtype=bool)
    outlets.ravel()[[0, 4, 8]] = True
    found = fluvial_measure.hillslope_metrics(ordering, receivers, channel, (100.0, 100.0), (3, 4), outlets)
    assert math.isclose(found["hillslope_length"], 200.0)
    assert math.isclose(found["drainage_density"], 0.3 / 0.09)


def test_steeper_ground_starts_channels_at_smaller_areas(bridge):
    law = fluvial_model.Law(erodibility=K_DEFAULT, channel_area=1e4, head_slope=0.6, head_exponent=2.0)
    x = numpy.arange(20.0)[None, :] * numpy.ones((20, 1))
    steep, gentle = x * 0.6 * 30.0, x * 0.15 * 30.0
    area = numpy.full((20, 20), 2e4)
    assert fluvial_model.channel_mask(law, steep, (30.0, 30.0), area)[10, 10]
    assert not fluvial_model.channel_mask(law, gentle, (30.0, 30.0), area)[10, 10]
    assert fluvial_model.channel_mask(law, gentle, (30.0, 30.0), numpy.full((20, 20), 1.7e5))[10, 10]


def test_critical_angles_stay_in_their_range_and_vary_with_the_seed(bridge):
    first = fluvial_fields.critical_angles(SHAPE, SPACING, 30.0, 38.0, 1, shortest=200.0)
    second = fluvial_fields.critical_angles(SHAPE, SPACING, 30.0, 38.0, 2, shortest=200.0)
    assert first.min() >= 30.0 and first.max() <= 38.0 and numpy.ptp(first) > 6.0
    assert not numpy.allclose(first, second)
    assert numpy.array_equal(first, fluvial_fields.critical_angles(SHAPE, SPACING, 30.0, 38.0, 1, shortest=200.0))


run(globals())
