"""Tree species data and materials."""

SPECIES_PROPERTY = "blendworks_species"
TREE_NAMES = ("oak", "birch", "pine", "willow", "maple", "olive")
SHRUB_NAMES = ("hazel", "hawthorn", "elder", "sallow")
SPECIES_NAMES = TREE_NAMES + SHRUB_NAMES
PRESET_SPECIES = {"weeping_willow": "willow", "gnarled_oak": "oak"}

FOLIAGE_DEFAULTS = {
    "layout": "clusters",
    "size": 0.09,
    "size_by_order": 0.9,
    "density": 18.0,
    "orders": 2,
    "tip_leaves": 3,
    "divergence": 137.5,
    "angle": 55.0,
    "shapes": 3,
    "shape_length": [0.85, 1.0, 1.25],
    "detail": "full",
    "variants": 8,
    "card": {"width": 0.55, "fold": 15.0},
    "align": {"sun": [0.0, 0.0, 1.0], "factor": 0.7, "inner": 0.2},
    "jitter": {"size": 0.2, "roll": 20.0},
    "clusters": {
        "arrangement": "alternate",
        "leaves": [4, 8],
        "spacing": 0.1,
        "spacing_variation": 0.5,
        "per_tip": 2,
        "tip_spread": 35.0,
        "angle": 50.0,
        "divergence": 137.5,
        "twig_length": 0.14,
        "twig_radius": 0.002,
        "twig_bend": 0.15,
        "forks": [1, 3],
        "fork_angle": 40.0,
        "fork_length": 0.7,
        "leaf_angle": 50.0,
        "petiole": 0.15,
        "droop": 0.0,
        "inner_keep": 0.4,
        "shade_growth": 0.25,
        "bearing_radius": 0.0,
        "reach": 0.0,
    },
    "variation": {"size": 0.25, "curl": 35.0, "fold": 10.0, "tilt": 25.0, "hue": 0.025, "saturation": 0.15, "value": 0.18, "age": 0.6, "damage": 0.7},
}

FOLIAGE = {
    "oak": {
        "size": 0.1,
        "card": {"width": 0.7, "fold": 12.0},
        "clusters": {"arrangement": "terminal", "leaves": [5, 8], "spacing": 0.13, "per_tip": 2, "twig_length": 0.11, "twig_radius": 0.0025, "leaf_angle": 45.0, "petiole": 0.08, "inner_keep": 0.2},
    },
    "birch": {
        "size": 0.055,
        "card": {"width": 0.8, "fold": 10.0},
        "clusters": {"arrangement": "alternate", "leaves": [4, 6], "forks": [0, 1], "spacing": 0.13, "per_tip": 2, "twig_length": 0.13, "twig_radius": 0.0013, "leaf_angle": 55.0, "petiole": 0.22, "droop": 0.35, "inner_keep": 0.6, "bearing_radius": 0.07},
        "variation": {"hue": 0.03, "value": 0.2},
    },
    "pine": {
        "size": 0.18,
        "shapes": 3,
        "shape_length": [0.8, 1.0, 1.25],
        "align": {"factor": 0.2, "inner": 0.0},
        "orders": 2,
        "card": {"width": 0.6, "fold": 0.0},
        "clusters": {"arrangement": "brush", "leaves": [4, 6], "forks": [1, 2], "spacing": 0.1, "per_tip": 3, "tip_spread": 28.0, "twig_length": 0.24, "twig_radius": 0.0035, "twig_bend": 0.2, "leaf_angle": 12.0, "petiole": 0.0, "inner_keep": 0.5, "shade_growth": 0.0, "bearing_radius": 0.02, "reach": 0.5},
        "variation": {"size": 0.2, "curl": 10.0, "fold": 0.0, "tilt": 20.0, "hue": 0.012, "saturation": 0.1, "value": 0.12, "age": 0.4, "damage": 0.15},
    },
    "willow": {
        "size": 0.11,
        "orders": 3,
        "detail": "low",
        "card": {"width": 0.17, "fold": 14.0},
        "align": {"factor": 0.3, "inner": 0.1},
        "clusters": {"arrangement": "alternate", "leaves": [7, 10], "forks": [0, 1], "spacing": 0.15, "per_tip": 2, "tip_spread": 20.0, "twig_length": 0.25, "twig_radius": 0.0015, "twig_bend": -0.05, "leaf_angle": 28.0, "petiole": 0.06, "droop": 0.85, "inner_keep": 0.5},
        "variation": {"curl": 45.0, "value": 0.15},
    },
    "maple": {
        "size": 0.12,
        "card": {"width": 1.0, "fold": 8.0},
        "clusters": {"arrangement": "opposite", "leaves": [2, 5], "forks": [0, 1], "spacing": 0.18, "per_tip": 2, "twig_length": 0.12, "twig_radius": 0.0025, "leaf_angle": 60.0, "petiole": 0.35, "inner_keep": 0.15},
    },
    "olive": {
        "size": 0.07,
        "card": {"width": 0.24, "fold": 18.0},
        "clusters": {"arrangement": "opposite", "leaves": [10, 16], "spacing": 0.08, "per_tip": 2, "twig_length": 0.2, "twig_radius": 0.0016, "leaf_angle": 38.0, "petiole": 0.06, "inner_keep": 0.4},
        "variation": {"hue": 0.02, "saturation": 0.1, "value": 0.15},
    },
    "hazel": {
        "size": 0.095,
        "card": {"width": 0.85, "fold": 10.0},
        "clusters": {"arrangement": "alternate", "leaves": [4, 7], "forks": [0, 1], "spacing": 0.11, "per_tip": 2, "twig_length": 0.12, "twig_radius": 0.0018, "leaf_angle": 60.0, "petiole": 0.1, "droop": 0.15, "inner_keep": 0.45},
    },
    "hawthorn": {
        "size": 0.045,
        "card": {"width": 0.8, "fold": 8.0},
        "clusters": {"arrangement": "terminal", "leaves": [5, 9], "spacing": 0.06, "per_tip": 3, "twig_length": 0.08, "twig_radius": 0.0015, "leaf_angle": 50.0, "petiole": 0.12, "inner_keep": 0.55},
        "variation": {"value": 0.15},
    },
    "elder": {
        "size": 0.08,
        "card": {"width": 0.38, "fold": 12.0},
        "clusters": {"arrangement": "opposite", "leaves": [5, 7], "forks": [0, 1], "spacing": 0.07, "per_tip": 2, "twig_length": 0.18, "twig_radius": 0.002, "leaf_angle": 55.0, "petiole": 0.05, "droop": 0.3, "inner_keep": 0.35},
    },
    "sallow": {
        "size": 0.07,
        "card": {"width": 0.5, "fold": 14.0},
        "align": {"factor": 0.4, "inner": 0.1},
        "clusters": {"arrangement": "alternate", "leaves": [6, 9], "forks": [0, 1], "spacing": 0.09, "per_tip": 2, "twig_length": 0.16, "twig_radius": 0.0015, "leaf_angle": 40.0, "petiole": 0.06, "droop": 0.1, "inner_keep": 0.5},
        "variation": {"hue": 0.02, "value": 0.15},
    },
}

