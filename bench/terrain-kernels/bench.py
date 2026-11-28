import json
import os
import platform
import sys
import time

BRIDGE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bridge"))
sys.path.insert(0, BRIDGE)

import numpy

from blendworks_bridge import terrain_core
from blendworks_bridge import terrain_kernels as kernels
from blendworks_bridge.terrain_grid import EDGE_SOUTH

DOMAIN = 61440.0
UPLIFT = 2e-3
ERODIBILITY = 2e-5
AREA_EXPONENT = 0.45
STEP_YEARS = 1000.0
COARSE = 257
COARSE_STEPS = 300
NOISE = 2e-4
TARGETS = {"stream-power step": 0.5, "lake routing": 1.0, "ADI diffusion": 0.3}
SPEEDUP = 2.5
SERIAL = {"Priority-Flood+epsilon"}
# Stated exceptions to the speedup rule, with the evidence in docs/terrain-core.md: on the judge
# machine these kernels are bound by memory parallelism, not by threads.
MEMORY_BOUND = {"accumulation", "ADI diffusion", "non-linear diffusion (3 Picard)"}
# A sum of kernels that are judged on their own rows.
SUMS = {"stream-power step"}


def coarse_landscape(seed):
    rng = numpy.random.default_rng(seed)
    heights = rng.random((COARSE, COARSE))
    spacing = DOMAIN / (COARSE - 1)
    for _ in range(COARSE_STEPS):
        receivers, _ = kernels.d8(heights, (spacing, spacing), EDGE_SOUTH, 4, "core")
        ordering = kernels.order(receivers, heights.shape, 1, 4, "core")
        routed = kernels.route_lakes(heights, receivers, ordering, True, (spacing, spacing), EDGE_SOUTH, 4, "core")
        ordering = kernels.order(routed.receivers, heights.shape, 1, 4, "core")
        area = kernels.accumulate(ordering, numpy.full(heights.size, spacing * spacing), threads=4, engine="core")
        lifted = heights + numpy.where(routed.receivers.reshape(heights.shape) >= 0, UPLIFT * STEP_YEARS, 0.0)
        heights = kernels.incise(lifted, routed.receivers, ordering, area, ERODIBILITY, AREA_EXPONENT, 1.0, STEP_YEARS, (spacing, spacing), 4, "core")
    return heights


def upsample(heights, size):
    count = heights.shape[0]
    position = numpy.linspace(0.0, count - 1.0, size)
    index = numpy.minimum(numpy.floor(position).astype(numpy.int64), count - 2)
    fraction = position - index
    rows = heights[index] * (1.0 - fraction)[:, None] + heights[index + 1] * fraction[:, None]
    return rows[:, index] * (1.0 - fraction)[None, :] + rows[:, index + 1] * fraction[None, :]


def terrain(size):
    heights = upsample(coarse_landscape(1), size)
    rng = numpy.random.default_rng(2)
    return heights + rng.random(heights.shape) * numpy.ptp(heights) * NOISE


def fastest(function, repeats):
    found = float("inf")
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        found = min(found, time.perf_counter() - started)
    return found


def measure(heights, threads, repeats):
    spacing = (DOMAIN / (heights.shape[0] - 1),) * 2
    count = heights.size
    receivers, _ = kernels.d8(heights, spacing, EDGE_SOUTH, threads, "core")
    ordering = kernels.order(receivers, heights.shape, 1, threads, "core")
    routed = kernels.route_lakes(heights, receivers, ordering, True, spacing, EDGE_SOUTH, threads, "core")
    routed_order = kernels.order(routed.receivers, heights.shape, 1, threads, "core")
    weights = numpy.full(count, spacing[0] * spacing[1])
    area = kernels.accumulate(routed_order, weights, threads=threads, engine="core")
    erodibility = numpy.full(count, ERODIBILITY)
    diffusivity = numpy.full(heights.shape, 0.01)
    tangent = numpy.full(heights.shape, 0.7)
    table, shares, _ = kernels.mfd(heights, 1.1, spacing, EDGE_SOUTH, threads, "core")
    mfd_order = kernels.order(table, heights.shape, 8, threads, "core")
    cases = {
        "receivers (D8)": lambda: kernels.d8(heights, spacing, EDGE_SOUTH, threads, "core"),
        "ordering (queue with levels)": lambda: kernels.order(routed.receivers, heights.shape, 1, threads, "core"),
        "accumulation": lambda: kernels.accumulate(routed_order, weights, threads=threads, engine="core"),
        "incision n = 1": lambda: kernels.incise(heights, routed.receivers, routed_order, area, erodibility, AREA_EXPONENT, 1.0, STEP_YEARS, spacing, threads, "core"),
        "lake routing": lambda: kernels.route_lakes(heights, receivers, ordering, True, spacing, EDGE_SOUTH, threads, "core"),
        "ADI diffusion": lambda: kernels.diffuse(heights, diffusivity, STEP_YEARS, spacing, EDGE_SOUTH, threads=threads, engine="core"),
        "non-linear diffusion (3 Picard)": lambda: kernels.diffuse(heights, diffusivity, STEP_YEARS, spacing, EDGE_SOUTH, critical_slope=0.6, iterations=3, threads=threads, engine="core"),
        "thermal slides (1 iteration)": lambda: kernels.slide(heights, tangent, 0.5, 1, spacing, EDGE_SOUTH, threads, "core"),
        "incision n = 1.5 (Newton)": lambda: kernels.incise(heights, routed.receivers, routed_order, area, erodibility, AREA_EXPONENT, 1.5, STEP_YEARS, spacing, threads, "core"),
        "receivers (multiple flow)": lambda: kernels.mfd(heights, 1.1, spacing, EDGE_SOUTH, threads, "core"),
        "ordering (multiple flow)": lambda: kernels.order(table, heights.shape, 8, threads, "core"),
        "accumulation (multiple flow)": lambda: kernels.accumulate(mfd_order, weights, shares, threads, "core"),
    }
    if threads == 1:
        cases["Priority-Flood+epsilon"] = lambda: kernels.priority_flood(heights, True, EDGE_SOUTH, "core")
    found = {name: fastest(function, repeats) / count * 1e6 for name, function in cases.items()}
    found["stream-power step"] = sum(found[name] for name in ("receivers (D8)", "ordering (queue with levels)", "accumulation", "incision n = 1"))
    shape = {"basins": routed.basins, "levels": routed_order.levels, "pits_levels": ordering.levels}
    return found, shape


def rows(single, multi):
    found = []
    for name, value in single.items():
        speedup = single[name] / multi[name] if name in multi else None
        target = TARGETS.get(name)
        exception = "serial" if name in SERIAL else "memory-bound" if name in MEMORY_BOUND else "sum" if name in SUMS else None
        passes = (target is None or value <= target) and (exception is not None or speedup >= SPEEDUP)
        found.append({"kernel": name, "one": value, "four": multi.get(name), "speedup": speedup, "target": target, "exception": exception, "pass": bool(passes)})
    return found


def main():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    output, size, repeats = arguments[0], int(arguments[1]), int(arguments[2])
    terrain_core.require()
    started = time.perf_counter()
    heights = terrain(size)
    built = time.perf_counter() - started
    single, shape = measure(heights, 1, repeats)
    multi, _ = measure(heights, 4, repeats)
    result = {"size": size, "repeats": repeats, "cpus": os.cpu_count(), "platform": platform.platform(), "terrain_seconds": built, "shape": shape, "rows": rows(single, multi)}
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)


main()
