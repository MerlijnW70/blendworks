import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from autosave_helpers import commands, entries, files, folder, meta, saving, touch_later, write_png
from fingerprint import differences, fingerprint
from harness import Bridge, run

from blendworks_bridge import autosave as autosave_module
from blendworks_bridge.commands.scene import reset_scene


class Crash(BaseException):
    pass


def scene_print(session):
    session.ok("scene_info")
    return fingerprint()


def restarted(session, allow_python=False):
    return Bridge(session.workspace, allow_python=allow_python, autosave_seconds=session.handler.autosave.interval)


def assert_same(before, after):
    found = differences(before, after)
    assert not found, found


def build(session):
    session.ok("material_procedural", name="ground", grass_ground={"density": 0.75, "dryness": 0.2})
    session.ok("heightfield", name="land", size=[20.0, 20.0], resolution=41, height=2.0, seed=5)
    session.ok("noise_displace", name="land", amplitude=0.3, seed=6)
    session.ok("assign_material", name="land", material="ground")
    session.ok("add_primitive", type="ico_sphere", name="rock", radius=0.5, subdivisions=1)
    session.ok("chip", name="rock", count=6, depth=0.12, seed=7)
    session.ok("add_primitive", type="cube", name="gone")
    session.ok("delete", names=["gone"])
    session.ok("add_primitive", type="cube", name="gone", location=[3.0, 0.0, 0.0])


def test_recovery_replays_the_journal_to_the_same_scene(bridge):
    session = saving(bridge, seconds=3600.0)
    build(session)
    spare = bpy.data.meshes.new("Spare")
    assert spare.users == 0
    assert session.handler.autosave.snapshot("test")
    session.ok("add_primitive", type="cube", name="Spare", location=[0.0, 4.0, 0.0])
    session.ok("transform", name="rock", location=[1.0, 2.0, 0.5], rotation=[0.0, 0.0, 30.0])
    before = scene_print(session)
    assert [mesh.name for mesh in bpy.data.meshes if mesh.name.startswith("Spare")] == ["Spare", "Spare.001"]
    result = restarted(session).ok("recover")
    assert result["restored"] is True and result["path"] == ".blendworks/autosave-2.blend"
    assert result["replayed"]["requests"] == 2 and result["snapshot"]["reason"] == "test"
    assert result["reason"] == "snapshot test, then 2 journaled requests replayed, the last transform"
    assert "not_replayed" not in result
    assert_same(before, scene_print(session))


def test_a_failed_command_is_not_replayed(bridge):
    session = saving(bridge, seconds=3600.0)
    session.ok("add_primitive", type="cube", name="A")
    session.refuse("boolean", "not_found", name="A", cutters=["Ghost"])
    session.refuse("delete", "not_found", names=["A", "Ghost"])
    session.ok("transform", name="A", location=[0.0, 0.0, 2.0])
    before = scene_print(session)
    result = restarted(session).ok("recover")
    assert result["replayed"]["requests"] == 2
    assert_same(before, scene_print(session))


def test_a_changed_input_file_is_reported_and_not_replayed(bridge):
    session = saving(bridge, seconds=3600.0)
    session.ok("add_primitive", type="cube", name="Kept")
    texture = os.path.join(session.workspace, "red.png")
    write_png(texture, (255, 0, 0))
    session.ok("image_load", path="red.png", name="red")
    session.ok("add_primitive", type="cube", name="Later")
    write_png(texture, (0, 255, 0))
    touch_later(texture)
    after = restarted(session)
    result = after.ok("recover")
    assert result["restored"] is True and result["replayed"]["requests"] == 1
    assert result["not_replayed"] == [{"seq": 2, "cmd": "image_load"}, {"seq": 3, "cmd": "add_primitive"}]
    assert result["not_replayed_reason"] == "its input red.png changed since it was journaled"
    assert "journaled request 2 (image_load) was not replayed because its input red.png changed since it was journaled" in result["reason"]
    assert "nor the 1 request after it" in result["reason"]
    assert sorted(obj.name for obj in bpy.data.objects) == ["Kept"] and "red" not in bpy.data.images
    assert commands(after) == ["add_primitive"]
    after.ok("add_primitive", type="cube", name="Next")
    assert [entry["seq"] for entry in entries(after)] == [1, 2]


def test_a_torn_last_entry_is_dropped_on_recovery(bridge):
    session = saving(bridge, seconds=3600.0)
    session.ok("add_primitive", type="cube", name="A")
    before = scene_print(session)
    with open(os.path.join(folder(session), f"journal-{meta(session)['generation']}.jsonl"), "ab") as handle:
        handle.write(b'{"seq":2,"cmd":"add_primitive","args":{"type":"cu')
    after = restarted(session)
    assert after.ok("recover")["replayed"]["requests"] == 1
    assert_same(before, scene_print(session))
    after.ok("add_primitive", type="cube", name="B")
    assert commands(after) == ["add_primitive", "add_primitive"]


def crash_in_snapshot_file(path):
    with open(path, "wb") as handle:
        handle.write(b"BLENDER-v5")
    raise Crash()


