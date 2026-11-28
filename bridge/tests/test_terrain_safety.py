import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy
from terrain_helpers import core_ready, raises

from blendworks_bridge import terrain_core
from blendworks_bridge import terrain_kernels as kernels
from blendworks_bridge.terrain_grid import TerrainGrid

INVALID = 1
CYCLE = 2


def native_code(function, *arguments, **keywords):
    error = raises(function, *arguments, **keywords)
    assert isinstance(error, terrain_core.NativeError), f"expected a native error, got {error!r}"
    assert error.code in (INVALID, CYCLE), f"the core reported {error}, a panic or unknown code"
    return error


def setup():
    rng = numpy.random.default_rng(4)
    heights = rng.random((12, 15)) * 9.0
    receivers, _ = kernels.d8(heights, engine="core")
    ordering = kernels.order(receivers, heights.shape, 1, engine="core")
    return heights, receivers, ordering


def raw_d8(heights_buffer, receivers_buffer, grid, threads=2):
    terrain_core.core().call("bw_d8", grid, threads, heights_buffer, receivers_buffer, terrain_core.I64(0))


def test_buffer_types_lengths_layout_and_overlap_are_checked(bridge):
    if not core_ready():
        return
    heights, _, _ = setup()
    grid = terrain_core.grid_spec(TerrainGrid.of(heights))
    good_heights = terrain_core.describe(heights)
    receivers = numpy.zeros(heights.size, dtype=numpy.int32)
    cases = {
        "float32 heights": (terrain_core.describe(heights.astype(numpy.float32)), terrain_core.describe(receivers), "float64"),
        "int64 receivers": (good_heights, terrain_core.describe(receivers.astype(numpy.int64)), "int32"),
        "short heights": (terrain_core.describe(heights.ravel()[:-1]), terrain_core.describe(receivers), "values"),
        "long receivers": (good_heights, terrain_core.describe(numpy.zeros(heights.size + 1, dtype=numpy.int32)), "values"),
        "strided heights": (terrain_core.describe(numpy.repeat(heights.ravel(), 2)[::2]), terrain_core.describe(receivers), "C-contiguous"),
    }
    read_only = numpy.zeros(heights.size, dtype=numpy.int32)
    read_only.flags.writeable = False
    cases["read-only output"] = (good_heights, terrain_core.describe(read_only), "writable")
    raw = numpy.zeros(heights.size * 8 + 8, dtype=numpy.uint8)
    misaligned = terrain_core.Buffer(raw.ctypes.data + 1, heights.size, terrain_core.KIND_FLOAT64, 8, 1, 1)
    cases["misaligned heights"] = (misaligned, terrain_core.describe(receivers), "aligned")
    cases["null data"] = (terrain_core.Buffer(None, heights.size, terrain_core.KIND_FLOAT64, 8, 1, 1), terrain_core.describe(receivers), "null")
    shared = numpy.zeros(heights.size * 2, dtype=numpy.float64)
    cases["overlapping output"] = (terrain_core.describe(shared[: heights.size]), terrain_core.Buffer(shared.ctypes.data + 8, heights.size, terrain_core.KIND_INT32, 4, 1, 1), "overlaps")
    for name, (heights_buffer, receivers_buffer, words) in cases.items():
        error = native_code(raw_d8, heights_buffer, receivers_buffer, grid)
        assert words in str(error), f"{name}: {error}"
    function = terrain_core.core().functions["bw_d8"]
    assert function(None, 1, None, None, None) == INVALID
    assert function(ctypes.byref(grid), 1, None, ctypes.byref(terrain_core.describe(receivers)), ctypes.byref(terrain_core.I64(0))) == INVALID
    assert function(ctypes.byref(grid), 1, ctypes.byref(good_heights), ctypes.byref(terrain_core.describe(receivers)), None) == INVALID


