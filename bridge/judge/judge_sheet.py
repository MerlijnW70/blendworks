"""Composes contact sheets from images, UV tiles and text."""

from array import array

import bpy
import numpy

from judge_font import GLYPH_HEIGHT, draw_text, fit_text, printable, text_width

BACKGROUND = (0.10, 0.10, 0.11, 1.0)
TEXT = (0.93, 0.93, 0.93, 1.0)
MUTED = (0.62, 0.62, 0.64, 1.0)
MARKER = (1.0, 0.55, 0.08, 1.0)
OUTLINE = (0.0, 0.0, 0.0, 1.0)
UV_EMPTY = (0.16, 0.16, 0.17, 1.0)
UV_ONCE = (0.72, 0.74, 0.76, 1.0)
UV_OVERLAP = (0.92, 0.18, 0.16, 1.0)
MARGIN = 16
GAP = 16
LABEL_HEIGHT = 36
LABEL_SCALE = 3
HEADER_SCALE = 2
HEADER_LINE = 22
MEBIBYTE = 1024 * 1024


class Canvas:
    def __init__(self, width, height, colour=BACKGROUND):
        self.width = width
        self.height = height
        self.pixels = array("f", colour) * (width * height)

    def fill_rect(self, left, top, width, height, colour):
        left_clip = max(0, left)
        right_clip = min(self.width, left + width)
        top_clip = max(0, top)
        bottom_clip = min(self.height, top + height)
        if left_clip >= right_clip or top_clip >= bottom_clip:
            return
        run = array("f", colour) * (right_clip - left_clip)
        for row in range(top_clip, bottom_clip):
            start = (row * self.width + left_clip) * 4
            self.pixels[start : start + len(run)] = run

    def paste_bottom_up(self, pixels, width, height, left, top):
        for source_row in range(height):
            target_row = top + height - 1 - source_row
            if not 0 <= target_row < self.height:
                continue
            source = source_row * width * 4
            target = (target_row * self.width + left) * 4
            self.pixels[target : target + width * 4] = pixels[source : source + width * 4]

    def save_png(self, path, name):
        image = bpy.data.images.new(name, self.width, self.height, alpha=False)
        flipped = array("f")
        row_length = self.width * 4
        for row in range(self.height - 1, -1, -1):
            flipped.extend(self.pixels[row * row_length : (row + 1) * row_length])
        image.pixels.foreach_set(flipped)
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
        bpy.data.images.remove(image)


def load_png(path):
    image = bpy.data.images.load(path, check_existing=False)
    width, height = image.size
    pixels = array("f", [0.0]) * (width * height * 4)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels, width, height


def texture_line(textures):
    if not isinstance(textures, dict):
        return "TEXTURES NOT MEASURED"
    count = int(textures.get("count", 0))
    mebibytes = int(textures.get("gpuBytes", 0)) / MEBIBYTE
    noun = "TEXTURE" if count == 1 else "TEXTURES"
    return f"{count} {noun}   GPU ESTIMATE {mebibytes:.1f} MIB (RGBA8 WITH MIPS)"


def uv_tile(grid):
    palette = numpy.array((UV_EMPTY, UV_ONCE, UV_OVERLAP), dtype=numpy.float32)
    counts = numpy.frombuffer(bytes(grid.counts), dtype=numpy.uint8)
    rows = array("f")
    rows.frombytes(palette[counts].tobytes())
    return rows, grid.size, grid.size


def crosshair(canvas, x, y, left, top, size):
    if x is None:
        return
    centre_x = left + int(round(x))
    centre_y = top + int(round(y))
    centre_x = min(max(centre_x, left), left + size - 1)
    centre_y = min(max(centre_y, top), top + size - 1)
    arm = 14
    for colour, thickness in ((OUTLINE, 6), (MARKER, 2)):
        canvas.fill_rect(centre_x - arm, centre_y - thickness // 2, arm * 2 + 1, thickness, colour)
        canvas.fill_rect(centre_x - thickness // 2, centre_y - arm, thickness, arm * 2 + 1, colour)


def compose(tiles, header_lines, path):
    tile_size = tiles[0]["size"]
    columns = min(len(tiles), 4)
    rows = (len(tiles) + columns - 1) // columns
    header_height = MARGIN + HEADER_LINE * len(header_lines)
    header_width = max(text_width(printable(text), HEADER_SCALE) for text, _ in header_lines) if header_lines else 0
    width = MARGIN * 2 + max(columns * tile_size + (columns - 1) * GAP, header_width)
    height = header_height + GAP + rows * (LABEL_HEIGHT + tile_size) + (rows - 1) * GAP + MARGIN
    canvas = Canvas(width, height)
    for index, (text, colour) in enumerate(header_lines):
        draw_text(canvas, fit_text(text, HEADER_SCALE, width - 2 * MARGIN), MARGIN, MARGIN + index * HEADER_LINE, HEADER_SCALE, colour)
    for index, tile in enumerate(tiles):
        column = index % columns
        row = index // columns
        left = MARGIN + column * (tile_size + GAP)
        top = header_height + GAP + row * (LABEL_HEIGHT + tile_size + GAP)
        label_top = top + (LABEL_HEIGHT - GLYPH_HEIGHT * LABEL_SCALE) // 2 - 2
        draw_text(canvas, fit_text(tile["label"], LABEL_SCALE, tile_size), left, label_top, LABEL_SCALE, TEXT)
        canvas.paste_bottom_up(tile["pixels"], tile_size, tile_size, left, top + LABEL_HEIGHT)
        marker = tile.get("marker")
        if marker is not None:
            crosshair(canvas, marker[0], marker[1], left, top + LABEL_HEIGHT, tile_size)
    canvas.save_png(path, "contact-sheet")
    return width, height