def crash_after_journal(original):
    def crashing(*args, **kwargs):
        original(*args, **kwargs)
        raise Crash()
    return crashing


def crash_before_rename(path, value):
    with open(f"{path}.partial", "w", encoding="utf-8") as handle:
        handle.write('{"generation": 99')
    raise Crash()


def test_a_crash_during_a_snapshot_leaves_the_previous_snapshot_and_journal_usable(bridge):
    points = (
        ("write_snapshot", crash_in_snapshot_file),
        ("JournalFile", None),
        ("write_json_atomically", crash_before_rename),
    )
    for name, replacement in points:
        reset_scene(bpy.context.scene)
        session = saving(Bridge(os.path.join(bridge.workspace, name)), seconds=3600.0)
        session.ok("add_primitive", type="cube", name="A")
        session.ok("transform", name="A", location=[1.0, 0.0, 0.0])
        before = scene_print(session)
        kept = files(session)
        original = getattr(autosave_module, name)
        if name == "JournalFile":
            class Crashing(original):
                create = staticmethod(crash_after_journal(original.create))
            replacement = Crashing
        setattr(autosave_module, name, replacement)
        try:
            session.handler.autosave.snapshot("test")
            raise AssertionError(f"{name}: the snapshot did not crash")
        except Crash:
            pass
        finally:
            setattr(autosave_module, name, original)
        assert files(session) != kept, name
        bpy.data.objects.remove(bpy.data.objects["A"])
        after = restarted(session)
        assert files(after) == kept, (name, files(after))
        result = after.ok("recover")
        assert result["replayed"]["requests"] == 2, (name, result)
        assert_same(before, scene_print(after))


def test_an_unreplayable_request_whose_snapshot_failed_stops_the_replay(bridge):
    session = saving(bridge, seconds=3600.0, allow_python=True)
    session.ok("add_primitive", type="cube", name="A")
    before = scene_print(session)
    original = autosave_module.write_snapshot

    def failing(path):
        raise OSError("disk full")

    autosave_module.write_snapshot = failing
    try:
        session.ok("run_python", code="import bpy\nbpy.data.objects['A'].location.x = 4.0\nresult = 1")
    finally:
        autosave_module.write_snapshot = original
    assert session.ok("scene_info")["autosave"]["error"] == "after run_python: disk full"
    assert entries(session)[-1] == {"seq": 2, "cmd": "run_python", "unreplayable": "run_python runs code that cannot be replayed"}
    result = restarted(session, allow_python=True).ok("recover")
    assert result["replayed"]["requests"] == 1 and result["not_replayed"] == [{"seq": 2, "cmd": "run_python"}]
    assert result["not_replayed_reason"].startswith("it could not be replayed (run_python runs code")
    assert_same(before, scene_print(session))


def test_recovery_works_across_checkpoints_load_blend_and_save_blend(bridge):
    session = saving(bridge, seconds=3600.0)
    session.ok("add_primitive", type="cube", name="A")
    session.ok("checkpoint", name="first")
    session.ok("add_primitive", type="cube", name="B", location=[2.0, 0.0, 0.0])
    session.ok("save_blend", path="two.blend")
    session.ok("restore_checkpoint", name="first")
    session.ok("add_primitive", type="cube", name="C", location=[0.0, 2.0, 0.0])
    session.ok("load_blend", path="two.blend")
    session.ok("transform", name="B", location=[0.0, 0.0, 5.0])
    before = scene_print(session)
    assert meta(session)["reason"] == "after load_blend" and commands(session) == ["transform"]
    result = restarted(session).ok("recover")
    assert result["replayed"]["requests"] == 1
    assert_same(before, scene_print(session))
    assert sorted(obj.name for obj in bpy.data.objects) == ["A", "B"]


def test_recovery_can_run_twice_and_the_journal_continues(bridge):
    session = saving(bridge, seconds=3600.0)
    session.ok("add_primitive", type="cube", name="A")
    first = restarted(session)
    first.ok("recover")
    first.ok("add_primitive", type="cube", name="B", location=[2.0, 0.0, 0.0])
    before = scene_print(first)
    assert [entry["seq"] for entry in entries(first)] == [1, 2]
    second = restarted(first)
    assert second.ok("recover")["replayed"]["requests"] == 2
    assert_same(before, scene_print(second))


def test_recover_without_an_autosave_says_so(bridge):
    session = saving(bridge)
    assert session.ok("recover") == {"restored": False, "reason": "there was no autosave yet"}


def test_recover_opens_an_autosave_of_the_earlier_layout(bridge):
    session = saving(bridge)
    os.makedirs(folder(session))
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.active_object.name = "Old"
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder(session), "autosave.blend"), copy=True)
    bpy.data.objects.remove(bpy.data.objects["Old"])
    result = restarted(session).ok("recover")
    assert result["restored"] is True and result["path"] == ".blendworks/autosave.blend" and result["objects"] == 1
    assert "Old" in bpy.data.objects


run(globals())