def test_grid_descriptions_and_scalar_settings_are_checked(bridge):
    if not core_ready():
        return
    heights, receivers, ordering = setup()
    for rows, columns, spacing, edges in ((0, 15, 1.0, 31), (12, -1, 1.0, 31), (2**31, 2**31, 1.0, 31), (12, 15, float("nan"), 31), (12, 15, -1.0, 31), (12, 15, 1.0, 32), (12, 15, 1.0, -1)):
        grid = terrain_core.GridSpec(rows, columns, spacing, 1.0, edges)
        native_code(raw_d8, terrain_core.describe(heights), terrain_core.describe(numpy.zeros(heights.size, dtype=numpy.int32)), grid)
    for threads in (0, 65, -3):
        native_code(kernels.d8, heights, threads=threads, engine="core")
    native_code(kernels.mfd, heights, float("nan"), engine="core")
    native_code(kernels.mfd, heights, 0.0, engine="core")
    native_code(kernels.order, numpy.full(heights.size * 9, -1, dtype=numpy.int32), heights.shape, 9, engine="core")
    area = numpy.ones(heights.size)
    for m, n, dt in ((-0.1, 1.0, 1.0), (0.5, 0.0, 1.0), (0.5, 11.0, 1.0), (0.5, 1.0, -1.0), (0.5, 1.0, float("inf"))):
        native_code(kernels.incise, heights, receivers, ordering, area, 1e-3, m, n, dt, engine="core")
    native_code(kernels.incise, heights, receivers, ordering, -area, 1e-3, 0.5, 1.0, 1.0, engine="core")
    native_code(kernels.incise, heights, receivers, ordering, area, float("nan"), 0.5, 1.0, 1.0, engine="core")
    native_code(kernels.diffuse, heights, -1.0, 1.0, engine="core")
    native_code(kernels.diffuse, heights, 1.0, float("nan"), engine="core")
    native_code(kernels.diffuse, heights, 1.0, 1.0, critical_slope=1.0, max_ratio=1.0, engine="core")
    native_code(kernels.diffuse, heights, 1.0, 1.0, critical_slope=1.0, iterations=0, engine="core")
    assert isinstance(raises(kernels.diffuse, heights, 1.0, 1.0, critical_slope=-1.0, engine="core"), ValueError)
    for rate in (0.0, 1.5, float("nan")):
        native_code(kernels.slide, heights, 0.5, rate, 1, engine="core")
    native_code(kernels.slide, heights, -0.5, 0.5, 1, engine="core")
    found = terrain_core.core()
    lakes = [numpy.empty(heights.size, dtype=numpy.int32) for _ in range(3)] + [numpy.empty(heights.shape)] + [numpy.empty(heights.size + 1, dtype=numpy.int32) for _ in range(2)]
    describe = terrain_core.describe
    error = native_code(found.call, "bw_route_lakes", terrain_core.grid_spec(TerrainGrid.of(heights)), 2, describe(heights), describe(receivers), describe(ordering.order), describe(ordering.padded_level_start()), 2, *[describe(array) for array in lakes], terrain_core.I64(0), terrain_core.I64(0))
    assert "mode" in str(error)


def test_receiver_tables_and_orders_that_are_not_graphs_are_refused(bridge):
    if not core_ready():
        return
    heights, receivers, ordering = setup()
    for value, code in ((heights.size, INVALID), (-2, INVALID)):
        broken = receivers.copy()
        broken[5] = value
        assert native_code(kernels.order, broken, heights.shape, engine="core").code == code
    own = receivers.copy()
    own[7] = 7
    assert native_code(kernels.order, own, heights.shape, engine="core").code == CYCLE
    loop = numpy.full(heights.size, -1, dtype=numpy.int32)
    loop[[0, 1, 16]] = [1, 16, 0]
    assert native_code(kernels.order, loop, heights.shape, engine="core").code == CYCLE
    for cell, value, code in ((20, heights.size, INVALID), (20, -2, INVALID), (20, 20, INVALID), (0, 1, INVALID)):
        broken = receivers.copy()
        broken[cell] = value
        assert native_code(kernels.route_lakes, heights, broken, ordering, True, engine="core").code == code, (cell, value)
    circle = receivers.copy()
    circle[[16, 17, 32]] = [17, 32, 16]
    assert native_code(kernels.route_lakes, heights, circle, ordering, True, engine="core").code == CYCLE
    twice = numpy.full(heights.size * 8, -1, dtype=numpy.int32)
    twice[[8 * 20, 8 * 20 + 1]] = 21
    native_code(kernels.order, twice, heights.shape, 8, engine="core")
    weights = numpy.ones(heights.size)
    shuffled = kernels.order(receivers, heights.shape, engine="core")
    shuffled.order[3] = shuffled.order[4]
    native_code(kernels.accumulate, shuffled, weights, engine="core")
    bad_levels = kernels.order(receivers, heights.shape, engine="core")
    bad_levels.level_start[-1] -= 1
    native_code(kernels.accumulate, bad_levels, weights, engine="core")
    bad_donors = kernels.order(receivers, heights.shape, engine="core")
    if len(bad_donors.donors):
        bad_donors.donors[0] = heights.size
        native_code(kernels.accumulate, bad_donors, weights, engine="core")
    native_code(kernels.accumulate, ordering, weights[:-1], engine="core")


