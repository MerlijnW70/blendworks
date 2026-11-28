"""Minimal OpenEXR header and part reader."""

import mmap
import struct
import zlib

import numpy as np

MAGIC = b"\x76\x2f\x31\x01"
MULTIPART = 0x1000
TILED = 0x200
COMPRESSION_NONE = 0
COMPRESSION_ZIPS = 2
COMPRESSION_ZIP = 3
LINES_PER_CHUNK = {COMPRESSION_NONE: 1, COMPRESSION_ZIPS: 1, COMPRESSION_ZIP: 16}
PIXEL_TYPES = {0: (np.dtype("<u4"), 4), 1: (np.dtype("<f2"), 2), 2: (np.dtype("<f4"), 4)}


class ExrError(ValueError):
    pass


class Part:
    def __init__(self, attributes):
        self.attributes = attributes
        self.name = string_attribute(attributes, "name")
        self.channels = channel_list(attributes["channels"][1])
        self.compression = attributes["compression"][1][0]
        low_x, low_y, high_x, high_y = struct.unpack("<4i", attributes["dataWindow"][1])
        self.origin_y = low_y
        self.width = high_x - low_x + 1
        self.height = high_y - low_y + 1
        if self.compression not in LINES_PER_CHUNK:
            raise ExrError(f"EXR compression {self.compression} is not supported (none, zips and zip are)")
        if self.width <= 0 or self.height <= 0:
            raise ExrError("the EXR data window is empty")
        self.lines = LINES_PER_CHUNK[self.compression]
        self.chunks = (self.height + self.lines - 1) // self.lines


def string_attribute(attributes, name):
    entry = attributes.get(name)
    return entry[1].decode("utf-8", "replace") if entry is not None else ""


def channel_list(raw):
    channels = []
    position = 0
    while position < len(raw) and raw[position] != 0:
        end = raw.index(b"\0", position)
        name = raw[position:end].decode("utf-8", "replace")
        pixel_type, _linear, x_sampling, y_sampling = struct.unpack("<iBxxxii", raw[end + 1 : end + 17])
        if pixel_type not in PIXEL_TYPES:
            raise ExrError(f"EXR channel {name} has unknown pixel type {pixel_type}")
        if (x_sampling, y_sampling) != (1, 1):
            raise ExrError(f"EXR channel {name} is subsampled")
        channels.append((name, pixel_type))
        position = end + 17
    return sorted(channels)


def terminator(data, position):
    end = data.find(bytes(1), position)
    if end < 0:
        raise ExrError("the EXR header is cut short")
    return end


def read_attributes(data, position):
    attributes = {}
    while True:
        end = terminator(data, position)
        name = data[position:end].decode("utf-8", "replace")
        position = end + 1
        if not name:
            return attributes, position
        end = terminator(data, position)
        kind = data[position:end].decode("utf-8", "replace")
        size = struct.unpack("<i", data[end + 1 : end + 5])[0]
        start = end + 5
        attributes[name] = (kind, bytes(data[start : start + size]))
        position = start + size


def read_parts(data):
    if data[:4] != MAGIC:
        raise ExrError("not an OpenEXR file")
    flags = struct.unpack("<I", data[4:8])[0]
    if flags & TILED:
        raise ExrError("tiled EXR files are not supported")
    position = 8
    parts = []
    if flags & MULTIPART:
        while data[position] != 0:
            attributes, position = read_attributes(data, position)
            parts.append(Part(attributes))
        position += 1
    else:
        attributes, position = read_attributes(data, position)
        parts.append(Part(attributes))
    return parts, position, bool(flags & MULTIPART)


def undo_zip(raw, expected):
    data = np.frombuffer(zlib.decompress(raw), dtype=np.uint8)
    if data.size != expected:
        raise ExrError("an EXR chunk has the wrong size")
    data = ((np.cumsum(data.astype(np.int64) - 128) + 128) % 256).astype(np.uint8)
    half = (data.size + 1) // 2
    out = np.empty(data.size, dtype=np.uint8)
    out[0::2] = data[:half]
    out[1::2] = data[half:]
    return out


def chunk_bytes(part, raw, lines):
    expected = sum(PIXEL_TYPES[kind][1] for _name, kind in part.channels) * part.width * lines
    if part.compression == COMPRESSION_NONE or len(raw) == expected:
        if len(raw) != expected:
            raise ExrError("an EXR chunk has the wrong size")
        return np.frombuffer(raw, dtype=np.uint8)
    return undo_zip(raw, expected)


def decode_part(data, part, offsets, multipart, index, wanted):
    planes = {name: np.zeros((part.height, part.width), dtype=np.float32) for name, _kind in part.channels if wanted(name)}
    for offset in offsets:
        position = offset
        if multipart:
            owner = struct.unpack("<i", data[position : position + 4])[0]
            if owner != index:
                raise ExrError("an EXR chunk belongs to another part")
            position += 4
        y, size = struct.unpack("<ii", data[position : position + 8])
        row = y - part.origin_y
        lines = min(part.lines, part.height - row)
        if row < 0 or lines <= 0:
            raise ExrError("an EXR chunk lies outside the data window")
        block = chunk_bytes(part, data[position + 8 : position + 8 + size], lines)
        cursor = 0
        for line in range(lines):
            for name, kind in part.channels:
                dtype, width = PIXEL_TYPES[kind]
                count = part.width * width
                if name in planes:
                    planes[name][row + line] = block[cursor : cursor + count].view(dtype)
                cursor += count
    return planes


def mapped(path):
    handle = open(path, "rb")
    try:
        return mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    except ValueError as error:
        raise ExrError("the EXR file is empty") from error
    finally:
        handle.close()


def read_exr(path, wanted=None):
    """Read the channels that wanted(name) accepts (all by default) as float32 planes; the file is mapped, not read whole."""
    accept = wanted if wanted is not None else (lambda _name: True)
    with mapped(path) as data:
        parts, position, multipart = read_parts(data)
        layers = {}
        metadata = {}
        for index, part in enumerate(parts):
            offsets = struct.unpack(f"<{part.chunks}Q", data[position : position + 8 * part.chunks])
            position += 8 * part.chunks
            layers.update(decode_part(data, part, offsets, multipart, index, accept))
            metadata.update(string_attributes(part))
    return Image(layers, metadata)


class Image:
    def __init__(self, channels, metadata):
        self.channels = channels
        self.metadata = metadata

    def has(self, name):
        return name in self.channels

    def channel(self, name):
        if name not in self.channels:
            raise ExrError(f"the EXR has no channel {name}")
        return self.channels[name]

    def stack(self, prefix, suffixes):
        return np.stack([self.channel(f"{prefix}.{suffix}" if prefix else suffix) for suffix in suffixes], axis=-1)

    def layer_names(self):
        return sorted({name.rsplit(".", 1)[0] for name in self.channels if "." in name})


def read_metadata(path):
    """The string attributes of every part; only the header is touched."""
    with mapped(path) as data:
        parts = read_parts(data)[0]
    metadata = {}
    for part in parts:
        metadata.update(string_attributes(part))
    return metadata


def string_attributes(part):
    return {name: value.decode("utf-8", "replace") for name, (kind, value) in part.attributes.items() if kind == "string"}
