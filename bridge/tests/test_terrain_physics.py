import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy
from terrain_helpers import grid_cases, core_ready, ridge_terrain, stream_power_run

from blendworks_bridge import terrain_kernels as kernels
from blendworks_bridge.terrain_grid import EDGE_SOUTH, TerrainGrid

SLOPE_AREA_TOLERANCE = 1e-6
UPLIFT = 1e-3
ERODIBILITY = 2e-5
AREA_EXPONENT = 0.5


def steady_state(n, dt):
    rng = numpy.random.default_rng(3)
    spacing = (100.0, 100.0)
    heights = rng.random((33, 33))
    heights[-1, :] = 0.0
    for _ in range(80):
        before = heights
        heights = stream_power_run(heights, spacing, EDGE_SOUTH, UPLIFT, ERODIBILITY, AREA_EXPONENT, n, dt, 25)
        if numpy.abs(heights - before).max() <= 1e-11 * heights.max():
            return heights, spacing
    raise AssertionError(f"no steady state for n = {n}: the last 25 steps still moved {numpy.abs(heights - before).max()} m")


def check_slope_area(n, dt):
    heights, spacing = steady_state(n, dt)
    receivers, _ = kernels.d8(heights, spacing, EDGE_SOUTH, 2, "core")
    ordering = kernels.order(receivers, heights.shape, 1, 2, "core")
    assert kernels.route_lakes(heights, receivers, ordering, True, spacing, EDGE_SOUTH, 2, "core").basins == 0, "steady state left a pit"
    area = kernels.accumulate(ordering, numpy.full(heights.size, spacing[0] * spacing[1]), threads=2, engine="core")
    flat = heights.ravel()
    moving = receivers >= 0
    grid = TerrainGrid.of(heights, spacing, EDGE_SOUTH)
    slope = (flat[moving] - flat[receivers[moving]]) / grid.distance(numpy.flatnonzero(moving), receivers[moving])
    uplift = ERODIBILITY * area[moving] ** AREA_EXPONENT * slope**n
    error = numpy.abs(uplift / UPLIFT - 1.0).max()
    assert error <= SLOPE_AREA_TOLERANCE, f"n = {n}: K A^m S^n differs from U by up to {error:.2e} of U"
    fitted = numpy.polyfit(numpy.log(area[moving]), numpy.log(slope), 1)[0]
    assert abs(fitted + AREA_EXPONENT / n) <= 1e-6, f"slope-area exponent {fitted}, expected {-AREA_EXPONENT / n}"
    assert area[moving].max() / area[moving].min() >= 100.0


def test_stream_power_reaches_the_analytic_slope_area_relation_for_n_one(bridge):
    if not core_ready():
        return
    check_slope_area(1.0, 2e4)


def test_stream_power_reaches_the_analytic_slope_area_relation_with_newton(bridge):
    if not core_ready():
        return
    check_slope_area(2.0, 2e4)


def cosine_mode(rows, columns, k, l):
    row, column = numpy.mgrid[0:rows, 0:columns].astype(float)
    return numpy.cos(math.pi * k * (column + 0.5) / columns) * numpy.cos(math.pi * l * (row + 0.5) / rows)


def test_adi_damps_a_cosine_mode_by_the_exact_implicit_factor(bridge):
    if not core_ready():
        return
    rows, columns, spacing, diffusivity, dt = 24, 30, (2.0, 3.0), 0.7, 40.0
    for k, l in ((1, 0), (3, 2), (29, 23)):
        heights = 10.0 + cosine_mode(rows, columns, k, l)
        stepped = kernels.diffuse(heights, diffusivity, dt, spacing, 0, threads=2, engine="core")
        along_x = diffusivity * dt / spacing[0] ** 2 * 2.0 * (1.0 - math.cos(math.pi * k / columns))
        along_y = diffusivity * dt / spacing[1] ** 2 * 2.0 * (1.0 - math.cos(math.pi * l / rows))
        expected = 10.0 + cosine_mode(rows, columns, k, l) / ((1.0 + along_x) * (1.0 + along_y))
        assert numpy.abs(stepped - expected).max() <= 1e-11, (k, l, numpy.abs(stepped - expected).max())


def test_both_diffusions_stay_stable_and_conserve_mass_at_long_steps(bridge):
    if not core_ready():
        return
    rng = numpy.random.default_rng(9)
    heights = ridge_terrain(40, 36, 2) + rng.random((40, 36)) * 5.0
    explicit_limit = 1.0 / (4.0 * 0.5)
    for critical in (None, 0.8):
        current = heights
        for _ in range(20):
            current = kernels.diffuse(current, 0.5, 1e6 * explicit_limit, (1.0, 1.0), 0, critical_slope=critical, threads=2, engine="core")
            assert current.min() >= heights.min() - 1e-9 and current.max() <= heights.max() + 1e-9, "a long step broke the maximum principle"
            assert abs(current.sum() - heights.sum()) <= 1e-9 * abs(heights.sum()), "a long step changed the mass"
        assert numpy.ptp(current) < 1e-3 * numpy.ptp(heights), "long steps did not flatten the surface"


