import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import Bridge, run

from blendworks_bridge.autosave import interval_from_environment


def saving(bridge, seconds=0.0, allow_python=False):
    return Bridge(bridge.workspace, allow_python=allow_python, autosave_seconds=seconds)


def files(bridge):
    folder = os.path.join(bridge.workspace, ".blendworks")
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def meta(bridge, name="autosave.json"):
    with open(os.path.join(bridge.workspace, ".blendworks", name), encoding="utf-8") as handle:
        return json.load(handle)


def test_mutating_commands_autosave_atomically_and_keep_the_previous_one(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="First")
    assert files(session) == ["autosave.blend", "autosave.json"]
    assert meta(session)["reason"] == "after add_primitive" and meta(session)["objects"] == 1
    session.ok("add_primitive", type="cube", name="Second")
    assert files(session) == ["autosave.blend", "autosave.json", "autosave.prev.blend", "autosave.prev.json"]
    assert meta(session)["objects"] == 2 and meta(session, "autosave.prev.json")["objects"] == 1
    size = os.path.getsize(os.path.join(session.workspace, ".blendworks", "autosave.blend"))
    assert meta(session)["bytes"] == size


def test_read_only_commands_do_not_autosave(bridge):
    session = saving(bridge)
    session.ok("scene_info")
    session.ok("render_preview", resolution=64, samples=1, device="cpu")
    assert files(session) == []


def test_saves_are_throttled_but_always_made_before_a_slow_command(bridge):
    session = saving(bridge, seconds=3600.0)
    session.ok("add_primitive", type="cube", name="A")
    assert meta(session)["reason"] == "after add_primitive"
    session.ok("add_primitive", type="cube", name="B")
    assert meta(session)["objects"] == 1
    status = session.ok("scene_info")["autosave"]
    assert status["unsaved_changes"] is True and status["interval_seconds"] == 3600.0
    session.ok("export", path="ab.glb")
    assert meta(session)["reason"] == "before export" and meta(session)["objects"] == 2
    session.ok("export", path="ab2.glb")
    assert meta(session)["reason"] == "before export"
    assert session.ok("scene_info")["autosave"]["unsaved_changes"] is False


def test_run_python_is_slow_so_the_scene_is_saved_before_it_runs(bridge):
    session = saving(bridge, seconds=3600.0, allow_python=True)
    session.ok("add_primitive", type="cube", name="A")
    session.ok("add_primitive", type="cube", name="B")
    session.ok("run_python", code="result = 1")
    assert meta(session)["reason"] == "before run_python" and meta(session)["objects"] == 2


def test_a_failed_command_leaves_the_autosave_state_alone(bridge):
    session = saving(bridge, seconds=3600.0)
    session.ok("add_primitive", type="cube", name="A")
    session.refuse("delete", "not_found", names=["Ghost"])
    assert session.ok("scene_info")["autosave"]["unsaved_changes"] is False


def test_recover_reloads_the_autosave(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="Kept", location=[1.0, 2.0, 3.0])
    bpy.data.objects.remove(bpy.data.objects["Kept"])
    result = session.ok("recover")
    assert result["restored"] is True and result["path"] == ".blendworks/autosave.blend"
    assert result["reason"] == "after add_primitive" and result["objects"] == 1 and result["saved_at"].endswith("Z")
    assert list(bpy.data.objects["Kept"].location) == [1.0, 2.0, 3.0]


def test_recover_falls_back_to_the_previous_autosave(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="Old")
    session.ok("add_primitive", type="cube", name="New")
    with open(os.path.join(session.workspace, ".blendworks", "autosave.blend"), "wb") as handle:
        handle.write(b"BLENDER-v999 broken")
    result = session.ok("recover")
    assert result["restored"] is True and result["path"] == ".blendworks/autosave.prev.blend"
    assert result["skipped"] and "autosave.blend" in result["skipped"][0]
    assert sorted(obj.name for obj in bpy.data.objects) == ["Old"]


def test_recover_without_an_autosave_says_so(bridge):
    session = saving(bridge)
    result = session.ok("recover")
    assert result == {"restored": False, "reason": "there was no autosave yet"}


def test_the_desktop_add_on_does_not_autosave_or_recover(bridge):
    desktop = Bridge(bridge.workspace, desktop=True, autosave_seconds=0.0)
    desktop.ok("add_primitive", type="cube")
    assert files(desktop) == []
    assert desktop.ok("scene_info")["autosave"] == {"enabled": False}
    desktop.refuse("recover", "forbidden")
    bridge.refuse("recover", "bad_args", path="x.blend")


def test_the_interval_comes_from_the_environment(bridge):
    assert interval_from_environment({}) == 30.0
    assert interval_from_environment({"BLENDWORKS_AUTOSAVE_SECONDS": "5"}) == 5.0
    assert interval_from_environment({"BLENDWORKS_AUTOSAVE_SECONDS": "off"}) is None
    assert interval_from_environment({"BLENDWORKS_AUTOSAVE_SECONDS": "-3"}) == 30.0
    assert interval_from_environment({"BLENDWORKS_AUTOSAVE_SECONDS": "soon"}) == 30.0

run(globals())
