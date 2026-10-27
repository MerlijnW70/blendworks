DEFAULT_TIMEOUT = 120
DEFAULT_MAX_TIMEOUT = 600
SLOW_TIMEOUT = 300
SLOW_MAX_TIMEOUT = 1800

UNDO = "undo"
NO_SNAPSHOT = "none"
REPLACES_FILE = "file"

OVERRIDES = {
    "bake": {"slow": True, "timeout": 660, "max_timeout": 1200},
    "boolean": {"slow": True, "destructive_when": "cutter_action is delete"},
    "decimate": {"slow": True},
    "import": {"slow": True},
    "uv_pack": {"slow": True},
    "set_world_hdri": {"slow": True},
    "image_save": {"writes_files": True, "destructive_when": "the file already exists"},
    "apply_modifier": {"slow": True},
    "sweep": {"slow": True},
    "loft": {"slow": True},
    "instances": {"slow": True},
    "rivet_line": {"slow": True},
    "roller_chain": {"slow": True},
    "displace_noise": {"slow": True},
    "mesh_from_data": {"slow": True},
}


class Policy:
    def __init__(self, name, mutates, slow=False, timeout=None, max_timeout=None, destructive=False,
                 destructive_when=None, writes_files=False, internal=False, snapshot=None):
        settings = {
            "slow": slow,
            "timeout": timeout,
            "max_timeout": max_timeout,
            "destructive": destructive,
            "destructive_when": destructive_when,
            "writes_files": writes_files,
        }
        settings.update(OVERRIDES.get(name, {}))
        self.mutates = bool(mutates)
        self.slow = bool(settings["slow"])
        self.timeout = settings["timeout"] or (SLOW_TIMEOUT if self.slow else DEFAULT_TIMEOUT)
        self.max_timeout = settings["max_timeout"] or (SLOW_MAX_TIMEOUT if self.slow else DEFAULT_MAX_TIMEOUT)
        self.destructive_when = settings["destructive_when"]
        self.destructive = bool(settings["destructive"] or self.destructive_when)
        self.writes_files = bool(settings["writes_files"])
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
