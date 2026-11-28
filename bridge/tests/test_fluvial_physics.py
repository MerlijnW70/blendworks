import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from harness import run

import numpy

from blendworks_bridge import fluvial_fields, fluvial_measure, fluvial_model, fluvial_spinup

UPLIFT = 1e-3
K = 2e-5
M = 0.45


def steady(edges, side=97, cell=150.0, steps=3000, tolerance=1e-4, **law):
    settings = {"erodibility": K, "area_exponent": M, "diffusivity": 0.0, "channel_area": 0.0, "head_exponent": 0.0, "edges": edges, "threads": 2, "flow": "d8"}
    settings.update(law)
    model = fluvial_model.Law(**settings)
    schedule = fluvial_spinup.Schedule(levels=[side], steps=[steps], courant=[60.0], tolerance=tolerance)
    uplift = lambda shape, spacing: fluvial_fields.uplift_field(shape, spacing, UPLIFT, "block")
    return fluvial_spinup.spin_up(side, cell, uplift, model, schedule, seed=3, initial_slope=5e-4, initial_relief=2.0), model


def test_steady_channels_follow_the_analytic_slope_area_relation(bridge):
    """Single receivers (flow d8): the analytic relation S = (U/K) A^-m is written for one receiver per cell."""
    spun, _ = steady(fluvial_model.edge_mask(["south"]))
    assert spun.levels[0].steady, spun.levels[0]
    heights, receivers, area = spun.heights.ravel(), spun.last.receivers, spun.last.area.ravel()
    flows = (receivers >= 0) & (area >= 1e6)
    length = fluvial_measure.flow_lengths(receivers, (150.0, 150.0), spun.heights.shape)[flows]
    slope = (heights[flows] - heights[receivers[flows]]) / length
    expected = (UPLIFT / K) * area[flows] ** -M
    error = numpy.abs(slope / expected - 1.0)
    assert numpy.median(error) < 0.01 and error.max() < 0.05, (numpy.median(error), error.max())


def test_lake_routing_leaves_no_undrained_pit_in_either_mode(bridge):
    edges = fluvial_model.edge_mask(["south"])
    for carve in (True, False):
        spun, law = steady(edges, steps=40, tolerance=1e-9, carve=carve)
        lakes, _, _ = fluvial_model.route(spun.heights, (150.0, 150.0), law)
        outlets = fluvial_model.outlet_cells(spun.heights.shape, edges)
        assert fluvial_measure.undrained_pits(lakes.receivers, outlets, spun.heights.shape) == 0, carve


def test_rivers_leave_only_through_the_base_level_sides(bridge):
    edges = fluvial_model.edge_mask(["south", "east"])
    spun, _ = steady(edges, steps=60, tolerance=1e-9)
    roots = (spun.last.receivers < 0).reshape(spun.heights.shape)
    outlets = fluvial_model.outlet_cells(spun.heights.shape, edges)
    assert (roots == outlets).all()
    assert (spun.heights[outlets] == 0.0).all() and spun.heights[~outlets].min() > 0.0


def test_hard_rock_bands_stand_higher(bridge):
    side, cell = 97, 150.0
    bands = fluvial_fields.lithology_bands((side, side), (cell, cell), K, [0.25, 1.0], 2400.0)
    spun, _ = steady(fluvial_model.edge_mask(["south"]), steps=300, tolerance=1e-3, erodibility=bands)
    hard = bands < K
    assert spun.heights[hard].mean() > 1.3 * spun.heights[~hard].mean()


def steepest_descent(heights, cell):
    padded = numpy.pad(heights, 1, mode="edge")
    steepest = numpy.zeros_like(heights)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                neighbour = padded[1 + dy: 1 + dy + heights.shape[0], 1 + dx: 1 + dx + heights.shape[1]]
                steepest = numpy.maximum(steepest, (heights - neighbour) / (cell * math.hypot(dx, dy)))
    return steepest


