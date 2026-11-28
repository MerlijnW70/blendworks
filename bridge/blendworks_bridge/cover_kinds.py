"""Ground cover element kinds: parameters, budgets, geometry and materials."""

import bpy
import numpy

from . import leaf_optics
from .cover_blades import blade_cards, blade_clump
from .cover_flowers import flower_cards, flower_geometry
from .cover_litter import leaf_cards, leaf_geometry, pebble_cards, pebble_geometry, twig_cards, twig_geometry
from .cover_shading import preset_material
from .errors import bad_args
from .limits import (FRACTION, HALF_TURN, LEAST_PETALS, MAX_BASE_LEAVES, MAX_CLUMP_BLADES, MAX_ELEMENT_TRIANGLES as ELEMENT_TRIANGLES,
                     MAX_LEAF_ASPECT, MAX_LENGTH, MAX_PEBBLE_ELONGATION, MAX_PEBBLE_FLATNESS, MAX_PETALS, MAX_SIDE_SHOOTS, QUARTER_TURN,
                     SHORTEST_LEAF, SMALLEST_ASPECT_RATIO, SMALLEST_BLADE_WIDTH, SMALLEST_ELEMENT_SIZE,
                     SMALLEST_PLANT_PART)
from .schema import array, color, integer, number, obj

KINDS = ("grass", "tuft", "sedge", "flower", "twig", "leaf", "pebble", "mound")
FORMS = ("geometry", "cards")
BLADE_KINDS = ("grass", "tuft", "sedge")
LITTER_KINDS = ("twig", "leaf", "pebble", "mound")
MAX_ELEMENT_TRIANGLES = ELEMENT_TRIANGLES
CARD_BLADE_SHARE = 0.45
BLADE_BUMP = 0.6
TIP_GAIN = (2.1, 1.65, 1.0)


def pair(description, low, high):
    return array({"type": "number", "minimum": low, "maximum": high}, description, 2, 2)


