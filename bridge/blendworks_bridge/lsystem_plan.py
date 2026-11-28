"""L-system planning: resolves a request into a checked word with organs."""

import math

from .errors import bad_args
from .kit_limits import MAX_INSTANCES
from .lsystem_derive import derive
from .lsystem_presets import PRESETS
from .lsystem_rules import format_word, parse_axiom, parse_rules
from .lsystem_turtle import Settings, interpret

DEFAULTS = {
    "iterations": 5,
    "angle": 22.5,
    "step": 0.1,
    "width": 0.01,
    "width_ratio": 1.0 / math.sqrt(2.0),
    "branch_taper": True,
    "tropism": {"vector": [0.0, 0.0, -1.0], "strength": 0.0},
    "rules": [],
}
PRESET_FIELDS = ("axiom", "rules", "iterations", "angle", "step", "width", "width_ratio", "branch_taper", "tropism")
WORD_REPLY_LIMIT = 2000


class Planned:
    def __init__(self, plant, derivation, settings, organ_counts):
        self.plant = plant
        self.derivation = derivation
        self.settings = settings
        self.organ_counts = organ_counts


def resolve(args):
    name = args.get("preset")
    preset = PRESETS[name] if name is not None else {}
    if name is None and "axiom" not in args:
        raise bad_args("give an axiom, or a preset that has one")
    chosen = {}
    for field in PRESET_FIELDS:
        if field in args:
            chosen[field] = args[field]
        elif field in preset:
            chosen[field] = preset[field]
        elif field in DEFAULTS:
            chosen[field] = DEFAULTS[field]
    constants = dict(preset.get("constants", {}))
    for entry in args.get("constants", ()):
        constants[entry["name"]] = entry["value"]
    chosen["constants"] = constants
    return chosen


def check_organs(organs):
    seen = set()
    for entry in organs:
        symbol = entry["symbol"]
        if len(symbol) != 1 or not symbol.isalpha() or not symbol.isascii() or symbol in "Ff":
            raise bad_args(f"organ symbol {symbol!r} must be one letter other than F and f, which draw")
        if symbol in seen:
            raise bad_args(f"organ symbol {symbol} is given twice")
        seen.add(symbol)
    return seen


def plan(args):
    chosen = resolve(args)
    constants = chosen["constants"]
    organ_symbols = check_organs(args.get("organs", ()))
    axiom = parse_axiom(chosen["axiom"], constants)
    rules = parse_rules(chosen["rules"], constants)
    derivation = derive(axiom, rules, chosen["iterations"], args["max_length"], args["seed"])
    tropism = chosen["tropism"]
    settings = Settings(chosen["angle"], chosen["step"], chosen["width"], chosen["width_ratio"], tuple(tropism["vector"]), tropism["strength"], chosen["branch_taper"], args["max_nodes"], organ_symbols)
    counts = {symbol: sum(1 for module in derivation.word if module[0] == symbol) for symbol in sorted(organ_symbols)}
    if sum(counts.values()) > MAX_INSTANCES:
        raise bad_args(f"the string carries {sum(counts.values())} organs, past the cap of {MAX_INSTANCES}; lower iterations or place fewer organ symbols")
    plant = interpret(derivation.word, settings)
    return Planned(plant, derivation, settings, counts)


def word_reply(derivation):
    text = format_word(derivation.word)
    return text[:WORD_REPLY_LIMIT], len(text) > WORD_REPLY_LIMIT
