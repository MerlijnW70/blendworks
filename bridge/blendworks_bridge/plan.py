"""Check a list of calls without running any of them.

Each call is checked against its command's schema, with every problem collected rather than the first. The names
the calls use are then followed through the plan: a field marked x-ref exists must name a datablock that is in the
scene or that an earlier call makes; one marked creates must name one that is not. Commands that change names in
other ways (new_scene clears the scene, delete removes, rename renames, load_blend replaces it with an unknown file)
say so with the plan hook of their registration. The handler runs the same schema check before every call, so a
script and the MCP server get the same answer from validate as from the call itself."""
import bpy

from .errors import BridgeError, bad_args
from .limits import MAX_PLAN_PROBLEMS
from .schema import CREATES, ENSURES, EXISTS, REF, REF_KINDS, REPLACES, check, more_problems

TIMEOUT_FIELD = "timeout_seconds"
PYTHON_COMMAND = "run_python"
VALIDATE_COMMAND = "validate"

MASTER_COLLECTION = "Scene Collection"
COLLECTIONS = {"object": "objects", "material": "materials", "image": "images", "collection": "collections"}
NOT_FOUND_HINT = {
    "object": "make it in an earlier call (add_primitive, heightfield, import and others) or check scene_info",
    "material": "make it in an earlier call (add_material, material_procedural, material_pbr) or check material_info",
    "image": "make it in an earlier call (image_new, image_load) or check image_info",
    "collection": "make it in an earlier call (collection_create)",
}


class PlanState:
    """The names of the scene's datablocks as the plan goes, per kind. A kind becomes open once a call leaves it
    unknown (load_blend, restore_checkpoint): from then on a missing name of that kind is not a problem."""

    def __init__(self, names=None, master=MASTER_COLLECTION):
        self.names = {kind: set(names.get(kind, ())) if names else set() for kind in REF_KINDS}
        self.master = master
        self.names["collection"].add(master)
        self.open = set()

    @classmethod
    def from_scene(cls):
        names = {kind: [block.name for block in getattr(bpy.data, attribute)] for kind, attribute in COLLECTIONS.items()}
        return cls(names, bpy.context.scene.collection.name)

    def has(self, kind, name):
        return name in self.names[kind] or kind in self.open

    def add(self, kind, name):
        self.names[kind].add(name)

    def remove(self, kind, name):
        self.names[kind].discard(name)

    def rename(self, kind, old, new):
        if old in self.names[kind]:
            self.names[kind].discard(old)
        self.names[kind].add(new)

    def clear(self, kinds=REF_KINDS):
        for kind in kinds:
            self.names[kind].clear()
            self.open.discard(kind)
        self.names["collection"].add(self.master)

    def unknown(self, kinds=REF_KINDS):
        for kind in kinds:
            self.open.add(kind)


def references(schema, value, where="args"):
    """(kind, use, name, argument) for every x-ref field in a cleaned value."""
    found = []
    if not isinstance(schema, dict):
        return found
    mark = schema.get(REF)
    if mark is not None and isinstance(value, str):
        found.append((mark["kind"], mark["use"], value, where))
    if schema.get("type") == "object" and isinstance(value, dict):
        for name, field in schema.get("properties", {}).items():
            if name in value:
                found.extend(references(field, value[name], f"{where}.{name}"))
    elif schema.get("type") == "array" and isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(references(schema["items"], item, f"{where}[{index}]"))
    return found


def without_timeout(command, args):
    """Every command takes timeout_seconds, the time a caller waits for it. The MCP server enforces it; a script that
    calls the handler directly waits as long as the call runs, so the handler and validate only check it and drop
    it. That way the same call works on both paths."""
    if TIMEOUT_FIELD not in args:
        return args
    limit = command.policy.max_timeout
    seconds = args[TIMEOUT_FIELD]
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= limit:
        raise bad_args(f"args.{TIMEOUT_FIELD} must be a number of seconds above 0 and at most {limit} for "
                       f"{command.name}; got {seconds!r}")
    return {key: value for key, value in args.items() if key != TIMEOUT_FIELD}


def unknown_command(name):
    if name == PYTHON_COMMAND:
        return {"argument": "cmd", "value": name, "message": "run_python is off; start the bridge with --allow-python "
                                                            "to enable it", "instead": "the modelling tools"}
    if name == VALIDATE_COMMAND:
        return {"argument": "cmd", "value": name, "message": "validate cannot check a validate call; list its calls "
                                                            "in this plan instead", "instead": "the calls themselves"}
    return {"argument": "cmd", "value": name, "message": f"unknown command {name}; call describe for the list"}


def call_problems(registry, name, args, state):
    command = registry.get(name) if name != VALIDATE_COMMAND else None
    if command is None:
        return [unknown_command(name)]
    if not isinstance(args, dict):
        return [{"argument": "args", "value": None, "message": "args must be an object"}]
    try:
        args = without_timeout(command, args)
    except BridgeError as error:
        return [{"argument": f"args.{TIMEOUT_FIELD}", "value": args.get(TIMEOUT_FIELD), "message": error.message}]
    cleaned, found = check(command.schema, args)
    if not found and command.rules is not None:
        found = command.rules(cleaned)
    return found + follow_names(command, cleaned, state, hook=not found)


def check_plan(registry, calls, state, most=MAX_PLAN_PROBLEMS):
    """Every problem of a list of {cmd, args} calls, in order, without running any. Each problem names the call by
    index and command, the argument, the value and, for a bound, the limit and what to use instead. Past most
    problems the rest are only counted, in one closing problem."""
    problems = []
    dropped = 0
    for index, call in enumerate(calls):
        name = call.get("cmd")
        found = call_problems(registry, name, call.get("args") or {}, state)
        room = max(0, most - len(problems))
        problems.extend({"call": index, "cmd": name, **problem} for problem in found[:room])
        dropped += len(found[room:])
    if dropped:
        problems.append({"call": None, "cmd": None, **more_problems(dropped, "calls", MAX_PLAN_PROBLEMS)})
    return problems


def follow_names(command, cleaned, state, hook=True):
    problems = []
    refs = references(command.schema, cleaned) if isinstance(cleaned, dict) else []
    for kind, use, name, where in refs:
        if use == EXISTS and not state.has(kind, name):
            problems.append({"argument": where, "value": name,
                             "message": f"{where} names the {kind} {name}, which neither the scene nor an earlier call "
                                        f"has; {NOT_FOUND_HINT[kind]}",
                             "instead": NOT_FOUND_HINT[kind]})
        elif use == CREATES and name in state.names[kind]:
            problems.append({"argument": where, "value": name,
                             "message": f"{where} must be an unused {kind} name, but {name} exists already or an earlier "
                                        "call makes it; choose another name or delete it first",
                             "instead": "another name, or delete first"})
    for kind, use, name, _ in refs:
        if use in (CREATES, REPLACES, ENSURES):
            state.add(kind, name)
    if hook and command.plan is not None and isinstance(cleaned, dict):
        problems.extend(command.plan(cleaned, state) or [])
    return problems
