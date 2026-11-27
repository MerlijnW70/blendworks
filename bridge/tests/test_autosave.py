import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from autosave_helpers import commands, entries, files, folder, meta, saving, snapshots, touch_later, write_gltf, write_png
from harness import Bridge, run

from blendworks_bridge import autosave as autosave_module
from blendworks_bridge import blendfile, limits
from blendworks_bridge.autosave import interval_from_environment


def test_the_first_change_of_a_session_starts_the_journal_from_a_snapshot(bridge):
    session = saving(bridge)
    session.ok("scene_info")
    assert files(session) == []
    session.ok("add_primitive", type="cube", name="A")
    assert files(session) == ["autosave-1.blend", "autosave.json", "journal-1.jsonl"]
    record = meta(session)
    assert record["generation"] == 1 and record["objects"] == 0 and record["reason"] == "before add_primitive, the first change of this session"
    assert record["bytes"] == os.path.getsize(os.path.join(folder(session), "autosave-1.blend"))
    assert commands(session) == ["add_primitive"]


def test_slow_commands_no_longer_force_a_snapshot(bridge):
    session = saving(bridge, seconds=3600.0)
    session.ok("heightfield", name="land", size=[10.0, 10.0], resolution=33, height=1.0, seed=1)
    session.ok("noise_displace", name="land", amplitude=0.2, seed=2)
    session.ok("decimate", name="land", ratio=0.5)
    session.ok("export", path="land.glb")
    session.ok("save_blend", path="land.blend")
    assert session.handler.autosave.saves == 1 and snapshots(session) == ["autosave-1.blend"]
    assert commands(session) == ["heightfield", "noise_displace", "decimate"]


def test_a_snapshot_is_taken_only_once_the_bridge_is_idle(bridge):
    session = saving(bridge, seconds=0.0)
    autosave = session.handler.autosave
    assert autosave.idle_wait() is None
    session.ok("add_primitive", type="cube", name="A")
    assert autosave.idle_seconds == limits.AUTOSAVE_IDLE_SECONDS and 0.0 < autosave.idle_wait() <= autosave.idle_seconds
    assert autosave.idle() is False and autosave.saves == 1
    autosave.idle_seconds = 0.2
    time.sleep(0.25)
    assert autosave.idle_wait() == 0.0 and autosave.idle() is True
    assert meta(session)["reason"] == "when idle" and meta(session)["objects"] == 1 and entries(session) == []
    assert autosave.idle_wait() is None


def test_the_snapshot_interval_spaces_idle_snapshots(bridge):
    session = saving(bridge, seconds=3600.0)
    autosave = session.handler.autosave
    autosave.idle_seconds = 0.0
    session.ok("add_primitive", type="cube", name="A")
    assert autosave.idle_wait() > 3500.0 and autosave.idle() is False


def test_a_snapshot_is_taken_when_the_replay_cost_passes_the_budget(bridge):
    session = saving(bridge)
    saved = autosave_module.REPLAY_BUDGET_RATIO, autosave_module.REPLAY_BUDGET_FLOOR_SECONDS
    autosave_module.REPLAY_BUDGET_RATIO, autosave_module.REPLAY_BUDGET_FLOOR_SECONDS = 2.0, 0.0
    try:
        autosave = session.handler.autosave
        for index in range(400):
            session.ok("add_primitive", type="ico_sphere", name=f"S{index}", subdivisions=3)
            assert autosave.replay_budget() == 2.0 * meta(session)["seconds"]
            assert autosave.replay_seconds <= autosave.replay_budget()
            if meta(session)["reason"].startswith("after add_primitive: replaying the journal would take"):
                break
        assert meta(session)["reason"].startswith("after add_primitive: replaying the journal would take")
    finally:
        autosave_module.REPLAY_BUDGET_RATIO, autosave_module.REPLAY_BUDGET_FLOOR_SECONDS = saved


def test_the_replay_budget_is_a_multiple_of_the_last_snapshot_within_its_floor_and_cap(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="A")
    autosave = session.handler.autosave
    for seconds, expected in ((0.0, limits.REPLAY_BUDGET_FLOOR_SECONDS), (0.5, 0.5 * limits.REPLAY_BUDGET_RATIO), (60.0, limits.MAX_REPLAY_SECONDS)):
        autosave.record["seconds"] = seconds
        assert autosave.replay_budget() == expected


def test_the_journal_size_limit_folds_it_into_a_snapshot(bridge):
    session = saving(bridge)
    saved = autosave_module.MAX_JOURNAL_BYTES
    autosave_module.MAX_JOURNAL_BYTES = 600
    try:
        for index in range(6):
            session.ok("add_primitive", type="cube", name=f"C{index}")
        assert meta(session)["generation"] > 1 and "the journal would pass" in meta(session)["reason"]
        assert session.handler.autosave.journal.bytes <= 600
    finally:
        autosave_module.MAX_JOURNAL_BYTES = saved


def test_requests_that_cannot_be_replayed_are_followed_by_a_snapshot(bridge):
    session = saving(bridge, seconds=3600.0, allow_python=True)
    session.ok("add_primitive", type="cube", name="A")
    session.ok("save_blend", path="kept.blend")
    session.ok("checkpoint", name="one")
    cases = (
        ("run_python", {"code": "import bpy\nbpy.data.objects['A'].location.x = 4.0\nresult = 1"}),
        ("load_blend", {"path": "kept.blend"}),
        ("restore_checkpoint", {"name": "one"}),
        ("image_new", {"name": "pixels", "width": 8, "height": 8}),
        ("image_save", {"name": "pixels", "path": "pixels.png"}),
    )
    for name, args in cases:
        generation = meta(session)["generation"]
        session.ok(name, **args)
        if name == "image_new":
            assert commands(session)[-1] == "image_new"
            continue
        assert meta(session)["generation"] == generation + 1 and meta(session)["reason"] == f"after {name}", name
        assert entries(session) == [], name


