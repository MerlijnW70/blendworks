from . import baking, limits
from .errors import bad_args
from .schema import EXISTS, array, integer, names, obj, ref

BYTES_PER_TEXEL = 4
MAX_RULES = limits.MAX_ATLAS_RULES


def gpu_bytes(width, height):
    total = 0
    while True:
        total += width * height
        if width == 1 and height == 1:
            return BYTES_PER_TEXEL * total
        width, height = max(1, width // 2), max(1, height // 2)


def size_rules_schema():
    rule = obj(
        {
            "size": integer("Image width and height in pixels for the matching images.", limits.LEAST_BAKE_SIZE, limits.MAX_BAKE_SIZE),
            "materials": ref(names("Materials the rule covers. Naming materials gives each material its own images, called prefix_material_channel."), "material", EXISTS),
            "channels": array({"type": "string", "enum": list(baking.CHANNELS)}, "Channels the rule covers.", 1, limits.MAX_BAKE_CHANNELS),
        },
        ["size"],
    )
    return array(rule, "Image sizes for some materials or channels; the last matching rule wins and everything else uses size.", 1, MAX_RULES)


def check_rules(rules, materials, channels):
    known = {material.name for material in materials}
    for position, rule in enumerate(rules):
        if "materials" not in rule and "channels" not in rule:
            raise bad_args(f"atlas_sizes[{position}] names no materials or channels; use size for the default")
        missing = [name for name in rule.get("materials", ()) if name not in known]
        if missing:
            raise bad_args(f"atlas_sizes[{position}] names {missing[0]}, which none of the baked objects uses")
        stray = [name for name in rule.get("channels", ()) if name not in channels]
        if stray:
            raise bad_args(f"atlas_sizes[{position}] names {stray[0]}, which is not baked")


def per_material(rules):
    return any("materials" in rule for rule in rules)


def size_for(rules, default, material, channel):
    chosen = default
    for rule in rules:
        if "materials" in rule and material not in rule["materials"]:
            continue
        if "channels" in rule and channel not in rule["channels"]:
            continue
        chosen = rule["size"]
    return chosen
