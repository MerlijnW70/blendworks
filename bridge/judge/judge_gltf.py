import base64
import os
import struct

from judge_common import JudgeError, quoted
from judge_paths import check_reference

GLB_BINARY_CHUNK = 0x004E4942
MAX_IMAGE_SIDE = 16384
MAX_IMAGE_PIXELS = 256 * 1024 * 1024
HEADER_BYTES = 1 << 20
REFUSED_EXTENSIONS = {"EXT_meshopt_compression": "Blender's glTF importer cannot decode meshopt compression"}
TRIANGLE_MODES = {4: lambda count: count // 3, 5: lambda count: max(0, count - 2), 6: lambda count: max(0, count - 2)}


def entries(document, key):
    value = document.get(key) or []
    if not isinstance(value, list):
        raise JudgeError("corrupt", f"the glTF {key} entry is not a list")
    return value


def whole(value, minimum=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def accessor_count(accessors, index):
    if not whole(index) or index >= len(accessors) or not isinstance(accessors[index], dict) or not whole(accessors[index].get("count")):
        raise JudgeError("corrupt", f"the glTF refers to a missing or malformed accessor {index}")
    return accessors[index]["count"]


def mesh_triangles(document):
    accessors = entries(document, "accessors")
    totals = []
    for mesh in entries(document, "meshes"):
        total = 0
        for primitive in (mesh.get("primitives") or []) if isinstance(mesh, dict) else []:
            if not isinstance(primitive, dict):
                continue
            mode = primitive.get("mode", 4)
            if mode not in TRIANGLE_MODES:
                continue
            if "indices" in primitive:
                count = accessor_count(accessors, primitive["indices"])
            else:
                attributes = primitive.get("attributes") or {}
                count = accessor_count(accessors, attributes.get("POSITION")) if isinstance(attributes, dict) and "POSITION" in attributes else 0
            total += TRIANGLE_MODES[mode](count)
        totals.append(total)
    return totals


def node_placements(document):
    nodes = entries(document, "nodes")
    parents = {index: [] for index in range(len(nodes))}
    for index, node in enumerate(nodes):
        for child in (node.get("children") or []) if isinstance(node, dict) else []:
            if not whole(child) or child >= len(nodes):
                raise JudgeError("corrupt", f"the glTF node {index} has a missing child {child}")
            parents[child].append(index)
    roots = set()
    for scene in entries(document, "scenes"):
        for root in (scene.get("nodes") or []) if isinstance(scene, dict) else []:
            if whole(root) and root < len(nodes):
                roots.add(root)
    placements = {}
    visiting = set()

    def placed(index):
        if index in placements:
            return placements[index]
        if index in visiting:
            raise JudgeError("corrupt", f"the glTF node hierarchy has a cycle through node {index}")
        visiting.add(index)
        own = 1 if index in roots or not parents[index] else 0
        placements[index] = own + sum(placed(parent) for parent in parents[index])
        visiting.discard(index)
        return placements[index]

    for index in range(len(nodes)):
        placed(index)
    return nodes, placements


def instance_count(node, accessors):
    extension = ((node.get("extensions") or {}).get("EXT_mesh_gpu_instancing") or {}) if isinstance(node, dict) else {}
    attributes = extension.get("attributes") or {}
    if not isinstance(attributes, dict) or not attributes:
        return 1
    return max(accessor_count(accessors, index) for index in attributes.values())


def declared_triangles(document):
    meshes = mesh_triangles(document)
    accessors = entries(document, "accessors")
    nodes, placements = node_placements(document)
    total = 0
    for index, node in enumerate(nodes):
        mesh = node.get("mesh") if isinstance(node, dict) else None
        if mesh is None:
            continue
        if not whole(mesh) or mesh >= len(meshes):
            raise JudgeError("corrupt", f"the glTF node {index} refers to a missing mesh {mesh}")
        total += meshes[mesh] * placements[index] * instance_count(node, accessors)
    return total


def image_size(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        return jpeg_size(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return webp_size(data)
    if data[:12] == b"\xabKTX 20\xbb\r\n\x1a\n" and len(data) >= 28:
        return struct.unpack("<II", data[20:28])
    return None


def jpeg_size(data):
    position = 2
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            return None
        marker = data[position + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            position += 2
            continue
        length = struct.unpack(">H", data[position + 2 : position + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC) and position + 9 <= len(data):
            height, width = struct.unpack(">HH", data[position + 5 : position + 9])
            return width, height
        position += 2 + length
    return None


def webp_size(data):
    kind = data[12:16]
    if kind == b"VP8X" and len(data) >= 30:
        return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
    if kind == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
    if kind == b"VP8 " and len(data) >= 30:
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    return None


class Buffers:
    def __init__(self, document, directory, binary):
        self.document = document
        self.directory = directory
        self.binary = binary

    def read(self, buffer_index, offset, length):
        buffers = entries(self.document, "buffers")
        if not whole(buffer_index) or buffer_index >= len(buffers) or not isinstance(buffers[buffer_index], dict):
            raise JudgeError("corrupt", f"the glTF refers to a missing buffer {buffer_index}")
        uri = buffers[buffer_index].get("uri")
        if uri is None:
            return (self.binary or b"")[offset : offset + length]
        return read_uri(uri, self.directory, offset, length)


def read_uri(uri, directory, offset, length):
    if not isinstance(uri, str):
        raise JudgeError("corrupt", "the glTF has a URI that is not text")
    if uri.startswith("data:"):
        _, _, payload = uri.partition(",")
        encoded = payload[: ((offset + length) * 4 // 3 + 8) // 4 * 4]
        try:
            return base64.b64decode(encoded + "=" * (-len(encoded) % 4))[offset : offset + length]
        except ValueError:
            raise JudgeError("corrupt", "the glTF has a malformed data URI") from None
    relative, problem = check_reference(uri, "uri")
    if problem is not None:
        raise JudgeError("external_reference", f"the glTF refers to a file the judge never opens: {quoted(uri)}: {problem[1]}")
    with open(os.path.join(directory, *relative.split("/")), "rb") as handle:
        handle.seek(offset)
        return handle.read(length)


def image_header(image, buffers):
    views = entries(buffers.document, "bufferViews")
    if "bufferView" in image:
        index = image["bufferView"]
        if not whole(index) or index >= len(views) or not isinstance(views[index], dict):
            raise JudgeError("corrupt", f"the glTF image refers to a missing bufferView {index}")
        view = views[index]
        start = view.get("byteOffset", 0)
        length = min(view.get("byteLength", 0), HEADER_BYTES)
        return buffers.read(view.get("buffer"), start if whole(start) else 0, length if whole(length) else 0)
    if "uri" in image:
        return read_uri(image["uri"], buffers.directory, 0, HEADER_BYTES)
    return b""


def check_images(document, buffers):
    total = 0
    for index, image in enumerate(entries(document, "images")):
        if not isinstance(image, dict):
            continue
        size = image_size(image_header(image, buffers))
        if size is None:
            continue
        width, height = size
        if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
            raise JudgeError("image_too_large", f"glTF image {index} is {width} x {height} pixels, over the judge's limit of {MAX_IMAGE_SIDE} per side")
        total += width * height
        if total > MAX_IMAGE_PIXELS:
            raise JudgeError("image_too_large", f"the glTF images hold more than {MAX_IMAGE_PIXELS} pixels together, the judge's limit")
    return total


def precheck_gltf(document, directory, binary, triangle_cap):
    required = document.get("extensionsRequired") or []
    for name in required if isinstance(required, list) else []:
        if name in REFUSED_EXTENSIONS:
            raise JudgeError("unsupported_extension", f"the glTF requires {name}: {REFUSED_EXTENSIONS[name]}")
    triangles = declared_triangles(document)
    if triangles > triangle_cap:
        raise JudgeError("too_many_triangles", f"the glTF declares {triangles} triangles in its accessors, over the judge's cap of {triangle_cap}; refused before import")
    return {"triangles": triangles, "pixels": check_images(document, Buffers(document, directory, binary))}


def glb_binary(data):
    position = 12
    while position + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, position)
        if kind == GLB_BINARY_CHUNK:
            return data[position + 8 : position + 8 + length]
        position += 8 + length + (-length % 4)
    return None
