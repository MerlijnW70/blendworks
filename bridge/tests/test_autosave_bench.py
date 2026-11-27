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


def build(workspace, autosave_seconds):
    driver = Driver(workspace, SMALL, autosave_seconds=autosave_seconds)
    started = time.perf_counter()
    small_build(driver)
    wall = time.perf_counter() - started
    return driver, wall, measures.geometry(bpy.context.scene)


def test_the_bench_scene_builds_the_same_geometry_with_the_journal_and_within_the_overhead_target(bridge):
    _, plain_wall, plain = build(os.path.join(bridge.workspace, "off"), None)
    driver, wall, journaled = build(os.path.join(bridge.workspace, "on"), 30.0)
    autosave = driver.handler.autosave
    print(f"build {plain_wall:.1f} s without autosave, {wall:.1f} s with it; autosave {autosave.seconds:.2f} s in {autosave.saves} snapshots")
    assert journaled["totals"] == plain["totals"]
    changed = sorted(name for name in plain["objects"] if journaled["objects"].get(name) != plain["objects"][name])
    assert not changed and sorted(journaled["objects"]) == sorted(plain["objects"]), changed
    assert autosave.saves >= 1 and autosave.status()["journal"]["requests"] > 0
    assert autosave.seconds <= TARGET_SHARE * wall, (autosave.seconds, wall)


run(globals())
