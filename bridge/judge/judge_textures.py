import os

KINDS = ("baseColor", "metallicRoughness", "normal", "emissive", "occlusion")
COLOUR_KINDS = ("baseColor", "emissive")
COLOUR_SPACE = "sRGB"
DATA_SPACE = "Non-Color"
PRINCIPLED_INPUTS = (
    ("Base Color", "baseColor"),
    ("Metallic", "metallicRoughness"),
    ("Roughness", "metallicRoughness"),
    ("Normal", "normal"),
    ("Emission Color", "emissive"),
)
GLTF_OUTPUT_GROUPS = ("glTF Material Output", "glTF Settings")
OCCLUSION_INPUT = "Occlusion"
NO_MATERIAL = "(no material)"
MAX_LISTED = 256
MAX_NAMES = 64
NAME_LENGTH = 120


def expected_space(kind):
    return COLOUR_SPACE if kind in COLOUR_KINDS else DATA_SPACE


def mip_chain_pixels(width, height):
    if width <= 0 or height <= 0:
        return 0
    total = 0
    while True:
        total += width * height
        if width == 1 and height == 1:
            return total
        width = max(1, width // 2)
        height = max(1, height // 2)


def gpu_bytes(width, height):
    return 4 * mip_chain_pixels(width, height)


def is_power_of_two(value):
    return value > 0 and value & (value - 1) == 0


def group_output(tree):
    outputs = [node for node in tree.nodes if node.type == "GROUP_OUTPUT"]
    active = [node for node in outputs if node.is_active_output]
    return (active or outputs or [None])[0]


def socket_by_identifier(sockets, identifier):
    return next((socket for socket in sockets if socket.identifier == identifier), None)


def upstream(socket, groups, stop_types):
    found = []
    stack = [(socket, groups)]
    visited = set()
    while stack:
        current, context = stack.pop()
        for link in current.links:
            if link.is_muted or not link.is_valid:
                continue
            node = link.from_node
            key = (node.as_pointer(), link.from_socket.identifier, tuple(group.as_pointer() for group in context))
            if key in visited:
                continue
            visited.add(key)
            stack.extend(next_sockets(node, link.from_socket, context, stop_types, found))
    return found


def next_sockets(node, from_socket, context, stop_types, found):
    if node.mute:
        return [(internal.from_socket, context) for internal in node.internal_links if internal.to_socket == from_socket]
    if node.type in stop_types:
        found.append((node, context))
        return []
    if node.type == "GROUP":
        output = group_output(node.node_tree) if node.node_tree is not None else None
        inner = socket_by_identifier(output.inputs, from_socket.identifier) if output is not None else None
        return [(inner, context + (node,))] if inner is not None else []
    if node.type == "GROUP_INPUT":
        if not context:
            return []
        outer = socket_by_identifier(context[-1].inputs, from_socket.identifier)
        return [(outer, context[:-1])] if outer is not None else []
    return [(socket, context) for socket in node.inputs]


def material_maps(material):
    tree = material.node_tree if material is not None else None
    if tree is None:
        return {}
    maps = {}

    def collect(socket, groups, kind):
        for node, _ in upstream(socket, groups, {"TEX_IMAGE"}):
            if node.image is not None:
                maps.setdefault(kind, set()).add(node.image)

    output = tree.get_output_node("CYCLES")
    if output is not None:
        surface = output.inputs.get("Surface")
        for shader, groups in upstream(surface, (), {"BSDF_PRINCIPLED"}) if surface is not None else []:
            for name, kind in PRINCIPLED_INPUTS:
                socket = shader.inputs.get(name)
                if socket is not None:
                    collect(socket, groups, kind)
    for node in tree.nodes:
        if node.type == "GROUP" and node.node_tree is not None and node.node_tree.name.split(".")[0] in GLTF_OUTPUT_GROUPS:
            socket = node.inputs.get(OCCLUSION_INPUT)
            if socket is not None:
                collect(socket, (), "occlusion")
    return maps


def image_source(image):
    if image.packed_file is not None:
        return "packed"
    if image.source == "GENERATED":
        return "generated"
    return "file"


def image_record(image, kinds, materials):
    width, height = (int(value) for value in image.size[:])
    source = image_source(image)
    embedded = source != "file"
    return {
        "name": image.name[:NAME_LENGTH],
        "kinds": sorted(kinds, key=KINDS.index),
        "materials": sorted(materials)[:MAX_NAMES],
        "width": width,
        "height": height,
        "colourSpace": image.colorspace_settings.name[:64],
        "embedded": embedded,
        "source": source,
        "file": None if embedded else os.path.basename(image.filepath)[:NAME_LENGTH],
        "gpuBytes": gpu_bytes(width, height),
        "powerOfTwo": is_power_of_two(width) and is_power_of_two(height),
    }


def limited(names):
    ordered = sorted(names)
    return {"count": len(ordered), "names": ordered[:MAX_NAMES]}


def measure_textures(materials, faces_without_material, refused_files):
    usage = {}
    material_records = []
    missing = {kind: set() for kind in KINDS}
    for name in sorted(materials):
        maps = material_maps(materials[name])
        material_records.append({"name": name[:NAME_LENGTH], "maps": [kind for kind in KINDS if kind in maps]})
        for kind in KINDS:
            if kind not in maps:
                missing[kind].add(name[:NAME_LENGTH])
            for image in maps.get(kind, ()):
                entry = usage.setdefault(image.as_pointer(), {"image": image, "kinds": set(), "materials": set()})
                entry["kinds"].add(kind)
                entry["materials"].add(name[:NAME_LENGTH])
    if faces_without_material:
        for kind in KINDS:
            missing[kind].add(NO_MATERIAL)
    images = sorted(
        (image_record(entry["image"], entry["kinds"], entry["materials"]) for entry in usage.values()),
        key=lambda record: (record["name"], record["width"], record["height"]),
    )
    mismatches = [
        {"image": record["name"], "kind": kind, "colourSpace": record["colourSpace"], "expected": expected_space(kind)}
        for record in images
        for kind in record["kinds"]
        if record["colourSpace"] != expected_space(kind)
    ]
    refused_images = [f"{name.split(':', 1)[1]} (refused)" for name in refused_files if name.startswith("images:")]
    external = [f"{record['name']} ({record['file']})" for record in images if not record["embedded"]] + refused_images
    shorter = [min(record["width"], record["height"]) for record in images]
    longer = [max(record["width"], record["height"]) for record in images]
    return {
        "count": len(images),
        "gpuBytes": sum(record["gpuBytes"] for record in images),
        "smallestSide": min(shorter) if images else None,
        "largestSide": max(longer) if images else None,
        "images": images[:MAX_LISTED],
        "materials": material_records[:MAX_LISTED],
        "facesWithoutMaterial": faces_without_material,
        "missing": {kind: limited(missing[kind]) for kind in KINDS},
        "external": limited(external),
        "nonPowerOfTwo": limited(f"{record['name']} {record['width']}x{record['height']}" for record in images if not record["powerOfTwo"]),
        "colourSpaceMismatches": {"count": len(mismatches), "items": mismatches[:MAX_NAMES]},
    }
