import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy
from terrain_helpers import LAKE_FIELDS, ORDER_FIELDS, grid_cases, core_ready, same_bits, same_fields

from blendworks_bridge import terrain_kernels as kernels

THREADS = 3


def both(function, *arguments, **keywords):
    return function(*arguments, threads=THREADS, engine="core", **keywords), function(*arguments, engine="python", **keywords)


def routed_graphs(heights, spacing, edges):
    receivers, _ = kernels.d8(heights, spacing, edges, THREADS, "core")
    ordering = kernels.order(receivers, heights.shape, 1, THREADS, "core")
    routed = kernels.route_lakes(heights, receivers, ordering, True, spacing, edges, THREADS, "core")
    return receivers, ordering, routed


def test_receivers_equal_the_reference_on_every_case(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        core, python = both(kernels.d8, heights, spacing, edges)
        same_bits(core[0], python[0], f"{name} d8")
        assert core[1] == python[1], (name, core[1], python[1])
        for exponent in (1.1, 4.0):
            core, python = both(kernels.mfd, heights, exponent, spacing, edges)
            same_bits(core[0], python[0], f"{name} mfd receivers p={exponent}")
            same_bits(core[1], python[1], f"{name} mfd shares p={exponent}")


def test_flats_drain_and_closed_flats_stay_pits(bridge):
    if not core_ready():
        return
    heights, spacing, edges = grid_cases()["plateau"]
    receivers, resolved = kernels.d8(heights, spacing, edges, THREADS, "core")
    assert resolved > 0
    flat = heights.ravel()
    interior = numpy.zeros(heights.shape, dtype=bool)
    interior[1:-1, 1:-1] = True
    lifted = interior.ravel() & (flat == 5.0)
    assert (receivers[lifted] >= 0).all(), "every cell of the plateau that touches its outlet must drain"
    closed = interior.ravel() & (flat == 4.0)
    assert (receivers[closed] == -1).sum() >= 1, "a closed flat floor keeps a pit"


def test_ordering_and_accumulation_equal_the_reference(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        receivers, _ = kernels.d8(heights, spacing, edges, THREADS, "core")
        weights = numpy.where(numpy.isfinite(heights), 1.25 + (numpy.arange(heights.size).reshape(heights.shape) % 5) / 3.0, 0.0).ravel()
        core, python = both(kernels.order, receivers, heights.shape, 1)
        same_fields(core, python, ORDER_FIELDS, f"{name} d8 order")
        same_bits(*both(kernels.accumulate, core, weights), f"{name} d8 accumulate")
        table, shares, _ = kernels.mfd(heights, 1.1, spacing, edges, THREADS, "core")
        core, python = both(kernels.order, table, heights.shape, 8)
        same_fields(core, python, ORDER_FIELDS, f"{name} mfd order")
        same_bits(*both(kernels.accumulate, core, weights, shares), f"{name} mfd accumulate")


def test_order_puts_every_cell_after_its_receivers_level_by_level(bridge):
    if not core_ready():
        return
    heights, spacing, edges = grid_cases()["ridges"]
    table, shares, _ = kernels.mfd(heights, 1.1, spacing, edges, THREADS, "core")
    ordering = kernels.order(table, heights.shape, 8, THREADS, "core")
    level = numpy.empty(heights.size, dtype=numpy.int64)
    for index in range(ordering.levels):
        level[ordering.level(index)] = index
    targets = table.reshape(heights.size, 8)
    for slot in range(8):
        has = targets[:, slot] >= 0
        assert (level[has] > level[targets[has, slot]]).all()
    total = kernels.accumulate(ordering, numpy.ones(heights.size), shares, THREADS, "core")
    outlets = (targets < 0).all(axis=1)
    assert abs(total[outlets].sum() - heights.size) < 1e-9 * heights.size


def test_lake_routing_equals_the_reference_in_both_modes(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        receivers, _ = kernels.d8(heights, spacing, edges, THREADS, "core")
        ordering = kernels.order(receivers, heights.shape, 1, THREADS, "core")
        for carve in (False, True):
            core, python = both(kernels.route_lakes, heights, receivers, ordering, carve, spacing, edges)
            same_fields(core, python, LAKE_FIELDS, f"{name} lakes carve={carve}")


def test_priority_flood_equals_the_reference(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        for epsilon in (False, True):
            core = kernels.priority_flood(heights, epsilon, edges, "core")
            python = kernels.priority_flood(heights, epsilon, edges, "python")
            same_bits(core[0], python[0], f"{name} flood epsilon={epsilon}")
            assert core[1] == python[1]


def test_threshold_hillslopes_equal_the_reference(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        tangent = 0.3 + (numpy.arange(heights.size).reshape(heights.shape) % 5) / 7.0
        core = kernels.threshold(heights, tangent, spacing, edges, "core")
        python = kernels.threshold(heights, tangent, spacing, edges, "python")
        same_bits(core[0], python[0], f"{name} threshold")
        assert core[1] == python[1], name
        valid = numpy.isfinite(heights)
        assert (core[0][valid] <= heights[valid]).all(), name


def test_dinf_and_incision_over_two_receivers_equal_the_reference(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        core = kernels.dinf(heights, spacing, edges, THREADS, "core")
        python = kernels.dinf(heights, spacing, edges, THREADS, "python")
        assert (core[0] == python[0]).all(), f"{name} dinf receivers"
        same_bits(core[1], python[1], f"{name} dinf shares")
        assert (numpy.count_nonzero(core[0].reshape(-1, 8) >= 0, axis=1) <= 2).all(), name
        ordering = kernels.order(core[0], heights.shape, 8, THREADS, "core")
        area = kernels.accumulate(ordering, numpy.full(heights.size, spacing[0] * spacing[1]), core[1], THREADS, "core")
        erodibility = 1e-3 * (1.0 + numpy.arange(heights.size) % 3)
        solved = [kernels.incise_many(heights, core[0], core[1], ordering, area, erodibility, 0.5, 10.0, spacing, THREADS, engine) for engine in ("core", "python")]
        same_bits(solved[0], solved[1], f"{name} incise over two receivers")

def test_incision_equals_the_reference_for_n_one_and_newton(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        _, _, routed = routed_graphs(heights, spacing, edges)
        ordering = kernels.order(routed.receivers, heights.shape, 1, THREADS, "core")
        area = kernels.accumulate(ordering, numpy.full(heights.size, spacing[0] * spacing[1]), threads=THREADS, engine="core")
        erodibility = 1e-3 * (1.0 + numpy.arange(heights.size) % 3)
        for m, n in ((0.5, 1.0), (0.45, 1.0), (0.4, 1.6), (0.5, 0.7)):
            core, python = both(kernels.incise, heights, routed.receivers, ordering, area, erodibility, m, n, 40.0, spacing)
            same_bits(core, python, f"{name} incise m={m} n={n}")


def test_diffusion_equals_the_reference_linear_and_nonlinear(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        diffusivity = 0.2 + 0.1 * (numpy.arange(heights.size) % 4)
        for dt in (0.5, 5000.0):
            same_bits(*both(kernels.diffuse, heights, diffusivity, dt, spacing, edges), f"{name} adi dt={dt}")
            same_bits(*both(kernels.diffuse, heights, diffusivity, dt, spacing, edges, critical_slope=0.9, iterations=3), f"{name} roering dt={dt}")


def test_slides_equal_the_reference(bridge):
    if not core_ready():
        return
    for name, (heights, spacing, edges) in grid_cases().items():
        tangent = 0.3 + 0.2 * (numpy.arange(heights.size) % 5)
        for iterations in (0, 1, 6):
            same_bits(*both(kernels.slide, heights, tangent, 0.6, iterations, spacing, edges), f"{name} slide iterations={iterations}")


run(globals())
