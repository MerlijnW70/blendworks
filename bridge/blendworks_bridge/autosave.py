import datetime
import os
import re
import sys
import time

import bpy

from .blendfile import open_blend, open_snapshot, read_json, remove_quietly, write_json_atomically, write_snapshot
from .errors import BridgeError
from .journal import FileHashes, JournalFile, content_changed, encode_line, journal_name, read_journal, stat_changed
from .limits import (
    AUTOSAVE_IDLE_SECONDS,
    DEFAULT_AUTOSAVE_SECONDS,
    MAX_JOURNAL_BYTES,
    MAX_LISTED_NAMES,
    MAX_REPLAY_SECONDS,
    REPLAY_BUDGET_FLOOR_SECONDS,
    REPLAY_BUDGET_RATIO,
)
from .policy import NO_SNAPSHOT, REPLACES_FILE

ENVIRONMENT = "BLENDWORKS_AUTOSAVE_SECONDS"
FOLDER = ".blendworks"
META = "autosave.json"
LEGACY = "autosave.blend"
PYTHON_COMMAND = "run_python"
OWN_FILE = re.compile(r"^(autosave-\d+\.blend|journal-\d+\.jsonl(\.partial)?|autosave\.json\.partial|autosave\.prev\.(blend|json)|autosave\.blend|\.autosave.*)$")


def interval_from_environment(environ=None):
    text = (environ if environ is not None else os.environ).get(ENVIRONMENT, "").strip().lower()
    if text == "":
        return DEFAULT_AUTOSAVE_SECONDS
    if text == "off":
        return None
    try:
        value = float(text)
    except ValueError:
        value = -1.0
    if not value >= 0.0 or value == float("inf"):
        print(f"blendworks: {ENVIRONMENT} must be off or a number of seconds, not {text!r}; using {DEFAULT_AUTOSAVE_SECONDS}", file=sys.stderr)
        return DEFAULT_AUTOSAVE_SECONDS
    return value


def now_text():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def journaled(command):
    return command.mutates and command.snapshot != NO_SNAPSHOT


def unreplayable(command):
    if command.name == PYTHON_COMMAND:
        return "run_python runs code that cannot be replayed"
    if command.snapshot == REPLACES_FILE:
        return f"{command.name} replaces the whole scene from a file"
    if command.policy.writes_files:
        return f"replaying {command.name} would write workspace files again"
    return None


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


