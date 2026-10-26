from .schema import obj

COMMANDS = {}


class Command:
    def __init__(self, name, description, schema, run, mutates, dangerous):
        self.name = name
        self.description = description
        self.schema = schema
        self.run = run
        self.mutates = mutates
        self.dangerous = dangerous

    def describe(self):
        entry = {"name": self.name, "description": self.description, "schema": self.schema}
        if self.dangerous:
            entry["dangerous"] = True
        return entry


def command(name, description, properties=None, required=(), mutates=True, dangerous=False):
    if "\n" in description or len(description) > 200:
        raise ValueError(f"{name}: the description must be one short line")

    def register(run):
        if name in COMMANDS:
            raise ValueError(f"command {name} is registered twice")
        COMMANDS[name] = Command(name, description, obj(properties or {}, required), run, mutates, dangerous)
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
