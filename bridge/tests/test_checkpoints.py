import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import Bridge, run

MARKER_SCRIPT = """
import os
open(os.path.join(os.path.dirname(__import__('bpy').data.filepath), 'ran.txt'), 'w').write('scripts ran')
"""


def names():
    return sorted(obj.name for obj in bpy.context.scene.objects)


def test_checkpoints_save_list_and_restore(bridge):
    bridge.ok("add_primitive", type="cube", name="Base")
    saved = bridge.ok("checkpoint", name="base-1")
    assert saved["path"] == ".blendworks/checkpoints/base-1.blend" and saved["replaced"] is False and saved["bytes"] > 0
    bridge.ok("add_primitive", type="cube", name="Later", location=[3.0, 0.0, 0.0])
    listed = bridge.ok("scene_info", detail="summary")["checkpoints"]
    assert [entry["name"] for entry in listed] == ["base-1"] and listed[0]["saved_at"].endswith("Z")
    restored = bridge.ok("restore_checkpoint", name="base-1")
    assert restored["name"] == "base-1" and restored["objects"] == 1
    assert names() == ["Base"]
    again = bridge.ok("checkpoint", name="base-1")
    assert again["replaced"] is True
    assert not any(name.endswith(".partial.blend") for name in os.listdir(os.path.join(bridge.workspace, ".blendworks", "checkpoints")))


def test_restoring_a_checkpoint_updates_the_autosave(bridge):
    session = Bridge(bridge.workspace, autosave_seconds=3600.0)
    session.ok("add_primitive", type="cube", name="Base")
    session.ok("checkpoint", name="one")
    session.ok("add_primitive", type="cube", name="Extra")
    session.ok("restore_checkpoint", name="one")
    bpy.data.objects.remove(bpy.data.objects["Base"])
    result = session.ok("recover")
    assert result["snapshot"]["reason"] == "after restore_checkpoint" and result["replayed"]["requests"] == 0
    assert names() == ["Base"]


def test_checkpoint_refusals(bridge):
    bridge.ok("add_primitive", type="cube")
    for bad in ("../escape", "has space", ".hidden", "a" * 65, "trailing."):
        bridge.refuse("checkpoint", "bad_args", name=bad)
    bridge.refuse("restore_checkpoint", "not_found", name="never")
    bridge.refuse("restore_checkpoint", "bad_args", name="../../x")
    bridge.refuse("checkpoint", "bad_args")
    assert not os.path.exists(os.path.join(bridge.workspace, ".blendworks", "checkpoints"))


def test_load_blend_opens_a_saved_file_and_refuses_bad_paths(bridge):
    bridge.ok("add_primitive", type="cube", name="Saved")
    bridge.ok("save_blend", path="files/scene.blend")
    bridge.ok("new_scene")
    loaded = bridge.ok("load_blend", path="files/scene.blend")
    assert loaded["path"] == "files/scene.blend" and loaded["objects"] == 1
    assert names() == ["Saved"]
    bridge.ok("add_primitive", type="cube", name="After")
    assert names() == ["After", "Saved"]
    bridge.refuse("load_blend", "not_found", path="missing.blend")
    bridge.refuse("load_blend", "forbidden", path="../outside.blend")
    bridge.refuse("load_blend", "forbidden", path="scene.glb")
    with open(os.path.join(bridge.workspace, "fake.blend"), "wb") as handle:
        handle.write(b"not a blend file")
    bridge.refuse("load_blend", "failed", path="fake.blend")
    assert names() == ["After", "Saved"]


def test_load_blend_never_runs_the_file_s_scripts(bridge):
    bridge.ok("add_primitive", type="cube", name="Trap")
    text = bpy.data.texts.new("startup.py")
    text.write(MARKER_SCRIPT)
    text.use_module = True
    bridge.ok("save_blend", path="trap.blend")
    bpy.data.texts.remove(text)
    bridge.ok("new_scene")
    bridge.ok("load_blend", path="trap.blend")
    assert names() == ["Trap"]
    assert "startup.py" in bpy.data.texts
    assert not os.path.exists(os.path.join(bridge.workspace, "ran.txt"))
    assert bpy.app.autoexec_fail is True


def test_the_desktop_refuses_to_drop_unsaved_changes(bridge):
    bridge.ok("add_primitive", type="cube", name="Saved")
    bridge.ok("save_blend", path="desk.blend")
    desktop = Bridge(bridge.workspace, desktop=True)
    desktop.ok("add_primitive", type="cube", name="Unsaved")
    assert bpy.data.is_dirty
    desktop.refuse("load_blend", "forbidden", path="desk.blend")
    desktop.refuse("restore_checkpoint", "not_found", name="none")
    desktop.ok("load_blend", path="desk.blend", discard_unsaved=True)
    assert names() == ["Saved"]


run(globals())
