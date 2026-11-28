import hashlib

import numpy

from blendworks_bridge import terrain_core
from blendworks_bridge import terrain_kernels as kernels
from blendworks_bridge.terrain_grid import EDGE_ALL, EDGE_EAST, EDGE_NODATA, EDGE_SOUTH, EDGE_WEST

ORDER_FIELDS = ("order", "level_start", "donor_start", "donors")
LAKE_FIELDS = ("receivers", "basin", "lake", "water", "spill", "spill_to", "basins", "lakes")


def core_ready():
    if terrain_core.core() is not None:
        return True
    reason = terrain_core.STATE.get("reason")
    assert not terrain_core.required(), f"the native core is required here and did not load: {reason}"
    print(f"skip: the native core is not loaded ({reason}), so there is nothing to compare with the Python reference")
    return False


def bowl(rows, columns, depth=10.0):
    row, column = numpy.mgrid[0:rows, 0:columns]
    return depth * (((row - (rows - 1) / 2) / rows) ** 2 + ((column - (columns - 1) / 2) / columns) ** 2)


def ridge_terrain(rows, columns, seed):
    rng = numpy.random.default_rng(seed)
    row, column = numpy.mgrid[0:rows, 0:columns].astype(float)
    tilt = 0.4 * row + 0.1 * column
    ridges = numpy.abs(((column * 0.37 + row * 0.11) % 9.0) - 4.5) * 1.5
    return tilt + ridges + rng.random((rows, columns)) * 2.0


def grid_cases():
    rng = numpy.random.default_rng(20261127)
    cases = {"random": (rng.random((23, 31)) * 10.0, (1.0, 1.0), EDGE_ALL)}
    cases["anisotropic"] = (rng.random((17, 13)) * 5.0, (0.7, 1.3), EDGE_SOUTH | EDGE_WEST)
    cases["flats"] = (numpy.floor(rng.random((25, 25)) * 3.0), (1.0, 1.0), EDGE_ALL)
    plateau = numpy.full((21, 24), 5.0)
    plateau[0, 11] = 1.0
    plateau[8:12, 6:9] = 7.0
    plateau[15:18, 15:20] = 4.0
    cases["plateau"] = (plateau, (1.0, 1.0), EDGE_ALL)
    pits = bowl(21, 27) + rng.random((21, 27)) * 0.1
    pits[rng.integers(1, 20, 12), rng.integers(1, 26, 12)] -= 3.0
    cases["pits"] = (pits, (2.0, 2.0), EDGE_ALL)
    nested = -bowl(31, 31, 20.0) + 25.0
    nested[8:23, 8:23] = 4.0 + bowl(15, 15, 6.0)
    nested[13:18, 13:18] = 1.0 + bowl(5, 5, 1.0)
    nested[15, 0] = 2.0
    cases["nested"] = (nested, (1.0, 1.0), EDGE_WEST)
    holes = rng.random((19, 22)) * 8.0
    holes[rng.random(holes.shape) < 0.2] = numpy.nan
    holes[4, 4] = numpy.inf
    holes[10, 3:9] = numpy.nan
    cases["nodata"] = (holes, (1.0, 1.0), EDGE_ALL)
    walled = rng.random((18, 20)) * 6.0
    walled[6:12, 6] = numpy.nan
    walled[6:12, 13] = -numpy.inf
    walled[6, 6:14] = numpy.nan
    walled[11, 6:14] = numpy.nan
    cases["walled"] = (walled, (1.0, 1.0), EDGE_EAST)
    cases["closed"] = (rng.random((15, 16)) * 3.0, (1.0, 1.0), 0)
    for shape in ((1, 1), (1, 9), (9, 1), (2, 2), (3, 17)):
        cases[f"border{shape[0]}x{shape[1]}"] = (rng.random(shape) * 4.0, (1.0, 1.0), EDGE_ALL)
    cases["constant"] = (numpy.full((6, 7), 3.0), (1.0, 1.0), EDGE_ALL | EDGE_NODATA)
    cases["ridges"] = (ridge_terrain(28, 33, 7), (1.5, 1.5), EDGE_SOUTH)
    return cases


def same_bits(actual, expected, label=""):
    actual = numpy.asarray(actual)
    expected = numpy.asarray(expected)
    assert actual.shape == expected.shape, f"{label}: shape {actual.shape} vs {expected.shape}"
    if actual.dtype.kind == "f" or expected.dtype.kind == "f":
        actual, expected = actual.astype(numpy.float64), expected.astype(numpy.float64)
        both_nan = numpy.isnan(actual) & numpy.isnan(expected)
        differ = (actual.view(numpy.int64) != expected.view(numpy.int64)) & ~both_nan
    else:
        differ = actual.astype(numpy.int64) != expected.astype(numpy.int64)
    assert not differ.any(), f"{label}: {int(differ.sum())} values differ, first at {numpy.argwhere(differ)[0].tolist()}: {actual[differ][:3]} vs {expected[differ][:3]}"


def same_fields(actual, expected, fields, label):
    for name in fields:
        same_bits(getattr(actual, name), getattr(expected, name), f"{label} {name}")


def digest(*arrays):
    found = hashlib.sha256()
    for array in arrays:
        array = numpy.asarray(array)
        kind = "<f8" if array.dtype.kind == "f" else "<i8"
        found.update(numpy.ascontiguousarray(array, dtype=kind).tobytes())
    return found.hexdigest()[:16]


def raises(function, *arguments, **keywords):
    try:
        function(*arguments, **keywords)
    except Exception as error:
        return error
    raise AssertionError(f"{getattr(function, '__name__', function)} accepted {arguments!r} {keywords!r}")


def stream_power_run(heights, spacing, edges, uplift, erodibility, m, n, dt, steps, threads=2, engine="auto"):
    heights = numpy.array(heights, dtype=float)
    dx, dy = spacing
    for _ in range(steps):
        receivers, _ = kernels.d8(heights, spacing, edges, threads, engine)
        ordering = kernels.order(receivers, heights.shape, 1, threads, engine)
        routed = kernels.route_lakes(heights, receivers, ordering, True, spacing, edges, threads, engine)
        ordering = kernels.order(routed.receivers, heights.shape, 1, threads, engine)
        area = kernels.accumulate(ordering, numpy.where(numpy.isfinite(heights), dx * dy, 0.0).ravel(), threads=threads, engine=engine)
        lifted = heights + numpy.where(routed.receivers.reshape(heights.shape) >= 0, uplift * dt, 0.0)
        heights = kernels.incise(lifted, routed.receivers, ordering, area, erodibility, m, n, dt, spacing, threads, engine)
    return heights
