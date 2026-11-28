"""Composes a LOD comparison sheet."""

from array import array

import numpy as np

from judge_font import GLYPH_HEIGHT, draw_text, fit_text, printable, text_width
from judge_sheet import BACKGROUND, MUTED, TEXT, Canvas
from package_metrics import BACKGROUND as TILE_GREY

MARGIN = 16
GAP = 12
LABEL_SCALE = 2
LABEL_HEIGHT = 24
HEADER_SCALE = 2
HEADER_LINE = 22
SECTION_SCALE = 3
SECTION_HEIGHT = 34


def opaque(rgba):
    alpha = rgba[..., 3:4]
    colour = rgba[..., :3] * alpha + TILE_GREY * (1.0 - alpha)
    return np.concatenate([colour, np.ones_like(alpha)], axis=2)


def pixel_buffer(rgba):
    buffer = array("f")
    buffer.frombytes(np.ascontiguousarray(opaque(rgba), dtype=np.float32).tobytes())
    return buffer


def compose_sheet(header_lines, sections, cell, path):
    columns = max(len(row["tiles"]) for section in sections for row in section["rows"])
    header_width = max((text_width(printable(text), HEADER_SCALE) for text, _ in header_lines), default=0)
    width = MARGIN * 2 + max(columns * cell + (columns - 1) * GAP, header_width)
    rows_total = sum(len(section["rows"]) for section in sections)
    height = MARGIN + HEADER_LINE * len(header_lines) + len(sections) * (SECTION_HEIGHT + GAP) + rows_total * (LABEL_HEIGHT + cell + GAP) + MARGIN
    canvas = Canvas(width, height, BACKGROUND)
    for index, (text, colour) in enumerate(header_lines):
        draw_text(canvas, fit_text(text, HEADER_SCALE, width - 2 * MARGIN), MARGIN, MARGIN + index * HEADER_LINE, HEADER_SCALE, colour)
    top = MARGIN + HEADER_LINE * len(header_lines)
    for section in sections:
        draw_text(canvas, fit_text(section["title"], SECTION_SCALE, width - 2 * MARGIN), MARGIN, top + 6, SECTION_SCALE, TEXT)
        top += SECTION_HEIGHT + GAP
        for row in section["rows"]:
            for column, tile in enumerate(row["tiles"]):
                left = MARGIN + column * (cell + GAP)
                label = fit_text(tile["label"], LABEL_SCALE, cell)
                draw_text(canvas, label, left, top + (LABEL_HEIGHT - GLYPH_HEIGHT * LABEL_SCALE) // 2, LABEL_SCALE, row.get("colour", MUTED))
                image = tile["pixels"]
                size_y, size_x = image.shape[0], image.shape[1]
                canvas.paste_bottom_up(pixel_buffer(image), size_x, size_y, left + (cell - size_x) // 2, top + LABEL_HEIGHT + (cell - size_y) // 2)
            top += LABEL_HEIGHT + cell + GAP
    canvas.save_png(path, "lod-sheet")
    return width, height