def test_every_step_ends_on_its_own_threshold_surface(bridge):
    edges = fluvial_model.edge_mask(["south"])
    rng = numpy.random.default_rng(5)
    heights = numpy.cumsum(rng.random((65, 65)) * 60.0, axis=0) + rng.random((65, 65)) * 200.0
    heights[0] = 0.0
    uplift = numpy.where(fluvial_model.outlet_cells(heights.shape, edges), 0.0, UPLIFT)
    drawn = {}

    def tangent_of(shape, index):
        drawn[index] = numpy.tan(numpy.radians(fluvial_fields.critical_angles(shape, (150.0, 150.0), 30.0, 38.0, index, shortest=300.0)))
        return drawn[index]

    law = fluvial_model.Law(erodibility=K, area_exponent=M, diffusivity=0.0, channel_area=2e5, threshold_of=tangent_of, edges=edges, threads=2)
    for index in range(3):
        stepped = fluvial_model.step(heights, uplift, (150.0, 150.0), law, 100.0, index)
        tangent = stepped.extra["tangent"]
        assert tangent is drawn[index]
        for axis in (0, 1):
            drop = numpy.diff(stepped.heights, axis=axis)
            higher = numpy.where(drop < 0.0, tangent[:-1] if axis == 0 else tangent[:, :-1], tangent[1:] if axis == 0 else tangent[:, 1:])
            assert (numpy.abs(drop) <= higher * 150.0 + 1e-6).all(), (index, axis)
        heights = stepped.heights
    assert not numpy.allclose(drawn[0], drawn[1])

def test_linear_and_non_linear_diffusion_both_wear_the_hillslopes(bridge):
    edges = fluvial_model.edge_mask(["south"])
    rng = numpy.random.default_rng(6)
    heights = numpy.cumsum(rng.random((65, 65)) * 60.0, axis=0) + rng.random((65, 65)) * 200.0
    heights[0] = 0.0
    uplift = numpy.zeros_like(heights)
    found = {}
    for name, diffusivity, critical in (("none", 0.0, None), ("linear", 0.05, None), ("non-linear", 0.05, 0.8)):
        law = fluvial_model.Law(erodibility=K, area_exponent=M, diffusivity=diffusivity, critical_slope=critical, channel_area=2e5,
                                edges=edges, threads=2)
        stepped = fluvial_model.step(heights, uplift, (150.0, 150.0), law, 20000.0)
        found[name] = numpy.percentile(steepest_descent(stepped.heights, 150.0)[stepped.area < 2e5], 99)
    assert found["linear"] < 0.95 * found["none"] and found["non-linear"] < 0.9 * found["linear"], found

def test_the_erosion_record_closes_the_mass_balance(bridge):
    edges = fluvial_model.edge_mask(["south"])
    law = fluvial_model.Law(erodibility=K, area_exponent=M, diffusivity=0.005, channel_area=1e5, threshold_slope=0.7, edges=edges, threads=2)
    rng = numpy.random.default_rng(1)
    heights = rng.random((65, 65)) * 50.0
    heights[fluvial_model.outlet_cells(heights.shape, edges)] = 0.0
    uplift = numpy.where(fluvial_model.outlet_cells(heights.shape, edges), 0.0, UPLIFT)
    eroded = numpy.zeros_like(heights)
    start = heights.copy()
    for _ in range(5):
        stepped = fluvial_model.step(heights, uplift, (150.0, 150.0), law, 5000.0)
        eroded += stepped.eroded
        heights = stepped.heights
    assert numpy.allclose(start + uplift * 25000.0 - eroded, heights, atol=1e-6)


def test_the_spin_up_runs_coarse_to_fine_and_stops_when_steady(bridge):
    """A deterministic law (single receivers, a fixed threshold, a fixed head area) so the steady state exists to be
    found; slope-dependent heads and a stochastic threshold keep a surface fluctuating."""
    edges = fluvial_model.edge_mask(["south"])
    law = fluvial_model.Law(erodibility=K, area_exponent=M, diffusivity=0.005, channel_area=1e5, threshold_slope=0.7, edges=edges, threads=2, flow="d8", head_exponent=0.0)
    schedule = fluvial_spinup.Schedule(levels=[65, 129], steps=[2000, 3], courant=[60.0, 30.0], tolerance=0.01)
    uplift = lambda shape, spacing: fluvial_fields.uplift_field(shape, spacing, UPLIFT, "block")
    spun = fluvial_spinup.spin_up(129, 120.0, uplift, law, schedule, seed=1, initial_slope=5e-4, initial_relief=2.0)
    coarse, fine = spun.levels
    assert coarse.side == 65 and fine.side == 129 and spun.heights.shape == (129, 129)
    assert coarse.steady and coarse.steps < 2000 and coarse.change < 0.01, coarse
    assert fine.steps == 3 and not fine.steady
    assert 0.0 < coarse.dt[0] <= coarse.dt[1] and math.isclose(spun.years, coarse.years + fine.years)


run(globals())
