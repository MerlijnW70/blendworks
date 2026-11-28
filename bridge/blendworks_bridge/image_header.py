"""Reads image dimensions from PNG, JPEG, WebP and EXR headers without loading pixels."""

import struct

from .errors import bad_args

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXR_MAGIC = b"\x76\x2f\x31\x01"
JPEG_FRAMES = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
HEADER_BYTES = 1024 * 1024


def image_dimensions(path):
    with open(path, "rb") as handle:
        data = handle.read(HEADER_BYTES)
    try:
        return dimensions_of(data)
    except (ValueError, IndexError, struct.error) as error:
        raise bad_args(f"the image header is damaged: {error}") from error


def dimensions_of(data):
    if data.startswith(PNG_SIGNATURE):
        return png_dimensions(data)
    if data.startswith(b"\xff\xd8"):
        return jpeg_dimensions(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return webp_dimensions(data)
    if data.startswith(EXR_MAGIC):
        return exr_dimensions(data)
    raise bad_args("the file is not a PNG, JPEG, WebP or OpenEXR image")


def png_dimensions(data):
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise bad_args("the PNG file has no header chunk")
    return struct.unpack(">II", data[16:24])


def jpeg_dimensions(data):
    position = 2
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            raise bad_args("the JPEG file is damaged")
        marker = data[position + 1]
        if marker == 0xFF:
            position += 1
            continue
        if marker in (0x01,) or 0xD0 <= marker <= 0xD7:
            position += 2
            continue
        length = struct.unpack(">H", data[position + 2 : position + 4])[0]
        if marker in JPEG_FRAMES:
            if position + 9 > len(data):
                break
            height, width = struct.unpack(">HH", data[position + 5 : position + 9])
            return width, height
        position += 2 + length
    raise bad_args("the JPEG file has no frame header in its first megabyte")


def webp_dimensions(data):
    kind = data[12:16]
    if kind == b"VP8 " and len(data) >= 30:
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if kind == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8X" and len(data) >= 30:
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    raise bad_args("the WebP file has no image header")


def exr_dimensions(data):
    position = 8
    while position < len(data):
        if data[position] == 0:
            break
        name_end = data.index(b"\x00", position)
        kind_end = data.index(b"\x00", name_end + 1)
        name = data[position:name_end]
        size = struct.unpack("<i", data[kind_end + 1 : kind_end + 5])[0]
        value = data[kind_end + 5 : kind_end + 5 + size]
        if name == b"dataWindow" and len(value) == 16:
            x_min, y_min, x_max, y_max = struct.unpack("<iiii", value)
            return x_max - x_min + 1, y_max - y_min + 1
        position = kind_end + 5 + size
    raise bad_args("the OpenEXR file has no data window")
