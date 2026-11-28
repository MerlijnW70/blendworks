import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "..", "..", "bench", "autosave")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(BENCH, "reference"))
sys.path.insert(0, BENCH)

import bpy

from harness import run

import measures
from driver import SMALL, Driver, small_build

TARGET_SHARE = 0.03


class CpuMeter:
    """CPU time of the main thread spent inside the autosave's entry points: before and after each journaled request and
    the idle snapshot, the same calls autosave.seconds times by the wall clock. CPU time does not grow while the host
    is busy, as wall time does, so the share stays a property of the code."""

    def __init__(self, autosave):
        self.seconds = 0.0
        for name in ("before", "after", "idle"):
            setattr(autosave, name, self.timed(getattr(autosave, name)))

    def timed(self, method):
        def run(*args, **kwargs):
            started = time.thread_time()
            try:
                return method(*args, **kwargs)
            finally:
                self.seconds += time.thread_time() - started
        return run


def build(workspace, autosave_seconds):
    driver = Driver(workspace, SMALL, autosave_seconds=autosave_seconds)
    meter = CpuMeter(driver.handler.autosave)
    started, cpu = time.perf_counter(), time.thread_time()
    small_build(driver)
    wall, cpu = time.perf_counter() - started, time.thread_time() - cpu
    return driver, wall, cpu, meter, measures.geometry(bpy.context.scene)


def test_the_bench_scene_builds_the_same_geometry_with_the_journal_and_within_the_overhead_target(bridge):
    _, plain_wall, plain_cpu, _, plain = build(os.path.join(bridge.workspace, "off"), None)
    driver, wall, cpu, meter, journaled = build(os.path.join(bridge.workspace, "on"), 30.0)
    autosave = driver.handler.autosave
    print(f"build {plain_wall:.1f} s wall ({plain_cpu:.1f} s CPU) without autosave, {wall:.1f} s ({cpu:.1f} s CPU) with it; autosave {autosave.seconds:.2f} s wall, {meter.seconds:.2f} s CPU in {autosave.saves} snapshots")
    assert journaled["totals"] == plain["totals"]
    changed = sorted(name for name in plain["objects"] if journaled["objects"].get(name) != plain["objects"][name])
    assert not changed and sorted(journaled["objects"]) == sorted(plain["objects"]), changed
    assert autosave.saves >= 1 and autosave.status()["journal"]["requests"] > 0
    assert meter.seconds <= TARGET_SHARE * cpu, (meter.seconds, cpu)


run(globals())
