import math

import numpy

from .errors import bad_args
from .lsystem_rules import format_word


class Derivation:
    def __init__(self, word, lengths, applications):
        self.word = word
        self.lengths = lengths
        self.applications = applications


class RuleTable:
    def __init__(self, rules):
        self.by_symbol = {}
        for rule in rules:
            self.by_symbol.setdefault(rule.symbol, []).append(rule)
        self.lows = {}

    def candidates(self, symbol, arity):
        return [rule for rule in self.by_symbol.get(symbol, ()) if rule.arity == arity]

    def low(self, symbol, arity):
        key = (symbol, arity)
        if key not in self.lows:
            found = self.candidates(symbol, arity)
            sure = found and all(rule.condition is None for rule in found)
            self.lows[key] = min(len(rule.successor) for rule in found) if sure else 1
        return self.lows[key]


def guaranteed_length(word, table):
    return sum(table.low(symbol, len(params)) for symbol, params in word)


def check_arithmetic(value, rule, module):
    if not math.isfinite(value):
        raise bad_args(f"{rule.label} applied to {format_word([module])} gives a value that is not a finite number")
    return value


def evaluate(function, env, rule, module):
    try:
        return check_arithmetic(function(env), rule, module)
    except ZeroDivisionError:
        raise bad_args(f"{rule.label} applied to {format_word([module])} divides by zero") from None
    except (ArithmeticError, ValueError) as error:
        raise bad_args(f"{rule.label} applied to {format_word([module])} cannot be computed ({error})") from None


def pick(applicable, rng):
    if len(applicable) == 1 or applicable[0].probability is None:
        return applicable[0]
    total = sum(rule.probability for rule in applicable)
    draw = rng.random() * total
    running = 0.0
    for rule in applicable:
        running += rule.probability
        if draw < running:
            return rule
    return applicable[-1]


def apply_rule(module, table, rng):
    symbol, params = module
    candidates = table.by_symbol.get(symbol)
    if not candidates:
        return None, None
    applicable = []
    for rule in candidates:
        if rule.arity != len(params):
            continue
        if rule.condition is not None:
            if evaluate(rule.condition, dict(zip(rule.names, params)), rule, module) == 0:
                continue
        applicable.append(rule)
    if not applicable:
        return None, None
    return pick(applicable, rng), params


def instantiate(rule, params, module):
    if rule.constant is not None:
        return rule.constant
    env = dict(zip(rule.names, params))
    return [(symbol, tuple(evaluate(argument, env, rule, module) for argument in arguments)) for symbol, arguments in rule.successor]


def too_long(step, before, at_least, cap):
    reach = f"at least {at_least}" if at_least else f"more than {cap}"
    return bad_args(f"derivation step {step} would grow the string from {before} modules to {reach}, past the cap of {cap} (max_length); lower iterations or raise max_length")


def rewrite(word, table, rng, step, cap, used):
    floor = guaranteed_length(word, table)
    if floor > cap:
        raise too_long(step, len(word), floor, cap)
    out = []
    for module in word:
        rule, params = apply_rule(module, table, rng)
        if rule is None:
            out.append(module)
        else:
            used[rule.index] = used.get(rule.index, 0) + 1
            out.extend(instantiate(rule, params, module))
        if len(out) > cap:
            raise too_long(step, len(word), None, cap)
    return out


def derive(axiom, rules, iterations, max_length, seed):
    table = RuleTable(rules)
    if len(axiom) > max_length:
        raise bad_args(f"the axiom has {len(axiom)} modules, past the cap of {max_length} (max_length)")
    rng = numpy.random.default_rng([seed])
    word = list(axiom)
    lengths = [len(word)]
    used = {}
    for step in range(1, iterations + 1):
        word = rewrite(word, table, rng, step, max_length, used)
        lengths.append(len(word))
    return Derivation(word, lengths, used)
