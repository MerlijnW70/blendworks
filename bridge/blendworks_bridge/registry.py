from .policy import Policy
from .schema import obj

COMMANDS = {}


class Command:
    def __init__(self, name, description, schema, run, policy, dangerous):
        self.name = name
        self.description = description
        self.schema = schema
        self.run = run
        self.policy = policy
        self.dangerous = dangerous

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
        if self.dangerous:
            entry["dangerous"] = True
        return entry


def command(name, description, properties=None, required=(), mutates=True, dangerous=False, **policy):
    if "\n" in description or len(description) > 200:
        raise ValueError(f"{name}: the description must be one short line")
    rules = Policy(name, mutates, **policy)

    def register(run):
        if name in COMMANDS:
            raise ValueError(f"command {name} is registered twice")
        COMMANDS[name] = Command(name, description, obj(properties or {}, required), run, rules, dangerous)
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