ELEMENT_FIELDS = {
    "blades": integer("grass, tuft, sedge: blades in one clump.", 1, MAX_CLUMP_BLADES),
    "height": pair("grass, tuft, sedge, flower: shortest and tallest height in metres.", SMALLEST_ELEMENT_SIZE, MAX_LENGTH),
    "width": number("grass, tuft, sedge: blade width at the root in metres.", SMALLEST_BLADE_WIDTH, MAX_LENGTH),
    "taper": number("grass, tuft, sedge: how much the width shrinks towards the tip, 0 to 1.", 0.0, FRACTION),
    "curvature": number("grass, tuft, sedge: extra bend at the tip in quarter turns, 0 straight to 1 arching over.", 0.0, FRACTION),
    "lean": number("grass, tuft, sedge: largest outward lean of a blade from vertical in degrees.", 0.0, QUARTER_TURN),
    "spread": number("grass, tuft, sedge: radius of the clump base in metres.", 0.0, MAX_LENGTH),
    "twist": number("grass, tuft, sedge: largest twist of a blade from root to tip in degrees.", 0.0, HALF_TURN),
    "fold": number("grass, tuft, sedge: V fold along the midrib as a share of the half width (sedges are folded).", 0.0, FRACTION),
    "dry_tips": number("grass, tuft, sedge: share of blades with a dry tip, 0 to 1.", 0.0, FRACTION),
    "dry_length": pair("grass, tuft, sedge: shortest and longest dry tip as a share of the blade.", 0.0, FRACTION),
    "seed_heads": number("grass, tuft, sedge: share of the blades that are flowering stems with a seed head, taller, narrow and dry towards the top; geometry only.", 0.0, FRACTION),
    "petals": integer("flower: petals, placed at the golden angle.", LEAST_PETALS, MAX_PETALS),
    "petal_length": number("flower: petal length in metres.", SMALLEST_ELEMENT_SIZE, MAX_LENGTH),
    "petal_width": number("flower: petal width in metres.", SMALLEST_PLANT_PART, MAX_LENGTH),
    "centre_radius": number("flower: radius of the disc in the middle in metres.", SMALLEST_PLANT_PART, MAX_LENGTH),
    "cup": number("flower: how far the petals rise from the disc plane in degrees.", -QUARTER_TURN, QUARTER_TURN),
    "head_tilt": number("flower: largest tilt of the head from the stem direction in degrees.", 0.0, QUARTER_TURN),
    "stem_width": number("flower: stem diameter in metres.", SMALLEST_PLANT_PART, MAX_LENGTH),
    "leaves": integer("flower: leaves at the base.", 0, MAX_BASE_LEAVES),
    "leaf_width": number("flower: base leaf width in metres.", SMALLEST_PLANT_PART, MAX_LENGTH),
    "length": pair("twig, leaf: shortest and longest length in metres.", SHORTEST_LEAF, MAX_LENGTH),
    "thickness": number("twig: radius of the main twig in metres.", SMALLEST_PLANT_PART, MAX_LENGTH),
    "branches": integer("twig: most side shoots.", 0, MAX_SIDE_SHOOTS),
    "aspect": number("leaf: width over length.", SMALLEST_ASPECT_RATIO, MAX_LEAF_ASPECT),
    "curl": number("leaf: how far the edges curl up, 0 to 1.", 0.0, FRACTION),
    "arch": number("leaf: how far the midrib arches, 0 to 1.", 0.0, FRACTION),
    "size": pair("pebble, mound: smallest and largest radius in metres.", SMALLEST_ELEMENT_SIZE, MAX_LENGTH),
    "flatness": number("pebble, mound: how flat, 0 round to 0.9 flat.", 0.0, MAX_PEBBLE_FLATNESS),
    "elongation": number("pebble, mound: how long, 0 round to 2.", 0.0, MAX_PEBBLE_ELONGATION),
    "roughness": number("pebble, mound: lumpiness of the outline, 0 to 1.", 0.0, FRACTION),
    "color": color("Main colour, linear RGB: the blade body, the twig bark, the leaf, the pebble or the soil of a mound.", None, False),
    "dry_color": color("grass, tuft, sedge: colour of the dry tips, linear RGB.", None, False),
    "petal_color": color("flower: petal colour, linear RGB.", None, False),
    "centre_color": color("flower: disc colour, linear RGB.", None, False),
}
ELEMENT = obj(ELEMENT_FIELDS)

