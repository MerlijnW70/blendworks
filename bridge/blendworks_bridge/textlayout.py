"""Text layout: splitting runs and placing glyph loops."""

import math
import re

from .errors import bad_args
from .outlines import drop_close, simplify_loop
from .glyphs import CAP_HEIGHT, CHARACTERS, FLATNESS, bounds_of, nest, symbol_loops, symbol_names, text_loops

TOKEN = re.compile(r"\{([a-z_]+)\}")
RUN_GAP = 0.12
ALIGNS = ("left", "centre", "right")
VALIGNS = ("middle", "baseline")
SIMPLIFY = FLATNESS / 4.0
EAR_SLOPE = 1.0 / 400.0
MIN_EDGE = 2.0 * FLATNESS


def split_runs(text):
    runs = []
    plain = []

    def flush():
        if plain:
            runs.append(("text", "".join(plain)))
            plain.clear()

    position = 0
    while position < len(text):
        token = TOKEN.match(text, position)
        if token is not None:
            if token.group(1) not in symbol_names():
                raise bad_args(f"{{{token.group(1)}}} is not a symbol; the built-in symbols are {', '.join(symbol_names())}")
            flush()
            runs.append(("symbol", token.group(1)))
            position = token.end()
        elif text[position] in CHARACTERS:
            flush()
            runs.append(("symbol", CHARACTERS[text[position]]))
            position += 1
        else:
            plain.append(text[position])
            position += 1
    flush()
    return runs


def run_loops(ctx, runs, size, spacing, font):
    loops = []
    cursor = 0.0
    for kind, value in runs:
        if kind == "symbol":
            found, advance = symbol_loops(value, size)
            moved = [[(x + cursor, y) for x, y in loop] for loop in found]
            width = advance
        else:
            found = text_loops(ctx, value, size, spacing, font)
            if not found:
                cursor += len(value) * 0.3 * size
                continue
            moved = [[(x + cursor, y) for x, y in loop] for loop in found]
            width = max(x for loop in found for x, _ in loop) + RUN_GAP * size
        loops.extend(moved)
        cursor += width
    return loops


def place(shapes, align, valign, size, rotation):
    low_x, _, high_x, _ = bounds_of(shapes)
    shift_x = {"left": -low_x, "centre": -(low_x + high_x) / 2.0, "right": -high_x}[align]
    shift_y = -CAP_HEIGHT * size / 2.0 if valign == "middle" else 0.0
    angle = math.radians(rotation)
    cosine, sine = math.cos(angle), math.sin(angle)

    def move(point):
        x, y = point[0] + shift_x, point[1] + shift_y
        return (x * cosine - y * sine, x * sine + y * cosine)

    return [([move(point) for point in outline], [[move(point) for point in hole] for hole in holes]) for outline, holes in shapes], high_x - low_x


def min_edge(size):
    return MIN_EDGE * size


def text_shapes(ctx, text, size, spacing, font, align, valign, rotation):
    loops = run_loops(ctx, split_runs(text), size, spacing, font)
    if not loops:
        raise bad_args("the text has nothing to engrave; it holds only spaces")
    return place(nest([simplify_loop(drop_close(loop, min_edge(size)), SIMPLIFY * size, EAR_SLOPE) for loop in loops]), align, valign, size, rotation)
