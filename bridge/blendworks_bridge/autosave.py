import datetime
import os
import sys
import time

import bpy

from .blendfile import open_blend, read_json, save_atomically, write_json_atomically
from .errors import BridgeError
from .limits import DEFAULT_AUTOSAVE_SECONDS

ENVIRONMENT = "BLENDWORKS_AUTOSAVE_SECONDS"
FOLDER = ".blendworks"


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


class Autosave:
    def __init__(self, workspace, interval):
        self.workspace = workspace
        self.interval = interval
        self.folder = os.path.join(workspace.root, FOLDER)
        self.path = os.path.join(self.folder, "autosave.blend")
        self.previous = os.path.join(self.folder, "autosave.prev.blend")
        self.meta = os.path.join(self.folder, "autosave.json")
        self.previous_meta = os.path.join(self.folder, "autosave.prev.json")
        self.dirty = False
        self.last_save = None
        self.last = None
        self.error = None
        self.saves = 0

    @property
    def enabled(self):
        return self.interval is not None

    def due(self):
        return self.last_save is None or time.monotonic() - self.last_save >= self.interval

    def before(self, command):
        if self.enabled and self.dirty and (command.slow or self.due()):
            self.save(f"before {command.name}")

    def after(self, command):
        if not self.enabled:
            return
        self.dirty = True
        if self.due():
            self.save(f"after {command.name}")

    def replaced(self, command):
        if self.enabled:
            self.dirty = True
            self.save(f"after {command.name}")

    def save(self, reason):
        try:
            os.makedirs(self.folder, exist_ok=True)
            size = save_atomically(self.path, self.previous)
            if os.path.isfile(self.meta):
                os.replace(self.meta, self.previous_meta)
            record = {"saved_at": now_text(), "reason": reason, "bytes": size, "objects": len(bpy.context.scene.objects)}
            write_json_atomically(self.meta, record)
        except (BridgeError, OSError) as error:
            self.error = f"{reason}: {getattr(error, 'message', None) or error}"
            print(f"blendworks: autosave failed {self.error}", file=sys.stderr, flush=True)
            return False
        self.dirty = False
        self.last_save = time.monotonic()
        self.last = record
        self.error = None
        self.saves += 1
        return True

    def status(self):
        if not self.enabled:
            return {"enabled": False}
        status = {
            "enabled": True,
            "path": self.workspace.relative(self.path),
            "interval_seconds": self.interval,
            "unsaved_changes": self.dirty,
            "last": self.last,
        }
        if self.error:
            status["error"] = self.error
        return status

    def recover(self):
        failures = []
        for path, meta in ((self.path, self.meta), (self.previous, self.previous_meta)):
            if not os.path.isfile(path):
                continue
            try:
                open_blend(path)
            except BridgeError as error:
                failures.append(f"{os.path.basename(path)}: {error.message}")
                continue
            record = read_json(meta)
            if record is not None and record.get("bytes") != os.path.getsize(path):
                record = None
            self.dirty = False
            self.last_save = time.monotonic()
            self.last = record
            result = {
                "restored": True,
                "path": self.workspace.relative(path),
                "saved_at": record.get("saved_at") if record else None,
                "reason": record.get("reason") if record else None,
                "objects": len(bpy.context.scene.objects),
            }
            if failures:
                result["skipped"] = failures
            return result
        reason = "; ".join(failures) if failures else "there was no autosave yet"
        return {"restored": False, "reason": reason}
