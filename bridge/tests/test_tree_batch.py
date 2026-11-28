import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bench"))

import bpy

from harness import run
from scene_digest import material_digest, scene_digest
from blendworks_bridge import workers
from blendworks_bridge.commands.scene import reset_scene

TREES = [
    {"grow": {"name": "oak", "preset": "oak", "seed": 3, "points": 300, "height": 5.0, "limit": 0}, "mesh": {}, "leaves": {"seed": 3, "detail": "low"}},
    {"grow": {"name": "birch", "preset": "birch", "seed": 4, "height": 5.0, "trunk_height": 1.5, "location": [8.0, 0.0, 0.0], "limit": 0}, "mesh": {"keep_skeleton": False}, "leaves": {"seed": 4, "detail": "low"}},
    {"grow": {"name": "pine", "preset": "pine", "seed": 5, "height": 5.0, "trunk_height": 1.5, "location": [16.0, 0.0, 0.0], "limit": 0}, "mesh": {}},
]


def state():
    bpy.context.view_layer.update()
    return {"objects": scene_digest(), "materials": material_digest(), "images": sorted(image.name for image in bpy.data.images),
            "collections": sorted(collection.name for collection in bpy.data.collections)}


def results(reply):
    return [tree["results"] for tree in reply["trees"]]


def prepared(bridge):
    bridge.ok("add_material", name="oak_bark", base_color=[0.3, 0.2, 0.1])
    bridge.ok("add_primitive", type="cube", name="stone", size=0.5, location=[0.0, -5.0, 0.0])


def serial_build(bridge):
    prepared(bridge)
    reply = bridge.ok("grow_trees", trees=TREES, parallel=False)
    return reply, state()


def test_parallel_build_equals_serial_build(bridge):
    serial, expected = serial_build(bridge)
    assert serial["workers"] == 0 and {tree["built"] for tree in serial["trees"]} == {"serial"}
    reset_scene(bpy.context.scene)
    prepared(bridge)
    parallel = bridge.ok("grow_trees", trees=TREES, workers=1)
    assert parallel["workers"] == 1 and not parallel["fallbacks"]
    assert {tree["built"] for tree in parallel["trees"]} == {"worker"}
    assert parallel["materials_reused"] >= 1 and parallel["worker_peak_memory"] > 0
    assert parallel["worker_peak_memory"] < workers.WORKER_MEMORY_BYTES
    assert results(parallel) == results(serial)
    found = state()
    assert found["objects"] == expected["objects"]
    assert found["materials"] == expected["materials"] and found["images"] == expected["images"] and found["collections"] == expected["collections"]
    assert bpy.data.objects["oak"].hide_get() and "birch" not in bpy.data.objects
    assert bpy.data.objects["oak_bark"].data.materials[0].name == "oak_bark"


def test_a_killed_worker_falls_back_to_building_serially(bridge):
    serial, expected = serial_build(bridge)
    reset_scene(bpy.context.scene)
    prepared(bridge)
    waiting = workers.Pool.wait

    def kill_first(pool, index):
        if index == 0:
            while pool.claimant(0) is None and pool.processes[0].poll() is None:
                time.sleep(0.01)
            pool.processes[0].kill()
            pool.processes[0].wait()
        return waiting(pool, index)

    workers.Pool.wait = kill_first
    try:
        reply = bridge.ok("grow_trees", trees=TREES, workers=1)
    finally:
        workers.Pool.wait = waiting
    assert [entry["tree"] for entry in reply["fallbacks"]] == [0, 1, 2]
    assert {tree["built"] for tree in reply["trees"]} == {"serial"}
    assert results(reply) == results(serial)
    assert state()["objects"] == expected["objects"]


def test_a_tree_that_fails_refuses_the_batch_and_changes_nothing(bridge):
    before = state()
    broken = [TREES[2], {"grow": {"name": "bad", "preset": "birch", "points": 10}}]
    message = bridge.refuse("grow_trees", "bad_args", trees=broken, workers=1)
    assert "points" in message
    assert state() == before


def test_names_that_clash_are_refused_before_any_work(bridge):
    bridge.ok("add_primitive", type="cube", name="pine_bark")
    message = bridge.refuse("grow_trees", "bad_args", trees=[TREES[2]], workers=1)
    assert "pine_bark already exists" in message
    clash = [{"grow": {"name": "a"}, "mesh": {}}, {"grow": {"name": "a_bark"}}]
    message = bridge.refuse("grow_trees", "bad_args", trees=clash, parallel=False)
    assert "both make an object named a_bark" in message


def test_the_plan_probes_host_memory_only_when_asked(bridge):
    calls = []

    def probe(value):
        def read():
            calls.append(value)
            return value
        return read

    assert workers.plan(6, cpus=8, probe=probe(6.5e9))["workers"] == 3
    assert workers.plan(6, cpus=8, probe=probe(6.5e9))["limited_by"] == "memory"
    assert workers.plan(6, cpus=8, probe=probe(None))["workers"] == 6
    assert workers.plan(6, cpus=8, memory=None, probe=probe(1.0))["workers"] == 6
    assert workers.plan(6, cpus=8, memory=16e9, probe=probe(1.0))["workers"] == 6
    assert calls == [6.5e9, 6.5e9, None]


def test_the_plan_follows_cpus_memory_and_tasks(bridge):
    assert workers.plan(6, cpus=4, memory=16e9)["workers"] == 4
    assert workers.plan(6, cpus=32, memory=16e9)["workers"] == 6
    assert workers.plan(6, cpus=32, memory=6.5e9) == {**workers.plan(6, cpus=32, memory=6.5e9), "workers": 3, "limited_by": "memory"}
    assert workers.plan(6, cpus=1, memory=16e9)["workers"] == 0
    assert workers.plan(6, cpus=8, memory=None)["workers"] == 6
    assert workers.plan(6, requested=1, cpus=8, memory=16e9)["workers"] == 1
    assert workers.plan(8, cpus=4, memory=16e9)["threads"] == 1 and workers.plan(2, cpus=8, memory=16e9)["threads"] == 4
    assert workers.cgroup_cpus("400000 100000") == 4 and workers.cgroup_cpus("max 100000") is None
    assert workers.cgroup_memory_free("8589934592\n", "1073741824\n") == 7516192768 and workers.cgroup_memory_free("max\n", "1\n") is None
    assert workers.meminfo_available("MemTotal: 100 kB\nMemAvailable:    2048 kB\n") == 2048 * 1024


run(globals())
