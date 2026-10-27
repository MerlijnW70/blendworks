from .policy import Policy
from .schema import obj

COMMANDS = {}


class Routing:
    def __init__(self, name, family, intents, nearest):
        if family is not None and not isinstance(family, str):
            raise ValueError(f"{name}: family must be a name")
        if any(not isinstance(intent, str) or not intent for intent in intents):
            raise ValueError(f"{name}: every intent must be a short phrase")
        if any(len(pair) != 2 or not all(isinstance(part, str) and part for part in pair) for pair in nearest):
            raise ValueError(f"{name}: nearest takes (command, when to use it instead) pairs")
        self.family = family
        self.intents = tuple(intents)
        self.nearest = tuple(tuple(pair) for pair in nearest)

    def describe(self):
        entry = {}
        if self.family is not None:
            entry["family"] = self.family
        if self.intents:
            entry["intents"] = list(self.intents)
        if self.nearest:
            entry["nearest"] = [{"name": name, "when": when} for name, when in self.nearest]
        return entry


class Command:
    def __init__(self, name, description, schema, run, policy, dangerous, routing):
        self.name = name
        self.description = description
        self.schema = schema
        self.run = run
        self.policy = policy
        self.dangerous = dangerous
        self.routing = routing

    @property
    def mutates(self):
        return self.policy.mutates

    @property
    def slow(self):
        return self.policy.slow

    @property
    def snapshot(self):
        return self.policy.snapshot

    @property
    def internal(self):
        return self.policy.internal

    def describe(self):
        entry = {"name": self.name, "description": self.description, "schema": self.schema}
        entry.update(self.policy.describe())
        entry.update(self.routing.describe())
        if self.dangerous:
            entry["dangerous"] = True
        return entry


def command(name, description, properties=None, required=(), mutates=True, dangerous=False, family=None, intents=(),
            nearest=(), **policy):
    if "\n" in description or len(description) > 200:
        raise ValueError(f"{name}: the description must be one short line")
    rules = Policy(name, mutates, **policy)
    routing = Routing(name, family, intents, nearest)

    def register(run):
        if name in COMMANDS:
            raise ValueError(f"command {name} is registered twice")
        COMMANDS[name] = Command(name, description, obj(properties or {}, required), run, rules, dangerous, routing)
        return run

    return register


class Registry:
    def __init__(self, commands):
        self.commands = dict(commands)

    def get(self, name):
        return self.commands.get(name)

    def names(self):
        return sorted(self.commands)

    def describe(self):
        return [self.commands[name].describe() for name in self.names()]
