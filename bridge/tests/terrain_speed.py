import json
import time
from pathlib import Path

import numpy

from blendworks_bridge import terrain_kernels as kernels
from blendworks_bridge.terrain_grid import EDGE_SOUTH

CALIBRATION = Path(__file__).resolve().parents[2] / "bench" / "terrain-kernels" / "speed-calibration.json"
SLOWDOWN_FACTOR = 4.0
SIZE = 257
REPEATS = 5
SPACING = (30.0, 30.0)


def workload():
    rng = numpy.random.default_rng(31)
    row, column = numpy.mgrid[0:SIZE, 0:SIZE].astype(float)
    heights = 0.02 * row + numpy.abs(((column * 0.37 + row * 0.11) % 23.0) - 11.5) * 0.3 + rng.random((SIZE, SIZE)) * 0.5
    receivers, _ = kernels.d8(heights, SPACING, EDGE_SOUTH, 1, "core")
    ordering = kernels.order(receivers, heights.shape, 1, 1, "core")
    routed = kernels.route_lakes(heights, receivers, ordering, True, SPACING, EDGE_SOUTH, 1, "core")
    routed_order = kernels.order(routed.receivers, heights.shape, 1, 1, "core")
    weights = numpy.full(heights.size, SPACING[0] * SPACING[1])
    area = kernels.accumulate(routed_order, weights, threads=1, engine="core")
    erodibility = numpy.full(heights.size, 2e-5)
    diffusivity = numpy.full(heights.shape, 0.01)
    tangent = numpy.full(heights.shape, 0.7)
    return {
        "receivers": lambda engine: kernels.d8(heights, SPACING, EDGE_SOUTH, 1, engine),
        "ordering": lambda engine: kernels.order(routed.receivers, heights.shape, 1, 1, engine),
        "accumulation": lambda engine: kernels.accumulate(routed_order, weights, threads=1, engine=engine),
        "incision": lambda engine: kernels.incise(heights, routed.receivers, routed_order, area, erodibility, 0.45, 1.0, 1000.0, SPACING, 1, engine),
        "lake routing": lambda engine: kernels.route_lakes(heights, receivers, ordering, True, SPACING, EDGE_SOUTH, 1, engine),
        "ADI diffusion": lambda engine: kernels.diffuse(heights, diffusivity, 1000.0, SPACING, EDGE_SOUTH, threads=1, engine=engine),
        "thermal slides": lambda engine: kernels.slide(heights, tangent, 0.5, 1, SPACING, EDGE_SOUTH, 1, engine),
    }


def calibration_seconds():
    rng = numpy.random.default_rng(5)
    values = rng.random(SIZE * SIZE)
    started = time.perf_counter()
    order = numpy.argsort(values, kind="stable")
    total = numpy.cumsum(values[order])
    numpy.maximum.accumulate(total[::-1])
    return time.perf_counter() - started


def fastest(function):
    found = float("inf")
    for _ in range(REPEATS):
        started = time.perf_counter()
        function()
        found = min(found, time.perf_counter() - started)
    return found


def measured_ratios(engines=None):
    engines = engines or {}
    ratios = {}
    for name, function in workload().items():
        engine = engines.get(name, "core")
        function(engine)
        calibration = min(calibration_seconds() for _ in range(REPEATS))
        ratios[name] = fastest(lambda: function(engine)) / calibration
    return ratios


def recorded_ratios():
    return json.loads(CALIBRATION.read_text(encoding="utf-8"))["ratios"]


def slowed(ratios, recorded, factor=SLOWDOWN_FACTOR):
    return {name: ratio / recorded[name] for name, ratio in ratios.items() if ratio > factor * recorded[name]}
