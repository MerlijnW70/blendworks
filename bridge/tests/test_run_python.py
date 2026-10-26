import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import Bridge, run, snapshot


def allowed(bridge):
    return Bridge(bridge.workspace, allow_python=True)


def test_run_python_is_absent_without_the_flag(bridge):
    names = [entry["name"] for entry in bridge.ok("describe")["commands"]]
    assert "run_python" not in names
    message = bridge.refuse("run_python", "forbidden", code="result = 1")
    assert "--allow-python" in message
    bridge.refuse("run_python", "forbidden", code="import bpy; bpy.ops.mesh.primitive_cube_add()")
    assert len(bpy.data.objects) == 0


def test_run_python_is_listed_as_dangerous_with_the_flag(bridge):
    python = allowed(bridge)
    described = python.ok("describe")
    assert described["python"] is True
    entry = next(entry for entry in described["commands"] if entry["name"] == "run_python")
    assert entry["dangerous"] is True
    assert "arbitrary" in entry["description"]


def test_run_python_runs_code_and_returns_result_and_stdout(bridge):
    python = allowed(bridge)
    result = python.ok("run_python", code="print('hello')\nresult = {'objects': len(bpy.data.objects), 'pi': 3.5}")
    assert result == {"stdout": "hello\n", "result": {"objects": 0, "pi": 3.5}}
    result = python.ok("run_python", code="result = bpy.data")
    assert isinstance(result["result"], str)


def test_run_python_failure_rolls_the_scene_back(bridge):
    python = allowed(bridge)
    python.ok("add_primitive", type="cube", name="Box")
    before = snapshot()
    code = (
        "box = bpy.data.objects['Box']\n"
        "box.location.x = 5\n"
        "box.name = 'Renamed'\n"
        "box.data.vertices[0].co.z = 9\n"
        "bpy.ops.mesh.primitive_monkey_add()\n"
        "bpy.data.materials.new('Stray')\n"
        "raise ValueError('boom')\n"
    )
    message = python.refuse("run_python", "failed", code=code)
    assert "boom" in message
    assert snapshot() == before


def test_run_python_refuses_bad_arguments(bridge):
    python = allowed(bridge)
    python.refuse("run_python", "bad_args")
    python.refuse("run_python", "bad_args", code="")
    python.refuse("run_python", "failed", code="def broken(:")
    python.refuse("run_python", "failed", code="raise SystemExit(3)")


run(globals())
