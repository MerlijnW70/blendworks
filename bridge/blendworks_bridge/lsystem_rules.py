"""L-system rule and axiom parsing."""

from .errors import bad_args
from .lsystem_expr import NAME, Scanner

LETTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
TURTLE = frozenset("+-&^\\/|!'$")
BRACKETS = frozenset("[]")
SYMBOLS = LETTERS | TURTLE
ARROWS = ("->", "→")
UNSUPPORTED = {"{": "polygons", "}": "polygons", ".": "polygon vertices", "%": "cutting a branch", "<": "context", ">": "context", "`": "colour decrement", ",": "a stray comma", ")": "a stray parenthesis", "(": "a stray parenthesis"}
PROBABILITY_TOLERANCE = 1e-6


def refuse_symbol(scanner, symbol):
    if symbol in UNSUPPORTED:
        extra = " (leaves and flowers are placed with the organs option)" if symbol in "{}." else ""
        scanner.fail(f"{symbol!r} is not supported: {UNSUPPORTED[symbol]}{extra}")
    scanner.fail(f"{symbol!r} is not an L-system symbol; use a letter or one of + - & ^ \\ / | ! ' $ [ ]")


def read_modules(scanner, stop):
    modules = []
    while True:
        scanner.skip()
        if scanner.finished() or scanner.peek() in stop:
            return modules
        symbol = scanner.text[scanner.position]
        start = scanner.position
        if symbol not in SYMBOLS and symbol not in BRACKETS:
            refuse_symbol(scanner, symbol)
        scanner.position += 1
        arguments = []
        if scanner.peek() == "(":
            if symbol in BRACKETS:
                scanner.fail(f"{symbol!r} takes no parameters", start)
            arguments = scanner.arguments()
        modules.append((symbol, tuple(arguments), start))


class Rule:
    def __init__(self, index, text, symbol, names, condition, successor, probability):
        self.index = index
        self.label = f"rule {index} ({text.strip()})"
        self.symbol = symbol
        self.names = tuple(names)
        self.condition = condition
        self.successor = tuple((symbol_, arguments) for symbol_, arguments in successor)
        self.constant = tuple((symbol_, ()) for symbol_, arguments in successor) if all(not arguments for _, arguments in successor) else None
        self.probability = probability

    @property
    def arity(self):
        return len(self.names)


def parse_axiom(text, constants):
    scanner = Scanner(text, 0, "axiom", (), constants)
    modules = read_modules(scanner, "")
    if not scanner.finished():
        scanner.fail("unexpected text")
    if not modules:
        scanner.fail("the axiom is empty")
    return [(symbol, tuple(argument({}) for argument in arguments)) for symbol, arguments, _ in modules]


def split_arrow(text, label):
    found = [(text.find(arrow), arrow) for arrow in ARROWS if arrow in text]
    if not found:
        raise bad_args(f"{label}: expected '->' between the predecessor and the successor")
    position, arrow = min(found)
    if any(other in text[position + len(arrow):] for other in ARROWS):
        raise bad_args(f"{label}, position {position + len(arrow) + 1}: a rule has one '->'")
    return position, position + len(arrow)


def parse_predecessor(text, arrow, label, constants):
    scanner = Scanner(text[:arrow], 0, label, (), constants)
    scanner.skip()
    if scanner.finished():
        scanner.fail("the predecessor is empty")
    symbol = scanner.text[scanner.position]
    if symbol not in SYMBOLS:
        if symbol in BRACKETS:
            scanner.fail("brackets replace themselves and cannot be rewritten")
        refuse_symbol(scanner, symbol)
    scanner.position += 1
    names = []
    if scanner.peek() == "(":
        scanner.position += 1
        while True:
            scanner.skip()
            found = NAME.match(scanner.text, scanner.position)
            if not found:
                scanner.fail("expected a parameter name")
            if found.group() in names:
                scanner.fail(f"parameter {found.group()} is listed twice")
            names.append(found.group())
            scanner.position = found.end()
            if scanner.take(")"):
                break
            scanner.expect(",", "a comma or a closing parenthesis")
    condition = None
    if scanner.take(":"):
        rest = scanner.text[scanner.position:].strip()
        if rest not in ("", "*"):
            condition_scanner = Scanner(text[:arrow], scanner.position, label, names, constants)
            condition = condition_scanner.expression()
            if not condition_scanner.finished():
                condition_scanner.fail("unexpected text after the condition")
    elif not scanner.finished():
        scanner.fail("expected ':' and a condition, or '->'")
    return symbol, names, condition


def parse_rule(index, text, constants):
    label = f"rule {index} ({text.strip()})"
    arrow, after = split_arrow(text, label)
    symbol, names, condition = parse_predecessor(text, arrow, label, constants)
    scanner = Scanner(text, after, label, names, constants)
    successor = read_modules(scanner, ":")
    probability = None
    if scanner.take(":"):
        weight = Scanner(text, scanner.position, label, (), constants)
        weight.skip()
        start = weight.position
        probability = weight.expression()({})
        if not weight.finished():
            weight.fail("unexpected text after the probability")
        if not 0.0 < probability <= 1.0:
            weight.fail(f"the probability {probability:g} is not in (0, 1]", start)
    return Rule(index, text, symbol, names, condition, [(sym, arguments) for sym, arguments, _ in successor], probability)


def parse_rules(texts, constants):
    rules = [parse_rule(index + 1, text, constants) for index, text in enumerate(texts)]
    check_probabilities(rules)
    return rules


def check_probabilities(rules):
    groups = {}
    for rule in rules:
        groups.setdefault((rule.symbol, rule.arity), []).append(rule)
    for (symbol, arity), group in groups.items():
        given = [rule.probability is not None for rule in group]
        numbers = ", ".join(str(rule.index) for rule in group)
        if any(given) and not all(given):
            raise bad_args(f"rules {numbers} all rewrite {symbol} with {arity} parameter(s): either every one has a probability or none does")
        if all(given) and all(rule.condition is None for rule in group):
            total = sum(rule.probability for rule in group)
            if abs(total - 1.0) > PROBABILITY_TOLERANCE:
                raise bad_args(f"the probabilities of rules {numbers} for {symbol} add up to {total:g}, not 1 [S1, 1.7]")
        if len(group) > 1 and not any(given) and all(rule.condition is None for rule in group):
            raise bad_args(f"rules {numbers} all rewrite {symbol} with {arity} parameter(s) without a condition or a probability; only the first could ever apply")


def format_word(word):
    parts = []
    for symbol, params in word:
        parts.append(symbol if not params else f"{symbol}({','.join(format(value, '.6g') for value in params)})")
    return "".join(parts)