def test_a_changed_input_file_forces_a_snapshot_before_the_next_change(bridge):
    session = saving(bridge, seconds=3600.0)
    texture = os.path.join(session.workspace, "red.png")
    write_png(texture, (255, 0, 0))
    session.ok("image_load", path="red.png", name="red")
    session.ok("add_primitive", type="cube", name="A")
    generation = meta(session)["generation"]
    write_png(texture, (0, 0, 255))
    touch_later(texture)
    session.ok("scene_info")
    assert meta(session)["generation"] == generation
    session.ok("add_primitive", type="cube", name="B")
    assert meta(session)["reason"] == "before add_primitive: red.png changed since it was journaled"
    assert commands(session) == ["add_primitive"]


def test_a_request_that_overwrites_a_journaled_input_is_followed_by_a_snapshot(bridge):
    session = saving(bridge, seconds=3600.0)
    write_gltf(session.workspace)
    session.ok("import", path="tri.gltf")
    session.ok("add_primitive", type="cube", name="A")
    generation = meta(session)["generation"]
    session.ok("export", path="other.glb")
    assert meta(session)["generation"] == generation
    session.ok("save_blend", path="tri.gltf.blend")
    assert meta(session)["generation"] == generation
    write_gltf(session.workspace, height=2.0)
    touch_later(os.path.join(session.workspace, "tri.bin"))
    session.ok("save_blend", path="after.blend")
    assert meta(session)["generation"] == generation + 1
    assert meta(session)["reason"].startswith("after save_blend: tri.") and meta(session)["reason"].endswith(" changed since it was journaled")


def test_one_snapshot_is_kept(bridge):
    session = saving(bridge)
    for index in range(4):
        session.ok("add_primitive", type="cube", name=f"C{index}")
        assert session.handler.autosave.snapshot(f"test {index}")
    assert files(session) == ["autosave-5.blend", "autosave.json", "journal-5.jsonl"]


def test_a_snapshot_keeps_unused_data_and_leaves_the_live_scene_as_it_was(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="A")
    spare = bpy.data.meshes.new("Spare")
    assert spare.users == 0
    assert session.handler.autosave.snapshot("test")
    assert spare.users == 0 and spare.use_fake_user is False
    assert ["meshes", "Spare"] in meta(session)["unused"], meta(session)["unused"]
    bpy.data.meshes.remove(spare)


def test_the_snapshot_peak_on_disk_stays_under_one_uncompressed_scene(bridge):
    session = saving(bridge)
    session.ok("heightfield", name="land", size=[100.0, 100.0], resolution=401, height=2.0, seed=3)
    session.ok("noise_displace", name="land", amplitude=2.0, seed=4)
    uncompressed = session.ok("save_blend", path="land.blend")["bytes"]
    peaks = []
    original = blendfile.write_blend

    def measured(path, compress):
        original(path, compress)
        peaks.append(sum(os.path.getsize(os.path.join(folder(session), name)) for name in files(session)))

    blendfile.write_blend = measured
    try:
        for index in range(2):
            assert session.handler.autosave.snapshot(f"test {index}")
    finally:
        blendfile.write_blend = original
    assert len(peaks) == 2 and len(snapshots(session)) == 1
    assert max(peaks) <= uncompressed, (peaks, uncompressed)


def test_the_desktop_add_on_does_not_autosave_or_recover(bridge):
    desktop = Bridge(bridge.workspace, desktop=True, autosave_seconds=0.0)
    desktop.ok("add_primitive", type="cube")
    assert files(desktop) == []
    assert desktop.ok("scene_info")["autosave"] == {"enabled": False}
    desktop.refuse("recover", "forbidden")
    bridge.refuse("recover", "bad_args", path="x.blend")


def test_off_turns_the_journal_and_snapshots_off(bridge):
    session = Bridge(bridge.workspace, autosave_seconds=None)
    session.ok("add_primitive", type="cube")
    assert files(session) == [] and session.ok("scene_info")["autosave"] == {"enabled": False}


def test_the_status_names_the_limits(bridge):
    session = saving(bridge, seconds=12.0)
    session.ok("add_primitive", type="cube")
    status = session.ok("scene_info")["autosave"]
    assert status["interval_seconds"] == 12.0 and status["idle_seconds"] == limits.AUTOSAVE_IDLE_SECONDS
    assert status["journal"]["requests"] == 1 and status["journal"]["replay_budget_seconds"] == limits.REPLAY_BUDGET_FLOOR_SECONDS
    assert status["path"] == ".blendworks/autosave-1.blend" and status["spent"]["snapshots"] == 1


def test_the_interval_comes_from_the_environment(bridge):
    assert interval_from_environment({}) == 30.0
    assert interval_from_environment({"BLENDWORKS_AUTOSAVE_SECONDS": "5"}) == 5.0
    assert interval_from_environment({"BLENDWORKS_AUTOSAVE_SECONDS": "off"}) is None
    assert interval_from_environment({"BLENDWORKS_AUTOSAVE_SECONDS": "-3"}) == 30.0
    assert interval_from_environment({"BLENDWORKS_AUTOSAVE_SECONDS": "soon"}) == 30.0


run(globals())