BLADE_FIELDS = ("blades", "height", "width", "taper", "curvature", "lean", "spread", "twist", "fold", "dry_tips", "dry_length", "seed_heads", "color", "dry_color")
KIND_FIELDS = {
    "grass": BLADE_FIELDS,
    "tuft": BLADE_FIELDS,
    "sedge": BLADE_FIELDS,
    "flower": ("height", "petals", "petal_length", "petal_width", "centre_radius", "cup", "head_tilt", "stem_width", "leaves", "leaf_width", "color", "petal_color", "centre_color"),
    "twig": ("length", "thickness", "branches", "color"),
    "leaf": ("length", "aspect", "curl", "arch", "color"),
    "pebble": ("size", "flatness", "elongation", "roughness", "color"),
    "mound": ("size", "flatness", "elongation", "roughness", "color"),
}
GRASS_LEAF = list(leaf_optics.OPTICS["grass"]["reflectance"])
KIND_DEFAULTS = {
    "grass": {"seed_heads": 0.0, "blades": 24, "height": [0.25, 0.5], "width": 0.004, "taper": 0.92, "curvature": 0.55, "lean": 22.0, "spread": 0.05, "twist": 40.0, "fold": 0.0, "dry_tips": 0.2, "dry_length": [0.15, 0.4], "color": GRASS_LEAF, "dry_color": [0.36, 0.28, 0.12]},
    "tuft": {"seed_heads": 0.0, "blades": 40, "height": [0.06, 0.16], "width": 0.003, "taper": 0.9, "curvature": 0.6, "lean": 40.0, "spread": 0.02, "twist": 60.0, "fold": 0.0, "dry_tips": 0.15, "dry_length": [0.1, 0.3], "color": GRASS_LEAF, "dry_color": [0.36, 0.28, 0.12]},
    "sedge": {"seed_heads": 0.0, "blades": 14, "height": [0.3, 0.6], "width": 0.008, "taper": 0.95, "curvature": 0.2, "lean": 14.0, "spread": 0.03, "twist": 15.0, "fold": 0.45, "dry_tips": 0.35, "dry_length": [0.1, 0.35], "color": GRASS_LEAF, "dry_color": [0.33, 0.27, 0.14]},
    "flower": {"height": [0.2, 0.45], "petals": 13, "petal_length": 0.012, "petal_width": 0.006, "centre_radius": 0.005, "cup": 20.0, "head_tilt": 45.0, "stem_width": 0.0025, "leaves": 3, "leaf_width": 0.006, "color": [0.06, 0.14, 0.03], "petal_color": [0.82, 0.82, 0.76], "centre_color": [0.62, 0.4, 0.02]},
    "twig": {"length": [0.08, 0.3], "thickness": 0.003, "branches": 2, "color": [0.12, 0.085, 0.055]},
    "leaf": {"length": [0.04, 0.09], "aspect": 0.6, "curl": 0.6, "arch": 0.5, "color": [0.2, 0.1, 0.035]},
    "pebble": {"size": [0.008, 0.03], "flatness": 0.4, "elongation": 0.4, "roughness": 0.5, "color": [0.3, 0.28, 0.25]},
    "mound": {"size": [0.15, 0.3], "flatness": 0.6, "elongation": 0.3, "roughness": 0.7, "color": [0.085, 0.058, 0.038]},
}
DEFAULT_TRIANGLES = {"grass": 400, "tuft": 400, "sedge": 300, "flower": 300, "twig": 200, "leaf": 48, "pebble": 320, "mound": 320}
CARD_TRIANGLES = {"grass": 12, "tuft": 12, "sedge": 12, "flower": 32, "twig": 6, "leaf": 2, "pebble": 2, "mound": 2}
MIN_TRIANGLES = {"geometry": {"flower": 14, "twig": 12, "leaf": 8, "pebble": 20, "mound": 20}, "cards": {"flower": 12}}


def element_params(kind, given):
    stray = sorted(set(given) - set(KIND_FIELDS[kind]))
    if stray:
        raise bad_args(f"{', '.join(stray)} does not apply to a {kind}; it takes {', '.join(KIND_FIELDS[kind])}")
    params = dict(KIND_DEFAULTS[kind], **given)
    for key in ("height", "dry_length", "length", "size"):
        if key in params and params[key][0] > params[key][1]:
            raise bad_args(f"{key} must be [smallest, largest]")
    return params


def element_budget(kind, form, triangles):
    defaults = DEFAULT_TRIANGLES if form == "geometry" else CARD_TRIANGLES
    budget = defaults[kind] if triangles is None else triangles
    smallest = MIN_TRIANGLES[form].get(kind, 1 if form == "geometry" else 2)
    if budget < smallest:
        raise bad_args(f"a {kind} as {form} needs a triangle budget of at least {smallest}")
    return budget


def build_geometry(kind, form, params, rng, budget):
    if kind in BLADE_KINDS:
        return blade_clump(params, rng, budget) if form == "geometry" else blade_cards(params, rng, budget)
    builders = {
        "flower": (flower_geometry, flower_cards),
        "twig": (twig_geometry, twig_cards),
        "leaf": (leaf_geometry, leaf_cards),
        "pebble": (pebble_geometry, pebble_cards),
        "mound": (pebble_geometry, pebble_cards),
    }[kind]
    return builders[0 if form == "geometry" else 1](params, rng, budget)


def scaled(values, factor):
    return [min(1.0, value * factor) for value in values[:3]]