LEAF_MATERIALS = {
    "oak": {"color": [0.03, 0.085, 0.016], "dark_color": [0.012, 0.035, 0.007], "underside_color": [0.08, 0.13, 0.05], "shape": "lobed", "vein_pairs": 6, "roughness": 0.55},
    "birch": {"color": [0.065, 0.15, 0.03], "dark_color": [0.025, 0.07, 0.012], "underside_color": [0.12, 0.19, 0.07], "shape": "deltoid", "vein_pairs": 8, "roughness": 0.5},
    "pine": {"color": [0.045, 0.08, 0.07], "dark_color": [0.014, 0.03, 0.026], "underside_color": [0.065, 0.09, 0.085], "translucency": 0.3, "shape": "brush", "needles": 24, "vein_pairs": 2, "vein_contrast": 0.12, "roughness": 0.45},
    "willow": {"color": [0.075, 0.14, 0.04], "dark_color": [0.03, 0.065, 0.016], "underside_color": [0.2, 0.24, 0.17], "shape": "lanceolate", "vein_pairs": 14, "roughness": 0.55},
    "maple": {"color": [0.045, 0.12, 0.022], "dark_color": [0.015, 0.05, 0.008], "underside_color": [0.1, 0.16, 0.06], "shape": "palmate", "vein_pairs": 5, "roughness": 0.5},
    "olive": {"color": [0.06, 0.08, 0.04], "dark_color": [0.025, 0.035, 0.016], "underside_color": [0.27, 0.29, 0.24], "shape": "lanceolate", "vein_pairs": 4, "roughness": 0.4},
    "hazel": {"color": [0.05, 0.11, 0.022], "dark_color": [0.018, 0.045, 0.009], "underside_color": [0.1, 0.15, 0.06], "shape": "ovate", "vein_pairs": 7, "roughness": 0.6},
    "hawthorn": {"color": [0.04, 0.1, 0.02], "dark_color": [0.014, 0.04, 0.008], "underside_color": [0.09, 0.14, 0.06], "shape": "lobed", "vein_pairs": 4, "roughness": 0.45},
    "elder": {"color": [0.05, 0.12, 0.025], "dark_color": [0.018, 0.05, 0.01], "underside_color": [0.1, 0.16, 0.07], "shape": "lanceolate", "vein_pairs": 8, "roughness": 0.5},
    "sallow": {"color": [0.05, 0.09, 0.035], "dark_color": [0.02, 0.04, 0.014], "underside_color": [0.2, 0.22, 0.17], "shape": "ovate", "vein_pairs": 9, "roughness": 0.6},
}

