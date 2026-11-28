"""Reads image dimensions from BMP, TGA, TIFF, EXR and HDR headers."""

import os
import struct

import bpy

from judge_common import JudgeError, quoted
from judge_gltf import HEADER_BYTES, MAX_IMAGE_PIXELS, MAX_IMAGE_SIDE, image_size

TGA_TYPES = {1, 2, 3, 9, 10, 11}
TIFF_WIDTH = 256
TIFF_HEIGHT = 257
EXR_MAGIC = b"\x76\x2f\x31\x01"
HDR_MAGICS = (b"#?RADIANCE", b"#?RGBE")
UDIM_TOKEN = "<UDIM>"


def bmp_size(data):
    if data[:2] != b"BM" or len(data) < 26:
        return None
    width, height = struct.unpack("<ii", data[18:26])
    return abs(width), abs(height)


def tga_size(data):
    if len(data) < 18 or data[2] not in TGA_TYPES:
        return None
    return struct.unpack("<HH", data[12:16])


def tiff_size(data):
    order = {b"II": "<", b"MM": ">"}.get(data[:2])
    if order is None or len(data) < 8 or struct.unpack(order + "H", data[2:4])[0] != 42:
        return None
    position = struct.unpack(order + "I", data[4:8])[0]
    if position + 2 > len(data):
        return None
    count = struct.unpack(order + "H", data[position : position + 2])[0]
    found = {}
    for index in range(count):
        start = position + 2 + 12 * index
        if start + 12 > len(data):
            return None
        tag, kind = struct.unpack(order + "HH", data[start : start + 4])
        if tag in (TIFF_WIDTH, TIFF_HEIGHT):
            found[tag] = struct.unpack(order + ("H" if kind == 3 else "I"), data[start + 8 : start + (10 if kind == 3 else 12)])[0]
    return (found[TIFF_WIDTH], found[TIFF_HEIGHT]) if len(found) == 2 else None


def exr_size(data):
    if data[:4] != EXR_MAGIC:
        return None
    position = 8
    while position < len(data):
        end = data.find(b"\x00", position)
        if end < 0 or end == position:
            return None
        name = data[position:end]
        kind_end = data.find(b"\x00", end + 1)
        if kind_end < 0 or kind_end + 5 > len(data):
            return None
        length = struct.unpack("<i", data[kind_end + 1 : kind_end + 5])[0]
        value = data[kind_end + 5 : kind_end + 5 + length]
        if name == b"dataWindow" and len(value) == 16:
            x_min, y_min, x_max, y_max = struct.unpack("<iiii", value)
            return x_max - x_min + 1, y_max - y_min + 1
        position = kind_end + 5 + length
    return None


def hdr_size(data):
    if not data.startswith(HDR_MAGICS):
        return None
    for line in data.split(b"\n")[1:64]:
        parts = line.split()
        if len(parts) == 4 and parts[0] in (b"-Y", b"+Y") and parts[2] in (b"+X", b"-X") and parts[1].isdigit() and parts[3].isdigit():
            return int(parts[3]), int(parts[1])
    return None


def any_size(data, targa):
    for reader in (image_size, bmp_size, tiff_size, exr_size, hdr_size):
        size = reader(data)
        if size is not None:
            return size
    return tga_size(data) if targa else None


def read_header(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(HEADER_BYTES)
    except OSError:
        return None


def image_files(image):
    path = bpy.path.abspath(image.filepath, library=image.library)
    if image.source == "TILED" and UDIM_TOKEN in path:
        return [path.replace(UDIM_TOKEN, str(tile.number)) for tile in image.tiles]
    return [path]


def image_sizes(image):
    if image.source == "GENERATED":
        return [(int(image.generated_width), int(image.generated_height))]
    targa = image.file_format == "TARGA" or os.path.splitext(image.filepath)[1].lower() in (".tga", ".tpic")
    if image.packed_file is not None:
        headers = [bytes(image.packed_file.data[:HEADER_BYTES])]
    elif image.source in ("FILE", "SEQUENCE", "TILED"):
        headers = [read_header(path) for path in image_files(image)]
    elif image.source in ("VIEWER",):
        return []
    else:
        raise JudgeError("unbounded_image", f"the judge cannot bound the size of the {image.source.lower()} image {quoted(image.name)} before loading it")
    sizes = []
    for header in headers:
        if header is None:
            continue
        size = any_size(header, targa)
        if size is None:
            raise JudgeError("unbounded_image", f"the judge cannot read the size of image {quoted(image.name)} from its header; deliver PNG, JPEG, WebP, KTX2, BMP, TGA, TIFF, HDR or EXR")
        sizes.append(size)
    return sizes


def bound_images():
    total = 0
    for image in bpy.data.images:
        if image.type in ("RENDER_RESULT", "COMPOSITING"):
            continue
        for width, height in image_sizes(image):
            if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
                raise JudgeError("image_too_large", f"image {quoted(image.name)} is {width} x {height} pixels, over the judge's limit of {MAX_IMAGE_SIDE} per side")
            total += width * height
            if total > MAX_IMAGE_PIXELS:
                raise JudgeError("image_too_large", f"the images hold more than {MAX_IMAGE_PIXELS} pixels together, the judge's limit")
    return total
