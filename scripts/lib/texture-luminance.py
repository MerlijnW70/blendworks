import json
import os
import struct
import sys
import zlib

import bpy
import numpy as np

LARGEST = 512
LUMINANCE = (0.2126, 0.7152, 0.0722)
SIGNATURE = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


def arguments():
    rest = sys.argv[sys.argv.index("--") + 1 :]
    return rest[0], rest[1]


def gltf_document(path):
    with open(path, "rb") as handle:
        data = handle.read()
    if path.lower().endswith(".glb"):
        length = struct.unpack_from("<I", data, 12)[0]
        return json.loads(data[20 : 20 + length].decode("utf-8"))
    return json.loads(data.decode("utf-8"))


def identity_transform(texture):
    transform = texture.get("extensions", {}).get("KHR_texture_transform")
    if transform is None:
        return True
    return transform.get("offset", [0, 0]) == [0, 0] and transform.get("rotation", 0) == 0 and transform.get("scale", [1, 1]) == [1, 1]


def base_colour_images(document):
    found = []
    for material in document.get("materials", []):
        pbr = material.get("pbrMetallicRoughness", {})
        texture = pbr.get("baseColorTexture")
        if texture is None:
            continue
        source = document["textures"][texture["index"]].get("source")
        factor = tuple(pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])[:3])
        entry = (source, factor, identity_transform(texture))
        if source is not None and entry not in found:
            found.append(entry)
    return [(document["images"][source], factor, identity) for source, factor, identity in found]


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def grey_png(path, grey):
    height, width = grey.shape
    rows = np.flipud(np.clip(np.round(grey * 255.0), 0, 255).astype(np.uint8))
    rgba = np.stack([rows, rows, rows, np.full((height, width), 255, dtype=np.uint8)], axis=2)
    raw = b"".join(bytes(1) + line.tobytes() for line in rgba)
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def main():
    asset, out = arguments()
    os.makedirs(out, exist_ok=True)
    written = []
    for index, (entry, factor, identity) in enumerate(base_colour_images(gltf_document(asset))):
        uri = entry.get("uri")
        if uri is None or not identity:
            written.append({"image": os.path.basename(uri or ""), "file": None, "size": None, "skipped": "embedded image" if uri is None else "KHR_texture_transform is not the identity"})
            continue
        image = bpy.data.images.load(os.path.join(os.path.dirname(asset), uri))
        image.colorspace_settings.name = "Non-Color"
        width, height = image.size
        scale = min(1.0, LARGEST / max(width, height))
        if scale < 1.0:
            image.scale(max(1, round(width * scale)), max(1, round(height * scale)))
            width, height = image.size
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        rgba = pixels.reshape(height, width, 4)
        grey = sum(rgba[:, :, channel] * factor[channel] * LUMINANCE[channel] for channel in range(3))
        name = f"texture-{index}.png"
        grey_png(os.path.join(out, name), grey)
        written.append({"image": os.path.basename(uri), "file": name, "size": [width, height]})
    with open(os.path.join(out, "textures.json"), "w", encoding="utf-8") as handle:
        json.dump(written, handle)


main()
