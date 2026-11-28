"""The Policy of a command: whether it mutates, is slow, snapshots or is internal."""

DEFAULT_TIMEOUT = 120
DEFAULT_MAX_TIMEOUT = 600
SLOW_TIMEOUT = 300
SLOW_MAX_TIMEOUT = 1800

UNDO = "undo"
NO_SNAPSHOT = "none"
REPLACES_FILE = "file"


class Policy:
    def __init__(self, name, mutates, slow=False, timeout=None, max_timeout=None, destructive=False,
                 destructive_when=None, writes_files=False, internal=False, snapshot=None, renders=False):
        self.mutates = bool(mutates)
        self.renders = bool(renders)
        self.slow = bool(slow)
        self.timeout = timeout or (SLOW_TIMEOUT if self.slow else DEFAULT_TIMEOUT)
        self.max_timeout = max_timeout or (SLOW_MAX_TIMEOUT if self.slow else DEFAULT_MAX_TIMEOUT)
        self.destructive_when = destructive_when
        self.destructive = bool(destructive or self.destructive_when)
        self.writes_files = bool(writes_files)
        self.internal = bool(internal)
        self.snapshot = snapshot or (UNDO if self.mutates else NO_SNAPSHOT)
        if self.timeout > self.max_timeout:
            raise ValueError(f"{name}: the default timeout is above its cap")
        if self.snapshot not in (UNDO, NO_SNAPSHOT, REPLACES_FILE):
            raise ValueError(f"{name}: unknown snapshot kind {self.snapshot}")

    def describe(self):
        entry = {
            "mutates": self.mutates,
            "destructive": self.destructive,
            "writes_files": self.writes_files,
            "slow": self.slow,
            "timeout": self.timeout,
            "max_timeout": self.max_timeout,
        }
        if self.destructive_when:
            entry["destructive_when"] = self.destructive_when
        if self.internal:
            entry["internal"] = True
        return entry
