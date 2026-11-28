"""L-system turtle: state, vector helpers and organs placed along the word."""

import math

from .errors import bad_args
from .lsystem_rules import format_word
from .tree_skeleton import Skeleton

UP = (0.0, 0.0, 1.0)
LEFT = (-1.0, 0.0, 0.0)
EXPONENT_RANGE = (1.8, 3.0)


QUARTER_TURNS = ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))


def cosine_sine(degrees):
    quarter = degrees / 90.0
    if quarter == round(quarter):
        return QUARTER_TURNS[int(round(quarter)) % 4]
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


def combine(first, second, cosine, sine):
    return (
        tuple(a * cosine + b * sine for a, b in zip(first, second)),
        tuple(b * cosine - a * sine for a, b in zip(first, second)),
    )


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def about_axis(vector, axis, cosine, sine):
    along = dot(vector, axis)
    side = cross(axis, vector)
    return tuple(vector[i] * cosine + side[i] * sine + axis[i] * along * (1.0 - cosine) for i in range(3))


class State:
    __slots__ = ("position", "heading", "left", "up", "width", "colour", "order", "node")

    def __init__(self, width):
        self.position = (0.0, 0.0, 0.0)
        self.heading, self.left = UP, LEFT
        self.up = cross(self.heading, self.left)
        self.width = width
        self.colour = 0
        self.order = 0
        self.node = 0

    def copy(self):
        other = State.__new__(State)
        for name in State.__slots__:
            setattr(other, name, getattr(self, name))
        return other

    def turn(self, degrees):
        cosine, sine = cosine_sine(degrees)
        self.heading, self.left = combine(self.heading, self.left, cosine, sine)

    def pitch(self, degrees):
        cosine, sine = cosine_sine(degrees)
        self.heading, self.up = combine(self.heading, tuple(-value for value in self.up), cosine, sine)
        self.up = tuple(-value for value in self.up)

    def roll(self, degrees):
        cosine, sine = cosine_sine(degrees)
        self.left, self.up = combine(self.left, tuple(-value for value in self.up), cosine, sine)
        self.up = tuple(-value for value in self.up)

    def level(self):
        side = cross(UP, self.heading)
        size = math.sqrt(dot(side, side))
        if size < 1e-9:
            return
        self.left = tuple(value / size for value in side)
        self.up = cross(self.heading, self.left)

    def bend(self, vector, strength):
        axis = cross(self.heading, vector)
        size = math.sqrt(dot(axis, axis))
        if size < 1e-12 or strength == 0.0:
            return
        unit = tuple(value / size for value in axis)
        angle = strength * size
        cosine, sine = math.cos(angle), math.sin(angle)
        self.heading = about_axis(self.heading, unit, cosine, sine)
        self.left = about_axis(self.left, unit, cosine, sine)
        self.up = about_axis(self.up, unit, cosine, sine)

    def advance(self, length):
        self.position = tuple(self.position[i] + length * self.heading[i] for i in range(3))


class Organ:
    def __init__(self, symbol, state, scale):
        self.symbol = symbol
        self.position = state.position
        self.heading, self.left, self.up = state.heading, state.left, state.up
        self.colour = state.colour
        self.scale = scale


class Settings:
    def __init__(self, angle, step, width, width_ratio, tropism, tropism_strength, branch_taper, max_nodes, organ_symbols):
        self.angle = angle
        self.step = step
        self.width = width
        self.width_ratio = width_ratio
        self.tropism = tropism
        self.tropism_strength = tropism_strength
        self.branch_taper = branch_taper
        self.max_nodes = max_nodes
        self.organ_symbols = frozenset(organ_symbols)


class Plant:
    def __init__(self, skeleton, organs, stats):
        self.skeleton = skeleton
        self.organs = organs
        self.stats = stats


def check_word(word, settings):
    depth = 0
    nodes = 1
    for index, (symbol, params) in enumerate(word):
        if symbol == "[":
            depth += 1
        elif symbol == "]":
            depth -= 1
            if depth < 0:
                raise bad_args(f"the derived string has a ']' without a '[' at module {index + 1}: {format_word(word[max(0, index - 6):index + 1])}")
        elif symbol in "Ff" and symbol not in settings.organ_symbols:
            nodes += 1
    if depth:
        raise bad_args(f"the derived string leaves {depth} '[' open")
    if nodes > settings.max_nodes:
        raise bad_args(f"the string draws {nodes} nodes, past the cap of {settings.max_nodes} (max_nodes); lower iterations or raise max_nodes")
    return nodes


def exponent_for(width_ratio):
    if width_ratio >= 1.0:
        return EXPONENT_RANGE[1]
    return round(min(max(math.log(2.0) / -math.log(width_ratio), EXPONENT_RANGE[0]), EXPONENT_RANGE[1]), 9)


def first_value(params, default):
    return params[0] if params else default


def interpret(word, settings):
    nodes = check_word(word, settings)
    positions = [(0.0, 0.0, 0.0)]
    parents = [-1]
    radii = [0.0]
    orders = [0]
    stack = []
    state = State(1.0)
    organs = []
    segments = moves = deepest = 0
    for index, (symbol, params) in enumerate(word):
        if symbol in ("F", "f") and symbol not in settings.organ_symbols:
            length = first_value(params, 1.0)
            if length < 0.0:
                raise bad_args(f"module {index + 1}, {format_word([word[index]])}: a step of negative length")
            if length == 0.0:
                continue
            state.advance(length * settings.step)
            positions.append(state.position)
            parents.append(state.node)
            radii.append(0.5 * state.width * settings.width)
            orders.append(state.order)
            state.node = len(positions) - 1
            if symbol == "F":
                segments += 1
                if settings.tropism_strength:
                    state.bend(settings.tropism, settings.tropism_strength)
            else:
                moves += 1
        elif symbol in settings.organ_symbols:
            organs.append(Organ(symbol, state, first_value(params, 1.0)))
        elif symbol == "+":
            state.turn(first_value(params, settings.angle))
        elif symbol == "-":
            state.turn(-first_value(params, settings.angle))
        elif symbol == "&":
            state.pitch(first_value(params, settings.angle))
        elif symbol == "^":
            state.pitch(-first_value(params, settings.angle))
        elif symbol == "\\":
            state.roll(first_value(params, settings.angle))
        elif symbol == "/":
            state.roll(-first_value(params, settings.angle))
        elif symbol == "|":
            state.turn(180.0)
        elif symbol == "$":
            state.level()
        elif symbol == "!":
            state.width = params[0] if params else state.width * settings.width_ratio
        elif symbol == "'":
            state.colour = int(params[0]) if params else state.colour + 1
        elif symbol == "[":
            stack.append(state)
            deepest = max(deepest, len(stack))
            state = state.copy()
            state.order += 1
            if settings.branch_taper:
                state.width *= settings.width_ratio
        elif symbol == "]":
            state = stack.pop()
    if len(positions) < 2:
        raise bad_args("the derived string draws no segment; it needs at least one F")
    radii[0] = radii[1]
    skeleton = Skeleton(positions, parents, radii, orders, [0] * len(positions), exponent_for(settings.width_ratio), min(radii), "lsystem")
    stats = {"segments": segments, "moves": moves, "branch_depth": deepest, "nodes": nodes}
    return Plant(skeleton, organs, stats)