def blade_material(params, form, report):
    overrides = {"color": params["color"], "root_color": scaled(params["color"], 0.45), "tip_color": [min(1.0, value * gain) for value, gain in zip(params["color"][:3], TIP_GAIN)], "dry_color": params["dry_color"], "variation": 0.7, "card": form == "cards", "dry_tips": params["dry_tips"], "bump": 0.0 if form == "cards" else BLADE_BUMP}
    if form == "cards":
        columns = int(min(32, max(4, round(params["blades"] / 2))))
        column_width = report["card_width"] / columns
        overrides.update({"card_blades": columns, "card_height_min": params["height"][0] / params["height"][1], "card_blade_width": min(0.95, max(CARD_BLADE_SHARE, params["width"] / column_width))})
    return ("grass_blade", overrides)


def litter_material(shape, base):
    return ("litter", {"shape": shape, "color": base, "second_color": scaled(base, 1.4), "dark_color": scaled(base, 0.4), "vein_color": scaled(base, 1.5), "vein_contrast": 0.4 if shape in ("leaf", "none") else 0.0})


def material_specs(kind, form, params, report):
    cards = form == "cards"
    if kind in BLADE_KINDS:
        return [blade_material(params, form, report)]
    if kind == "flower":
        stem = ("grass_blade", {"color": params["color"], "root_color": scaled(params["color"], 0.6), "tip_color": params["color"], "dry_tips": 0.0, "variation": 0.2})
        petal = ("leaf", {"color": params["petal_color"], "dark_color": scaled(params["petal_color"], 0.8), "vein_color": scaled(params["petal_color"], 1.1), "vein_contrast": 0.15, "vein_pairs": 4, "cutout": cards, "coordinates": "uv", "leaf_type": "petal", "roughness": 0.45})
        centre = ("litter", dict(litter_material("pebble" if cards else "none", params["centre_color"])[1], vein_contrast=0.0, mottling=1.0))
        return [stem, petal, centre]
    if kind == "twig":
        if cards:
            return [litter_material("twig", params["color"])]
        return [("bark", {"color": params["color"], "fissure_color": scaled(params["color"], 0.3), "coordinates": "object", "scale": 8.0, "grain": "x", "bump": 0.5})]
    if kind == "leaf":
        return [litter_material("leaf" if cards else "none", params["color"])]
    if cards:
        return [litter_material("pebble", params["color"])]
    if kind == "mound":
        return [("soil", {"color": params["color"], "moisture": 0.35, "pebbles": 0.15, "clod_size": 0.012, "coordinates": "object", "bump": 0.6})]
    return [("stone", {"color": params["color"], "secondary_color": scaled(params["color"], 0.7), "cracks": False, "cell_scale": 60.0, "coordinates": "object", "bump": 0.3})]


def material_names(prefix, kind, form):
    return [f"{prefix}_{kind}_{form}_{slot}" for slot in range(3 if kind == "flower" else 1)]


def require_free_materials(prefix, kind, form):
    for name in material_names(prefix, kind, form):
        if name in bpy.data.materials:
            raise bad_args(f"a material named {name} already exists; ground cover does not overwrite materials, so rename or delete it, or give another name")


def element_materials(prefix, kind, form, params, report, cache):
    materials = []
    for slot, (preset, overrides) in enumerate(material_specs(kind, form, params, report)):
        name = f"{prefix}_{kind}_{form}_{slot}"
        key = (name, preset, repr(sorted(overrides.items())))
        if key not in cache:
            taken = sum(1 for other in cache if other[0] == name)
            cache[key] = preset_material(name if not taken else f"{name}_v{taken}", preset, overrides)
        materials.append(cache[key])
    return materials


def make_element(name, kind, form, params, seed, budget, wind, prefix, cache):
    rng = numpy.random.default_rng([seed, KINDS.index(kind), FORMS.index(form)])
    mesh, report = build_geometry(kind, form, params, rng, budget)
    materials = element_materials(prefix, kind, form, params, report, cache)
    data = mesh.to_mesh(name, materials, wind)
    report.update(mesh.summary())
    report["budget"] = budget
    return data, mesh, report