def test_empty_nodata_and_extreme_grids_run_without_errors(bridge):
    if not core_ready():
        return
    shapes = [numpy.full((5, 6), numpy.nan), numpy.full((4, 4), numpy.inf), numpy.array([[1e308, -1e308, 1e308], [-1e308, 1e308, 0.0]]), numpy.array([[5e-324, -0.0, 0.0, 1e-300]]), numpy.full((1, 1), 3.0)]
    mixed = numpy.random.default_rng(2).random((9, 9)) * 1e300
    mixed[::3, ::2] = numpy.nan
    mixed[1, 1] = -numpy.inf
    shapes.append(mixed)
    for heights in shapes:
        for edges in (0, 4, 31):
            for engine in ("core", "python"):
                receivers, _ = kernels.d8(heights, edges=edges, engine=engine)
                ordering = kernels.order(receivers, heights.shape, engine=engine)
                routed = kernels.route_lakes(heights, receivers, ordering, True, edges=edges, engine=engine)
                again = kernels.order(routed.receivers, heights.shape, engine=engine)
                area = kernels.accumulate(again, numpy.ones(heights.size), engine=engine)
                kernels.incise(heights, routed.receivers, again, area, 1e-3, 0.5, 1.0, 1.0, engine=engine)
                kernels.priority_flood(heights, True, edges, engine)
                with numpy.errstate(all="ignore"):
                    kernels.diffuse(heights, 0.1, 1.0, edges=edges, engine=engine)
                    kernels.diffuse(heights, 0.1, 1.0, edges=edges, critical_slope=1.0, engine=engine)
                    kernels.slide(heights, 0.5, 0.5, 2, edges=edges, engine=engine)
        assert (kernels.d8(heights, engine="core")[0][~numpy.isfinite(heights.ravel())] == -1).all()


def test_random_corruption_never_crashes_or_panics(bridge):
    if not core_ready():
        return
    rng = numpy.random.default_rng(77)
    heights, receivers, ordering = setup()
    weights = numpy.ones(heights.size)
    refused = accepted = 0
    for trial in range(300):
        table = receivers.copy()
        positions = rng.integers(0, heights.size, int(rng.integers(1, 6)))
        table[positions] = rng.integers(-3, heights.size + 3, len(positions))
        candidate = heights.copy()
        candidate.ravel()[rng.integers(0, heights.size, 3)] = rng.choice([numpy.nan, numpy.inf, -numpy.inf, 1e308, -1e308, 0.0])
        try:
            built = kernels.order(table, heights.shape, threads=int(rng.integers(1, 5)), engine="core")
            kernels.accumulate(built, weights, threads=int(rng.integers(1, 5)), engine="core")
            kernels.incise(candidate, table, built, weights, 1e-3, 0.5, 1.0 + float(rng.random()), 2.0, engine="core")
            kernels.route_lakes(candidate, kernels.d8(candidate, engine="core")[0], kernels.order(kernels.d8(candidate, engine="core")[0], heights.shape, engine="core"), bool(trial % 2), engine="core")
            accepted += 1
        except terrain_core.NativeError as error:
            assert error.code in (INVALID, CYCLE), f"trial {trial}: {error}"
            refused += 1
    assert refused > 0 and accepted > 0, (refused, accepted)


run(globals())
