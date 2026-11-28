"""What each rock type looks like at the scale of its grains, and where every number comes from.

Colours are linear albedo, roughness the Principled roughness of dry rock, lengths metres. Sources (docs/research/rock-realism.md):
- Le Maitre et al. (2002, the IUGS classification of igneous rocks): grain size fine under 1 mm, medium 1 to 5 mm, coarse
  above; granite is leucocratic, its colour index (the share of dark minerals) mostly 5 to 20 %; Streckeisen (1976): quartz
  is 20 to 60 % of the light minerals. Granite's crystals and groundmass are medium grained and 12 % of it is biotite.
- Kokaly et al. (2017, USGS Spectral Library 7): feldspars are pale (visible reflectance above 0.3), quartz is clear and
  reads as grey in a rock, biotite and basalt are near black (under 0.1); sandstone is buff to red (0.15 to 0.45) and
  limestone pale (0.3 to 0.55).
- Wentworth (1922) grain sizes of sediments; Campbell (1967) bed and lamina thicknesses of sandstone;
- Ford and Williams (2007) solution pits on limestone;
- Lekner and Dorf (1988) why wet surfaces are darker.
Dry rock is rough: its roughness is set high (0.8 to 0.96) and the wet and dry test holds the specular light of dry rock
to a quarter of wet rock's.
"""

LITHOLOGIES = ("granite", "sandstone", "limestone", "basalt")

GRANITE = {
    "crystals": {
        "grain": 0.0045,
        "share": 0.6,
        "minerals": (
            {"name": "plagioclase", "share": 0.7, "color": (0.34, 0.33, 0.31), "relief": 0.0},
            {"name": "orthoclase", "share": 0.3, "color": (0.36, 0.27, 0.22), "relief": 0.0},
        ),
    },
    "groundmass": {
        "grain": 0.0016,
        "minerals": (
            {"name": "plagioclase", "share": 0.15, "color": (0.34, 0.33, 0.31), "relief": 0.0},
            {"name": "quartz", "share": 0.55, "color": (0.14, 0.14, 0.135), "relief": 1.0},
            {"name": "biotite", "share": 0.3, "color": (0.03, 0.028, 0.025), "relief": -0.6},
        ),
    },
    "grain": 0.004,
    "roughness": (0.8, 0.9),
    "rind": (0.3, 0.27, 0.22),
    "relief_share": {"grain": 0.6, "pits": 0.05, "cracks": 0.5, "fracture": 1.0, "surface": 1.25},
    "pits": {"size": 0.004, "cover": 0.01},
    "crack_spacing": 0.16,
    "conchoidal": 0.0,
}

SANDSTONE = {
    "color": (0.3, 0.22, 0.14),
    "band_color": (0.22, 0.13, 0.07),
    "grain": 0.0004,
    "bed": 0.06,
    "lamina": 0.006,
    "roughness": (0.8, 0.88),
    "rind": (0.26, 0.2, 0.14),
    "relief_share": {"grain": 0.3, "pits": 0.05, "cracks": 0.45, "fracture": 0.9, "bedding": 0.4, "surface": 1.0},
    "pits": {"size": 0.003, "cover": 0.01},
    "crack_spacing": 0.25,
    "conchoidal": 0.0,
}

LIMESTONE = {
    "color": (0.42, 0.405, 0.375),
    "grain": 0.0002,
    "roughness": (0.85, 0.93),
    "rind": (0.36, 0.35, 0.33),
    "relief_share": {"grain": 0.15, "pits": 2.5, "cracks": 0.5, "fracture": 0.8, "surface": 0.9},
    "pits": {"size": 0.008, "cover": 0.12},
    "crack_spacing": 0.2,
    "conchoidal": 0.03,
}

BASALT = {
    "color": (0.05, 0.047, 0.044),
    "speck_color": (0.085, 0.08, 0.074),
    "grain": 0.0006,
    "roughness": (0.88, 0.96),
    "rind": (0.075, 0.062, 0.05),
    "relief_share": {"grain": 0.25, "pits": 2.0, "cracks": 0.45, "fracture": 0.9, "surface": 1.1},
    "pits": {"size": 0.004, "cover": 0.09},
    "crack_spacing": 0.14,
    "conchoidal": 0.04,
}

TABLE = {"granite": GRANITE, "sandstone": SANDSTONE, "limestone": LIMESTONE, "basalt": BASALT}

WATER_INDEX = 1.33
WATER_OUTER_REFLECTANCE = 0.066


def lithology(name):
    """The table of one rock type; granite for an unknown name."""
    return TABLE.get(name, GRANITE)


def mixed(minerals):
    return tuple(sum(mineral["share"] * mineral["color"][channel] for mineral in minerals) for channel in range(3))


def mean_color(name):
    """Mean linear albedo of a rock type: granite's crystals and groundmass by their shares, else its colour."""
    table = lithology(name)
    if "crystals" not in table:
        return tuple(table["color"])
    share = table["crystals"]["share"]
    crystals, groundmass = mixed(table["crystals"]["minerals"]), mixed(table["groundmass"]["minerals"])
    return tuple(share * crystals[channel] + (1.0 - share) * groundmass[channel] for channel in range(3))


def wet_albedo(albedo):
    """Albedo of a rough surface under a water film (Lekner and Dorf 1988): light enters the film (1 - Re), is reflected by the
    surface (A) and leaves it (1 - Ri), the rest Ri of it returning to the surface again; Ri = 1 - (1 - Re) / n^2 is the mean
    internal reflectance of the water surface for diffuse light. A = 0.3 gives 0.17, about 0.57 of the dry albedo."""
    inner = 1.0 - (1.0 - WATER_OUTER_REFLECTANCE) / (WATER_INDEX * WATER_INDEX)
    return (1.0 - WATER_OUTER_REFLECTANCE) * albedo * (1.0 - inner) / (1.0 - albedo * inner)
