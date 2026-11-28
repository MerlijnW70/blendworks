import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy
from terrain_helpers import LAKE_FIELDS, ORDER_FIELDS, digest, core_ready, ridge_terrain, same_bits

from blendworks_bridge import terrain_kernels as kernels

THREAD_COUNTS = (1, 2, 4, 7)
SPACING = (2.0, 2.5)
EDGES = 4 | 8
GOLDEN = {
    "d8": "e11e7e11ab1ec702",
    "mfd": "db04f0c8686b6533",
    "order": "d3e629d1ed290dea",
    "mfd order": "963ae5b250fdeb28",
    "mfd accumulate": "b6ecf35d43a2b780",
    "lakes carve=False": "fe431a146a54fc8e",
    "lakes carve=True": "9f6b09db24c156fb",
    "routed order": "6823f7d7ec13a608",
    "accumulate": "4536acecf435a8a3",
    "incise n=1.0": "edb8f3d419590c32",
    "incise n=1.4": "3a7d2a47f03b97b4",
    "adi": "c7958ca64ad875a2",
    "roering": "b3974718ea9c972c",
    "slide": "ee37cdd6a46a7eca",
    "flood": "a8075a1b64f80ec6",
}


def terrain():
    heights = ridge_terrain(260, 300, 11) * 3.0
    rng = numpy.random.default_rng(12)
    heights += numpy.floor(rng.random(heights.shape) * 4.0) * 0.25
    heights[100:104, 50:60] = numpy.nan
    return heights


def outputs(threads):
    heights = terrain()
    found = {}
    receivers, resolved = kernels.d8(heights, SPACING, EDGES, threads, "core")
    found["d8"] = (receivers, resolved)
    table, shares, _ = kernels.mfd(heights, 1.1, SPACING, EDGES, threads, "core")
    found["mfd"] = (table, shares)
    ordering = kernels.order(receivers, heights.shape, 1, threads, "core")
    found["order"] = tuple(getattr(ordering, name) for name in ORDER_FIELDS)
    mfd_ordering = kernels.order(table, heights.shape, 8, threads, "core")
    found["mfd order"] = tuple(getattr(mfd_ordering, name) for name in ORDER_FIELDS)
    weights = numpy.where(numpy.isfinite(heights), 5.0 + (numpy.arange(heights.size).reshape(heights.shape) % 7) / 3.0, 0.0).ravel()
    found["mfd accumulate"] = (kernels.accumulate(mfd_ordering, weights, shares, threads, "core"),)
    for carve in (False, True):
        routed = kernels.route_lakes(heights, receivers, ordering, carve, SPACING, EDGES, threads, "core")
        found[f"lakes carve={carve}"] = tuple(getattr(routed, name) for name in LAKE_FIELDS)
    routed_order = kernels.order(routed.receivers, heights.shape, 1, threads, "core")
    found["routed order"] = tuple(getattr(routed_order, name) for name in ORDER_FIELDS)
    area = kernels.accumulate(routed_order, weights, threads=threads, engine="core")
    found["accumulate"] = (area,)
    for n in (1.0, 1.4):
        found[f"incise n={n}"] = (kernels.incise(heights, routed.receivers, routed_order, area, 2e-3, 0.45, n, 10.0, SPACING, threads, "core"),)
    found["adi"] = (kernels.diffuse(heights, 0.3, 50.0, SPACING, EDGES, threads=threads, engine="core"),)
    found["roering"] = (kernels.diffuse(heights, 0.3, 50.0, SPACING, EDGES, critical_slope=1.2, threads=threads, engine="core"),)
    found["slide"] = (kernels.slide(heights, 0.5 + 0.25 * (numpy.arange(heights.size) % 3), 0.5, 4, SPACING, EDGES, threads, "core"),)
    found["flood"] = kernels.priority_flood(heights, True, EDGES, "core")
    return found


def test_the_grid_exercises_the_parallel_level_sweeps(bridge):
    if not core_ready():
        return
    heights = terrain()
    receivers, _ = kernels.d8(heights, SPACING, EDGES, 1, "core")
    ordering = kernels.order(receivers, heights.shape, 1, 1, "core")
    sizes = numpy.diff(ordering.level_start)
    assert (sizes >= 256).sum() >= 3 and (sizes < 256).sum() >= 3, sizes[:20]


def test_every_kernel_gives_identical_outputs_at_every_thread_count(bridge):
    if not core_ready():
        return
    reference = outputs(1)
    for threads in THREAD_COUNTS[1:]:
        found = outputs(threads)
        for name, values in reference.items():
            for index, value in enumerate(values):
                same_bits(found[name][index], value, f"{name} part {index} at {threads} threads")


def test_outputs_match_the_digests_recorded_on_another_platform(bridge):
    if not core_ready():
        return
    found = {name: digest(*values) for name, values in outputs(1).items()}
    differ = {name: (found.get(name), value) for name, value in GOLDEN.items() if found.get(name) != value}
    assert not differ, f"digests (found, recorded) that differ: {differ}"
    assert set(GOLDEN) == set(found), sorted(set(found) ^ set(GOLDEN))


run(globals())
