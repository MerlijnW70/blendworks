"""The named limit type: a number that knows its name, unit, kind of reason and reason."""

PHYSICAL = "physical"
MEMORY = "memory"
TIME = "time"
BLENDER = "blender"
PROTOCOL = "protocol"
KINDS = (PHYSICAL, MEMORY, TIME, BLENDER, PROTOCOL)

LIMITS = {}
INSTEAD = {}


class _Limit:
    __slots__ = ()

    def describe(self):
        entry = {"name": self.key, "value": self.plain(), "unit": self.unit, "kind": self.kind, "reason": self.reason}
        if INSTEAD.get(self.key):
            entry["instead"] = INSTEAD[self.key]
        return entry

    def __neg__(self):
        return type(self)._make(-self.plain(), self.key, self.unit, self.kind, self.reason)

    def __reduce__(self):
        return (type(self)._make, (self.plain(), self.key, self.unit, self.kind, self.reason))

    def __deepcopy__(self, memo):
        return self

    def __copy__(self):
        return self


class FloatLimit(_Limit, float):

    @classmethod
    def _make(cls, value, key, unit, kind, reason):
        made = float.__new__(cls, value)
        made.key, made.unit, made.kind, made.reason = key, unit, kind, reason
        return made

    def plain(self):
        return float(self)


class IntLimit(_Limit, int):

    @classmethod
    def _make(cls, value, key, unit, kind, reason):
        made = int.__new__(cls, value)
        made.key, made.unit, made.kind, made.reason = key, unit, kind, reason
        return made

    def plain(self):
        return int(self)


def limit(key, value, unit, kind, reason, instead=None):
    if key in LIMITS:
        raise ValueError(f"limit {key} is defined twice")
    if kind not in KINDS:
        raise ValueError(f"limit {key}: unknown kind {kind}")
    if not reason or not reason.strip():
        raise ValueError(f"limit {key} needs a reason")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"limit {key} must be a number")
    made = (IntLimit if isinstance(value, int) else FloatLimit)._make(value, key, unit, kind, reason)
    LIMITS[key] = made
    INSTEAD[key] = instead
    return made


def limit_of(value):
    """The name of the limit a schema bound came from, or None for a plain number."""
    return value.key if isinstance(value, _Limit) else None


def table():
    return [LIMITS[key].describe() for key in sorted(LIMITS)]