BARK_MATERIALS = {
    "oak": {"color": [0.12, 0.1, 0.08], "fissure_color": [0.025, 0.02, 0.016], "lichen_color": [0.16, 0.16, 0.12], "fissure_depth": 0.8, "fissure_spacing": 0.045},
    "birch": {"color": [0.55, 0.53, 0.48], "fissure_color": [0.05, 0.045, 0.04], "lichen_color": [0.45, 0.45, 0.4], "fissure_depth": 0.15, "fissure_spacing": 0.08, "lenticels": 1.0},
    "pine": {"color": [0.16, 0.12, 0.095], "fissure_color": [0.014, 0.01, 0.008], "lichen_color": [0.26, 0.24, 0.21], "fissure_depth": 1.0, "fissure_spacing": 0.075, "upper_color": [0.33, 0.13, 0.05], "upper_start": 6.5, "upper_end": 9.5, "upper_fissures": 0.2},
    "willow": {"color": [0.13, 0.11, 0.09], "fissure_color": [0.03, 0.025, 0.02], "lichen_color": [0.15, 0.15, 0.11], "fissure_depth": 0.85, "fissure_spacing": 0.035},
    "maple": {"color": [0.16, 0.14, 0.12], "fissure_color": [0.05, 0.04, 0.03], "lichen_color": [0.2, 0.2, 0.17], "fissure_depth": 0.4, "fissure_spacing": 0.03},
    "olive": {"color": [0.2, 0.19, 0.16], "fissure_color": [0.04, 0.035, 0.03], "lichen_color": [0.28, 0.27, 0.22], "fissure_depth": 0.7, "fissure_spacing": 0.05},
    "hazel": {"color": [0.2, 0.14, 0.1], "fissure_color": [0.06, 0.045, 0.035], "lichen_color": [0.24, 0.24, 0.19], "fissure_depth": 0.12, "fissure_spacing": 0.05, "lenticels": 0.6},
    "hawthorn": {"color": [0.17, 0.15, 0.13], "fissure_color": [0.04, 0.035, 0.03], "lichen_color": [0.22, 0.23, 0.18], "fissure_depth": 0.55, "fissure_spacing": 0.025},
    "elder": {"color": [0.24, 0.21, 0.17], "fissure_color": [0.07, 0.06, 0.05], "lichen_color": [0.26, 0.26, 0.2], "fissure_depth": 0.7, "fissure_spacing": 0.03},
    "sallow": {"color": [0.17, 0.16, 0.13], "fissure_color": [0.05, 0.045, 0.04], "lichen_color": [0.22, 0.22, 0.18], "fissure_depth": 0.3, "fissure_spacing": 0.04},
}

MESH = {
    "oak": {"flare": {"amount": 0.7, "lobes": 0.8}, "root_flare": {"amount": 1.8}},
    "birch": {"flare": {"amount": 0.35, "lobes": 0.4}, "min_radius": 0.0012},
    "pine": {"flare": {"amount": 0.45, "lobes": 0.5}, "min_radius": 0.002},
    "willow": {"flare": {"amount": 0.5, "lobes": 0.6}, "root_flare": {"amount": 1.4}, "min_radius": 0.002},
    "maple": {"flare": {"amount": 0.5, "lobes": 0.6}},
    "olive": {"flare": {"amount": 0.8, "lobes": 0.9}, "root_flare": {"amount": 2.0}},
    "hazel": {"flare": {"amount": 0.2, "lobes": 0.3}, "min_radius": 0.0015},
    "hawthorn": {"flare": {"amount": 0.3, "lobes": 0.4}, "min_radius": 0.0015},
    "elder": {"flare": {"amount": 0.25, "lobes": 0.3}, "min_radius": 0.0018},
    "sallow": {"flare": {"amount": 0.2, "lobes": 0.3}, "min_radius": 0.0015},
}

FILL_FLOOR = {"oak": 0.54, "birch": 0.34, "pine": 0.54, "willow": 0.5, "maple": 0.5, "olive": 0.54, "hazel": 0.5, "hawthorn": 0.54, "elder": 0.45, "sallow": 0.5}

NESTED = ("card", "align", "jitter", "clusters", "variation")


def species_of(obj):
    found = obj.get(SPECIES_PROPERTY) if obj is not None else None
    return found if found in SPECIES_NAMES else None


def merged(*layers):
    result = {}
    for layer in layers:
        for key, value in layer.items():
            result[key] = {**result.get(key, {}), **value} if key in NESTED and isinstance(value, dict) else value
    return result


def foliage_settings(species, given):
    return merged(FOLIAGE_DEFAULTS, FOLIAGE.get(species, {}), given)


def species_material(ctx, kind, species, name):
    import bpy

    from .commands.procedural import material_procedural
    from .registry import COMMANDS
    from .schema import validate

    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    params = dict(LEAF_MATERIALS[species] if kind == "leaf" else BARK_MATERIALS[species]) if species else {}
    if kind == "leaf":
        params.update({"cutout": True, "translucency": params.get("translucency", 0.45), "petiole": foliage_settings(species, {})["clusters"]["petiole"]})
    else:
        params.update({"coordinates": "uv", "grain": "y"})
    material_procedural(ctx, validate(COMMANDS["material_procedural"].schema, {"name": name, kind: params}))
    return bpy.data.materials[name]