def test_roering_diffusion_reduces_to_linear_far_below_the_critical_slope(bridge):
    if not core_ready():
        return
    heights = ridge_terrain(20, 22, 4) * 0.01
    linear = kernels.diffuse(heights, 0.3, 10.0, (1.0, 1.0), 4, threads=2, engine="core")
    nonlinear = kernels.diffuse(heights, 0.3, 10.0, (1.0, 1.0), 4, critical_slope=1e6, threads=2, engine="core")
    assert numpy.abs(linear - nonlinear).max() <= 1e-12
    steep = ridge_terrain(20, 22, 4)
    linear = kernels.diffuse(steep, 0.3, 0.2, (1.0, 1.0), 0, threads=2, engine="core")
    nonlinear = kernels.diffuse(steep, 0.3, 0.2, (1.0, 1.0), 0, critical_slope=0.7, threads=2, engine="core")
    assert numpy.abs(nonlinear - steep).sum() > 1.5 * numpy.abs(linear - steep).sum(), "slopes near Sc must move more material than linear diffusion"


def test_slides_leave_no_slope_above_each_cells_critical_angle_and_keep_mass(bridge):
    if not core_ready():
        return
    heights = ridge_terrain(30, 30, 5) * 4.0
    tangent = numpy.where(numpy.arange(30)[None, :] < 15, 0.4, 0.9) * numpy.ones((30, 1))
    settled = kernels.slide(heights, tangent, 1.0, 10000, (1.0, 1.0), 0, 2, "core")
    assert abs(settled.sum() - heights.sum()) <= 1e-9 * abs(heights.sum())
    table = TerrainGrid(30, 30).neighbours()
    distances = TerrainGrid(30, 30).distances()
    flat, angle = settled.ravel(), tangent.ravel()
    for slot in range(8):
        inside = table[slot] >= 0
        drop = flat[inside] - flat[table[slot][inside]]
        assert (drop <= angle[inside] * distances[slot] + 1e-4).all(), f"slot {slot}: excess {(drop - angle[inside] * distances[slot]).max()}"
    assert (numpy.abs(settled - heights) > 1e-3).any()


def drains_to_sea(heights, routed, edges):
    ordering = kernels.order(routed.receivers, heights.shape, 1, 2, "core")
    status = TerrainGrid.of(heights, (1.0, 1.0), edges).status(heights)
    reach = status == 2
    receivers = routed.receivers.astype(numpy.int64)
    for index in range(1, ordering.levels):
        cells = ordering.level(index)
        reach[cells] = reach[receivers[cells]]
    return reach.reshape(heights.shape)


def test_lake_water_equals_the_priority_flood_fill_and_epsilon_drains_every_cell(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        receivers, _ = kernels.d8(heights, spacing, edges, 2, "core")
        ordering = kernels.order(receivers, heights.shape, 1, 2, "core")
        routed = kernels.route_lakes(heights, receivers, ordering, False, spacing, edges, 2, "core")
        filled, _ = kernels.priority_flood(heights, False, edges, "core")
        connected = drains_to_sea(heights, routed, edges)
        assert numpy.array_equal(routed.water[connected], filled[connected]), name
        assert numpy.array_equal(filled[~connected], heights[~connected], equal_nan=True), name
        sloped, _ = kernels.priority_flood(heights, True, edges, "core")
        drained, _ = kernels.d8(sloped, (1.0, 1.0), edges, 2, "core")
        status = TerrainGrid.of(heights, spacing, edges).status(heights)
        pits = (drained < 0) & (status == 1) & connected.ravel()
        assert not pits.any(), f"{name}: Priority-Flood with epsilon left {int(pits.sum())} pits"


def two_pit_depression():
    row, column = numpy.mgrid[0:25, 0:40].astype(float)
    heights = 0.5 * column + 0.01 * row
    inside = ((row - 12.0) / 7.0) ** 2 + ((column - 25.0) / 9.0) ** 2 <= 1.0
    cones = numpy.minimum(2.0 + 0.3 * numpy.hypot(row - 12.0, column - 20.0), 4.0 + 0.3 * numpy.hypot(row - 12.0, column - 30.0))
    heights[inside] = cones[inside]
    return heights


def test_nested_depressions_spill_into_one_lake_at_the_outer_pass(bridge):
    if not core_ready():
        return
    heights, spacing, edges = two_pit_depression(), (1.0, 1.0), 8
    receivers, _ = kernels.d8(heights, spacing, edges, 2, "core")
    ordering = kernels.order(receivers, heights.shape, 1, 2, "core")
    for carve in (False, True):
        routed = kernels.route_lakes(heights, receivers, ordering, carve, spacing, edges, 2, "core")
        lake = routed.lake.reshape(heights.shape)
        assert routed.basins == 2 and routed.lakes == 1, (routed.basins, routed.lakes)
        assert lake[12, 20] == lake[12, 30] > 0, "both pits lie in one lake"
        spill, across = routed.spill[lake[12, 20]], routed.spill_to[lake[12, 20]]
        level = max(heights.ravel()[spill], heights.ravel()[across])
        assert routed.water[12, 20] == level == routed.water[12, 30]
        assert level < 0.5 * 16 + 1.0, level
        again = kernels.order(routed.receivers, heights.shape, 1, 2, "core")
        assert kernels.route_lakes(heights, routed.receivers, again, carve, spacing, edges, 2, "core").basins == 0


run(globals())
