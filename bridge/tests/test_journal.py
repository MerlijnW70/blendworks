import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autosave_helpers import commands, entries, folder, journal_lines, meta, saving, write_gltf, write_png
from harness import run

from blendworks_bridge.journal import JournalFile, ReadRecorder, RecordingWorkspace, read_journal
from blendworks_bridge.workspace import Workspace


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def test_successful_mutating_requests_are_journaled_in_order(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="A", location=[1.0, 2.0, 3.0])
    session.ok("transform", name="A", scale=[2.0, 2.0, 2.0])
    found = entries(session)
    assert [entry["seq"] for entry in found] == [1, 2]
    assert found[0]["cmd"] == "add_primitive" and found[0]["args"] == {"type": "cube", "name": "A", "location": [1.0, 2.0, 3.0]}
    assert found[1]["cmd"] == "transform" and found[1]["inputs"] == [] and found[1]["seconds"] >= 0.0
    assert journal_lines(session)[0] == '{"journal":1,"generation":%d}' % meta(session)["generation"]


def test_the_journal_holds_the_content_hash_of_each_workspace_file_read(bridge):
    session = saving(bridge)
    texture = os.path.join(session.workspace, "maps", "albedo.png")
    os.makedirs(os.path.dirname(texture))
    write_png(texture, (200, 30, 10))
    session.ok("image_load", path="maps/albedo.png", name="albedo")
    entry = entries(session)[-1]
    assert entry["cmd"] == "image_load"
    assert entry["inputs"] == [{"path": "maps/albedo.png", "bytes": os.path.getsize(texture), "mtime_ns": os.stat(texture).st_mtime_ns, "sha256": sha256(texture)}]


def test_files_an_importer_opens_beside_the_named_one_are_hashed_too(bridge):
    session = saving(bridge)
    write_gltf(session.workspace)
    session.ok("import", path="tri.gltf")
    inputs = {item["path"]: item["sha256"] for item in entries(session)[-1]["inputs"]}
    assert inputs == {"tri.gltf": sha256(os.path.join(session.workspace, "tri.gltf")), "tri.bin": sha256(os.path.join(session.workspace, "tri.bin"))}


def test_the_entry_is_on_disk_before_the_reply_is_returned(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="Flushed")
    with open(os.path.join(folder(session), f"journal-{meta(session)['generation']}.jsonl"), "rb") as handle:
        text = handle.read().decode("utf-8")
    assert text.endswith("\n") and '"name":"Flushed"' in text.splitlines()[-1]


def test_refused_and_failed_requests_are_not_journaled(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="A")
    session.refuse("no_such_command", "bad_args")
    session.refuse("add_primitive", "bad_args", type="teapot")
    session.refuse("delete", "not_found", names=["Ghost"])
    session.refuse("boolean", "not_found", name="A", cutter="Ghost")
    session.refuse("run_python", "forbidden", code="result = 1")
    assert commands(session) == ["add_primitive"]


def test_read_only_requests_are_not_journaled(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="A")
    session.ok("scene_info")
    session.ok("describe")
    session.ok("render_preview", resolution=64, samples=1, device="cpu")
    session.ok("export", path="a.glb")
    session.ok("checkpoint", name="one")
    session.ok("save_blend", path="a.blend")
    assert commands(session) == ["add_primitive"]


def test_a_journal_with_a_torn_last_line_reads_up_to_it(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="A")
    path = os.path.join(folder(session), f"journal-{meta(session)['generation']}.jsonl")
    with open(path, "ab") as handle:
        handle.write(b'{"seq":2,"cmd":"add_prim')
    read, problem = read_journal(path, meta(session)["generation"])
    assert problem is None and read["torn"] is True and [entry["cmd"] for entry in read["entries"]] == ["add_primitive"]
    assert read_journal(path, meta(session)["generation"] + 1)[1] == "the journal header does not match the snapshot"


def test_the_read_recorder_keeps_only_reads_inside_the_workspace(bridge):
    workspace = bridge.workspace
    inside = os.path.join(workspace, "in.txt")
    with open(inside, "w", encoding="utf-8") as handle:
        handle.write("x")
    own = os.path.join(workspace, ".blendworks", "own.txt")
    os.makedirs(os.path.dirname(own), exist_ok=True)
    with open(own, "w", encoding="utf-8") as handle:
        handle.write("x")
    with ReadRecorder(workspace, os.path.join(workspace, ".blendworks")) as recorder:
        open(inside, "rb").close()
        open(own, "rb").close()
        open(os.path.join(workspace, "written.txt"), "w").close()
        open(__file__, "rb").close()
    assert recorder.paths == [os.path.realpath(inside)]
    open(inside, "rb").close()
    assert ReadRecorder.active is None and recorder.paths == [os.path.realpath(inside)]



def test_files_named_through_the_workspace_are_recorded_without_the_audit_hook(bridge):
    workspace = Workspace(bridge.workspace)
    write_png(os.path.join(bridge.workspace, "a.png"), (1, 2, 3))
    recorder = ReadRecorder(workspace.root, os.path.join(workspace.root, ".blendworks"))
    resolved = RecordingWorkspace(workspace, recorder).existing("a.png", (".png",))
    assert recorder.paths == [resolved] and ReadRecorder.active is None


def half_written(handle, line):
    handle.write(line[: len(line) // 2])
    raise OSError("disk full")


def test_a_failed_append_leaves_no_partial_line(bridge):
    path = os.path.join(bridge.workspace, "journal-1.jsonl")
    journal = JournalFile.create(path, 1).open()
    journal.append(b'{"seq":1,"cmd":"a"}\n')
    journal.write = half_written
    try:
        journal.append(b'{"seq":2,"cmd":"b"}\n')
        raise AssertionError("the append did not fail")
    except OSError:
        pass
    del journal.write
    journal.append(b'{"seq":2,"cmd":"c"}\n')
    read, problem = read_journal(path, 1)
    assert problem is None and [entry["cmd"] for entry in read["entries"]] == ["a", "c"]


def test_the_journal_holds_no_open_file_between_requests(bridge):
    session = saving(bridge)
    session.ok("add_primitive", type="cube", name="A")
    path = os.path.join(folder(session), f"journal-{meta(session)['generation']}.jsonl")
    os.replace(path, path + ".moved")
    os.replace(path + ".moved", path)
    session.ok("add_primitive", type="cube", name="B")
    assert commands(session) == ["add_primitive", "add_primitive"]


run(globals())
