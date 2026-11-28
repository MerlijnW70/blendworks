"""L-system expression scanner and evaluator."""

import math
import re

from .errors import bad_args

NUMBER = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+(?![\w.]))?")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FUNCTIONS = {"sqrt": (1, math.sqrt), "abs": (1, abs), "min": (2, min), "max": (2, max), "floor": (1, math.floor), "exp": (1, math.exp), "ln": (1, math.log)}


def truth(value):
    return 1.0 if value != 0 else 0.0


def binary(left, right, operation):
    return lambda env: operation(left(env), right(env))


class Scanner:
    def __init__(self, text, position, label, names, constants):
        self.text = text
        self.position = position
        self.label = label
        self.names = frozenset(names)
        self.constants = constants

    def fail(self, message, at=None):
        raise bad_args(f"{self.label}, position {(self.position if at is None else at) + 1}: {message}")

    def skip(self):
        while self.position < len(self.text) and self.text[self.position].isspace():
            self.position += 1

    def peek(self):
        self.skip()
        return self.text[self.position] if self.position < len(self.text) else ""

    def take(self, *options):
        self.skip()
        for option in options:
            if self.text.startswith(option, self.position):
                self.position += len(option)
                return option
        return None

    def expect(self, option, what):
        if self.take(option) is None:
            self.fail(f"expected {what}")

    def expression(self):
        return self.logical_or()

    def logical_or(self):
        left = self.logical_and()
        while self.take("||", "|"):
            left = binary(left, self.logical_and(), lambda a, b: truth(a != 0 or b != 0))
        return left

    def logical_and(self):
        left = self.equality()
        while self.take("&&", "&"):
            left = binary(left, self.equality(), lambda a, b: truth(a != 0 and b != 0))
        return left

    def equality(self):
        left = self.relation()
        while True:
            operator = self.take("==", "!=", "=")
            if operator is None:
                return left
            if operator == "!=":
                left = binary(left, self.relation(), lambda a, b: truth(a != b))
            else:
                left = binary(left, self.relation(), lambda a, b: truth(a == b))

    def relation(self):
        left = self.additive()
        while True:
            operator = self.take("<=", ">=", "<", ">")
            if operator is None:
                return left
            right = self.additive()
            test = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, ">": lambda a, b: a > b}[operator]
            left = binary(left, right, lambda a, b, test=test: truth(test(a, b)))

    def additive(self):
        left = self.term()
        while True:
            operator = self.take("+", "-")
            if operator is None:
                return left
            right = self.term()
            left = binary(left, right, (lambda a, b: a + b) if operator == "+" else (lambda a, b: a - b))

    def term(self):
        left = self.unary()
        while True:
            operator = self.take("*", "/")
            if operator is None:
                return left
            right = self.unary()
            left = binary(left, right, (lambda a, b: a * b) if operator == "*" else (lambda a, b: a / b))

    def unary(self):
        if self.take("-"):
            inner = self.unary()
            return lambda env: -inner(env)
        if self.peek() == "!" and not self.text.startswith("!=", self.position):
            self.position += 1
            inner = self.unary()
            return lambda env: 1.0 if inner(env) == 0 else 0.0
        return self.power()

    def power(self):
        base = self.primary()
        if self.take("^"):
            return binary(base, self.unary(), math.pow)
        return base

    def primary(self):
        self.skip()
        start = self.position
        if self.take("("):
            inner = self.expression()
            self.expect(")", "a closing parenthesis")
            return inner
        found = NUMBER.match(self.text, start)
        if found:
            self.position = found.end()
            value = float(found.group())
            return lambda env: value
        found = NAME.match(self.text, start)
        if not found:
            self.fail("expected a number, a parameter, a function or a parenthesis")
        word = found.group()
        self.position = found.end()
        if word in FUNCTIONS:
            return self.call(word, start)
        if word in self.names:
            return lambda env: env[word]
        if word in self.constants:
            value = float(self.constants[word])
            return lambda env: value
        known = sorted(self.names | set(self.constants))
        self.fail(f"unknown name {word}" + (f"; known names are {', '.join(known)}" if known else "; this place takes numbers only"), start)

    def call(self, word, start):
        arity, function = FUNCTIONS[word]
        self.expect("(", f"( after {word}")
        arguments = [self.expression()]
        while self.take(","):
            arguments.append(self.expression())
        self.expect(")", "a closing parenthesis")
        if len(arguments) != arity:
            self.fail(f"{word} takes {arity} argument(s), not {len(arguments)}", start)
        return lambda env: float(function(*(argument(env) for argument in arguments)))

    def arguments(self):
        self.expect("(", "(")
        found = [self.expression()]
        while self.take(","):
            found.append(self.expression())
        self.expect(")", "a closing parenthesis")
        return found

    def finished(self):
        self.skip()
        return self.position >= len(self.text)