class Autosave:
    def __init__(self, workspace, interval, replay_request=None, idle_seconds=AUTOSAVE_IDLE_SECONDS):
        self.workspace = workspace
        self.replay_request = replay_request
        self.interval = interval
        self.idle_seconds = idle_seconds
        self.folder = os.path.join(workspace.root, FOLDER)
        self.meta = os.path.join(self.folder, META)
        self.hashes = FileHashes()
        self.record = None
        self.journal = None
        self.entries = 0
        self.replay_seconds = 0.0
        self.inputs = {}
        self.last_snapshot = None
        self.idle_failed = None
        self.last_request = time.monotonic()
        self.error = None
        self.saves = 0
        self.seconds = 0.0
        self.snapshot_seconds = 0.0
        if self.enabled:
            self.remove_uncommitted()

    @property
    def enabled(self):
        return self.interval is not None

    def snapshot_path(self, record):
        if record is None or not record.get("snapshot"):
            return None
        return os.path.join(self.folder, record["snapshot"])

    def journal_path(self, generation):
        return os.path.join(self.folder, journal_name(generation))

    def committed(self):
        record = read_json(self.meta)
        if record is None or not isinstance(record.get("generation"), int) or not isinstance(record.get("snapshot"), str):
            return None
        return record

    def remove_uncommitted(self):
        if not os.path.isdir(self.folder):
            return
        record = self.committed()
        if record is not None:
            keep = {record["snapshot"], journal_name(record["generation"])}
        else:
            keep = {LEGACY}
        for name in os.listdir(self.folder):
            if OWN_FILE.match(name) and name not in keep:
                remove_quietly(os.path.join(self.folder, name))

    def touch(self):
        self.last_request = time.monotonic()

    def before(self, command):
        if not self.enabled or not journaled(command):
            return
        started = time.perf_counter()
        try:
            self.prepare(command)
        finally:
            self.seconds += time.perf_counter() - started

    def prepare(self, command):
        if self.journal is None:
            self.snapshot(f"before {command.name}, the first change of this session")
            return
        changed = self.changed_input()
        if changed is not None:
            self.snapshot(f"before {command.name}: {changed} changed since it was journaled")

    def after(self, command, args, reads, seconds):
        if not self.enabled:
            return
        started = time.perf_counter()
        try:
            self.record_request(command, args, reads, seconds)
        finally:
            self.seconds += time.perf_counter() - started

    def record_request(self, command, args, reads, seconds):
        if not journaled(command):
            changed = self.changed_input() if command.policy.writes_files else None
            if changed is not None:
                self.snapshot(f"after {command.name}: {changed} changed since it was journaled")
            return
        reason = unreplayable(command)
        if reason is not None:
            if not self.snapshot(f"after {command.name}"):
                self.write_entry({"cmd": command.name, "unreplayable": reason})
            return
        if self.journal is not None:
            self.append(command, args, reads, seconds)

    def append(self, command, args, reads, seconds):
        try:
            inputs = [dict(path=self.workspace.relative(path), **self.hashes.describe(path)) for path in reads]
            entry = {"cmd": command.name, "args": args, "inputs": inputs, "seconds": round(seconds, 6)}
            line = encode_line(dict(seq=self.entries + 1, **entry))
        except (OSError, ValueError, TypeError) as error:
            self.snapshot(f"after {command.name}: it could not be journaled ({error})")
            return
        if self.journal.bytes + len(line) > MAX_JOURNAL_BYTES:
            self.snapshot(f"after {command.name}: the journal would pass {MAX_JOURNAL_BYTES // (1024 * 1024)} MB")
            return
        if not self.write_entry(entry, line):
            self.snapshot(f"after {command.name}: the journal could not be written ({self.error})")
            return
        self.replay_seconds += seconds
        for item, path in zip(inputs, reads):
            self.inputs[path] = (item["path"], item["bytes"], item["mtime_ns"])
        if self.replay_seconds > self.replay_budget():
            self.snapshot(f"after {command.name}: replaying the journal would take {self.replay_seconds:.1f} s")

    def write_entry(self, entry, line=None):
        if self.journal is None:
            return False
        try:
            self.journal.append(line or encode_line(dict(seq=self.entries + 1, **entry)))
        except OSError as error:
            self.error = f"the journal could not be written: {error}"
            return False
        self.entries += 1
        return True

    def replay_budget(self):
        last = self.record.get("seconds", 0.0) if self.record else 0.0
        return min(MAX_REPLAY_SECONDS, max(REPLAY_BUDGET_FLOOR_SECONDS, REPLAY_BUDGET_RATIO * last))

    def changed_input(self):
        for path, (relative, size, mtime_ns) in self.inputs.items():
            if stat_changed(path, size, mtime_ns):
                return relative
        return None

    def idle_wait(self):
        if not self.enabled or self.journal is None or self.entries == 0:
            return None
        ready = self.last_request + self.idle_seconds
        if self.last_snapshot is not None:
            ready = max(ready, self.last_snapshot + self.interval)
        if self.idle_failed is not None:
            ready = max(ready, self.idle_failed + max(self.interval, self.idle_seconds))
        return max(0.0, ready - time.monotonic())

    def idle(self):
        wait = self.idle_wait()
        if wait is None or wait > 0.0:
            return False
        started = time.perf_counter()
        saved = self.snapshot("when idle")
        self.seconds += time.perf_counter() - started
        if saved:
            return True
        self.idle_failed = time.monotonic()
        return False

    def snapshot(self, reason):
        started = time.perf_counter()
        generation = (self.record["generation"] if self.record else self.latest_generation()) + 1
        name = f"autosave-{generation}.blend"
        target = os.path.join(self.folder, name)
        try:
            os.makedirs(self.folder, exist_ok=True)
            unused, unsaved = write_snapshot(target)
            journal = JournalFile.create(self.journal_path(generation), generation)
            record = {
                "generation": generation,
                "snapshot": name,
                "saved_at": now_text(),
                "reason": reason,
                "bytes": os.path.getsize(target),
                "seconds": round(time.perf_counter() - started, 6),
                "objects": len(bpy.context.scene.objects),
                "unused": unused,
                "unsaved_images": unsaved,
            }
            write_json_atomically(self.meta, record)
        except (BridgeError, OSError) as error:
            remove_quietly(target)
            remove_quietly(self.journal_path(generation))
            self.error = f"{reason}: {getattr(error, 'message', None) or error}"
            print(f"blendworks: autosave failed {self.error}", file=sys.stderr, flush=True)
            return False
        self.attach(record, journal, 0, 0.0, {})
        self.remove_uncommitted()
        self.saves += 1
        self.snapshot_seconds += time.perf_counter() - started
        return True

    def latest_generation(self):
        record = self.committed()
        return record["generation"] if record else 0

    def attach(self, record, journal, entries, replay_seconds, inputs):
        self.record = record
        self.journal = journal.open()
        self.entries = entries
        self.replay_seconds = replay_seconds
        self.inputs = inputs
        self.last_snapshot = time.monotonic()
        self.idle_failed = None
        self.error = None

    def status(self):
        if not self.enabled:
            return {"enabled": False}
        path = self.snapshot_path(self.record)
        status = {
            "enabled": True,
            "path": self.workspace.relative(path) if path else None,
            "interval_seconds": self.interval,
            "idle_seconds": self.idle_seconds,
            "journal": {
                "requests": self.entries,
                "replay_seconds": round(self.replay_seconds, 3),
                "replay_budget_seconds": round(self.replay_budget(), 3),
                "bytes": self.journal.bytes if self.journal else 0,
            },
            "last": self.record,
            "spent": {"seconds": round(self.seconds, 3), "snapshots": self.saves, "snapshot_seconds": round(self.snapshot_seconds, 3)},
        }
        if self.error:
            status["error"] = self.error
        return status

    def recover(self):
        self.journal = None
        record = self.committed()
        if record is None:
            return self.recover_legacy()
        path = self.snapshot_path(record)
        try:
            open_snapshot(path, record.get("unused") or [])
        except BridgeError as error:
            return {"restored": False, "reason": f"{record['snapshot']} could not be opened: {error.message}"}
        generation = record["generation"]
        read, problem = read_journal(self.journal_path(generation), generation)
        entries = read["entries"] if read else []
        replayed, stopped, replay_seconds, inputs = self.replay(entries)
        if problem is not None or stopped is not None or read["torn"]:
            journal = JournalFile.create(self.journal_path(generation), generation, replayed, atomic=True)
        else:
            journal = JournalFile(self.journal_path(generation), generation)
        self.attach(record, journal, len(replayed), replay_seconds, inputs)
        bpy.context.view_layer.update()
        return self.recovered(record, path, replayed, entries[len(replayed):], stopped, problem)

    def replay(self, entries):
        replayed = []
        replay_seconds = 0.0
        inputs = {}
        for entry in entries:
            problem = self.replay_problem(entry)
            if problem is None:
                try:
                    self.replay_request(entry["cmd"], entry.get("args") or {})
                except BridgeError as error:
                    problem = f"replaying it failed: {error.message}"
            if problem is not None:
                return replayed, {"seq": entry.get("seq"), "cmd": entry["cmd"], "reason": problem}, replay_seconds, inputs
            replayed.append(entry)
            replay_seconds += float(entry.get("seconds") or 0.0)
            for item in entry.get("inputs") or []:
                path = os.path.join(self.workspace.root, item["path"])
                stat = os.stat(path)
                inputs[path] = (item["path"], stat.st_size, stat.st_mtime_ns)
        return replayed, None, replay_seconds, inputs

    def replay_problem(self, entry):
        if "unreplayable" in entry:
            return f"it could not be replayed ({entry['unreplayable']}) and the snapshot after it failed"
        for item in entry.get("inputs") or []:
            try:
                path = self.workspace.resolve(item["path"])
            except BridgeError:
                return f"its input {item['path']} is outside the workspace"
            if content_changed(path, item["bytes"], item["sha256"]):
                return f"its input {item['path']} changed since it was journaled"
        return None

    def recovered(self, record, path, replayed, dropped, stopped, problem):
        how = f"snapshot {record['reason']}"
        if replayed:
            how += f", then {plural(len(replayed), 'journaled request')} replayed, the last {replayed[-1]['cmd']}"
        if stopped is not None:
            how += f"; journaled request {stopped['seq']} ({stopped['cmd']}) was not replayed because {stopped['reason']}"
            if len(dropped) > 1:
                how += f", nor the {plural(len(dropped) - 1, 'request')} after it"
        if problem is not None:
            how += f"; the journal was not replayed: {problem}"
        result = {
            "restored": True,
            "path": self.workspace.relative(path),
            "saved_at": record.get("saved_at"),
            "reason": how,
            "objects": len(bpy.context.scene.objects),
            "snapshot": {key: record.get(key) for key in ("generation", "saved_at", "reason", "bytes", "objects")},
            "replayed": {"requests": len(replayed), "seconds": round(sum(float(entry.get("seconds") or 0.0) for entry in replayed), 3)},
        }
        if dropped:
            result["not_replayed"] = [{"seq": entry.get("seq"), "cmd": entry["cmd"]} for entry in dropped[:MAX_LISTED_NAMES]]
            result["not_replayed_reason"] = stopped["reason"] if stopped else problem
        if record.get("unsaved_images"):
            result["unsaved_images"] = record["unsaved_images"]
        return result

    def recover_legacy(self):
        path = os.path.join(self.folder, LEGACY)
        if not os.path.isfile(path):
            return {"restored": False, "reason": "there was no autosave yet"}
        try:
            open_blend(path)
        except BridgeError as error:
            return {"restored": False, "reason": f"{LEGACY} could not be opened: {error.message}"}
        return {"restored": True, "path": self.workspace.relative(path), "saved_at": None, "reason": "an autosave from an earlier version",
                "objects": len(bpy.context.scene.objects)}
