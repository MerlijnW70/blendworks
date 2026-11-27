import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run

from blendworks_bridge import limits

REPLY_BYTES = 2 * 1024 * 1024


def problems(bridge, calls, from_scene=False):
    return bridge.ok("validate", calls=calls, from_scene=from_scene)["problems"]


def where(found):
    return [(problem["call"], problem["argument"]) for problem in found]


def test_a_huge_bad_input_gives_a_bounded_refusal(bridge):
    vertices = [[0.0, 0.0, "x"]] * 100_000
    reply = bridge.call("mesh_from_data", name="m", vertices=vertices, faces=[[0, 1, 2]])
    assert not reply["ok"] and len(json.dumps(reply)) < REPLY_BYTES // 8, len(json.dumps(reply))
    assert "more problem(s) not listed (limit problems)" in reply["error"]["message"]
    plan = [{"cmd": "add_primitive", "args": {"type": "cube", "location": [1e9, 1e9, 1e9], "size": -1.0, "bogus": 1}}] * 5_000
    result = bridge.ok("validate", calls=plan, from_scene=False)
    assert len(json.dumps(result)) < REPLY_BYTES, len(json.dumps(result))
    assert len(result["problems"]) == limits.MAX_PLAN_PROBLEMS + 1
    closing = result["problems"][-1]
    assert closing["limit"]["name"] == "plan_problems" and "more problem(s)" in closing["message"], closing


def test_validate_follows_delete_and_select(bridge):
    plan = [
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "box"}},
        {"cmd": "delete", "args": {"names": ["box"]}},
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "box"}},
        {"cmd": "select", "args": {"names": ["box"], "active": "box"}},
    ]
    assert problems(bridge, plan) == []
    gone = [plan[0], plan[1], {"cmd": "transform", "args": {"name": "box", "location": [1.0, 0.0, 0.0]}},
            {"cmd": "delete", "args": {"names": ["ghost"]}}, {"cmd": "select", "args": {"names": ["ghost"], "active": "nobody"}}]
    assert where(problems(bridge, gone)) == [(2, "args.name"), (3, "args.names[0]"), (4, "args.names[0]"), (4, "args.active")]


def test_validate_checks_timeouts_join_targets_python_and_nesting(bridge):
    found = problems(bridge, [
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "a", "timeout_seconds": 100_000}},
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "b", "timeout_seconds": 30}},
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "c"}},
        {"cmd": "join", "args": {"names": ["b", "c"], "target": "b"}},
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "c"}},
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "d"}},
        {"cmd": "join", "args": {"names": ["b", "c"], "target": "d"}},
        {"cmd": "run_python", "args": {"code": "pass"}},
        {"cmd": "validate", "args": {"calls": []}},
    ])
    assert where(found) == [(0, "args.timeout_seconds"), (6, "args.target"), (7, "cmd"), (8, "cmd")], found
    assert "--allow-python" in found[2]["message"] and "cannot check a validate call" in found[3]["message"]


def test_rules_that_need_several_arguments_refuse_in_both_paths(bridge):
    far = {"name": "t", "size": [200_000.0, 200_000.0], "tile": [1000, 1000], "resolution": 3, "height": 1.0}
    message = bridge.refuse("heightfield", "bad_args", **far)
    assert "args.tile[0]" in message and "coordinate limit" in message, message
    found = problems(bridge, [{"cmd": "heightfield", "args": far}])
    assert where(found) == [(0, "args.tile[0]"), (0, "args.tile[1]")], found
    assert "t" not in bpy.data.objects
    bridge.ok("heightfield", name="edge", size=[100_000.0, 100_000.0], tile=[1, -2], resolution=3, height=1.0)


def test_names_are_counted_in_bytes_where_blender_counts_bytes(bridge):
    wide = "é" * 200
    assert len(wide) <= limits.NAME_LENGTH < len(wide.encode("utf-8"))
    message = bridge.refuse("add_primitive", "bad_args", type="cube", name=wide)
    assert "bytes in UTF-8; got 400" in message and "limit name_length" in message, message
    bridge.ok("add_primitive", type="cube", name="é" * 127)


run(globals())
