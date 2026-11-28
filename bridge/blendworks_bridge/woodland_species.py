"""Species niches, age classes, allometry.

Which species grows where, and how big. Species follow moisture and light by their Ellenberg indicator values
(Ellenberg et al. 1991): L from 1 (deep shade) to 9 (full light), F from 1 (dry) to 9 (wet); indifferent species (x)
take every moisture. Sizes come in three age classes whose counts fall geometrically from saplings to mature trees by de
Liocourt's quotient q (de Liocourt 1898, Meyer 1952), and a young tree is not a small copy of an old one: its crown is
narrower and reaches lower (docs/research/woodland.md)."""
import math

import numpy

from .tree_presets import PRESETS

INDIFFERENT = None
NICHES = {
    "oak": (7.0, INDIFFERENT),
    "birch": (7.0, INDIFFERENT),
    "pine": (7.0, INDIFFERENT),
    "willow": (5.0, 8.0),
    "maple": (4.0, 6.0),
    "olive": (8.0, 3.0),
    "hazel": (6.0, INDIFFERENT),
    "hawthorn": (7.0, 4.0),
    "elder": (7.0, 5.0),
    "sallow": (7.0, 9.0),
}
LIGHT_WIDTH = 1.6
MOISTURE_WIDTH = 1.4
INDIFFERENT_WIDTH = 3.5
INDIFFERENT_CENTRE = 5.5
LIGHT_SCALE = (3.0, 8.5)
MOISTURE_SCALE = (3.5, 9.0)

CROWN_RADIUS = {"oak": 6.0, "birch": 4.0, "pine": 6.4, "willow": 7.0, "maple": 4.2, "olive": 3.1,
                "hazel": 1.7, "hawthorn": 2.1, "elder": 2.25, "sallow": 2.4}

CLASSES = ("mature", "young", "sapling")
HEIGHT_SHARE = {"mature": (0.8, 1.1), "young": (0.4, 0.65), "sapling": (0.13, 0.3), "shrub": (0.65, 1.1)}
BUILT_SHARE = {"mature": 0.95, "young": 0.52, "sapling": 0.21, "shrub": 0.88}
DE_LIOCOURT_Q = 1.6
CROWN_EXPONENT = 1.25
BOLE_EXPONENT = 1.5
STEP_EXPONENT = 0.5
LEAST_STEP_SHARE = 0.5
POINTS_EXPONENT = 2.0
LEAST_POINTS = 150
LEAST_BRANCHES = 4
TIP_EXPONENT = 0.3


def site_scale(value, scale):
    return scale[0] + (scale[1] - scale[0]) * numpy.clip(value, 0.0, 1.0)


def niche_weights(species, light, moisture):
    """Weight of each species at each site, light and moisture 0 to 1: a Gaussian about its indicator values."""
    light_value = site_scale(numpy.asarray(light, dtype=numpy.float64), LIGHT_SCALE)
    moisture_value = site_scale(numpy.asarray(moisture, dtype=numpy.float64), MOISTURE_SCALE)
    weights = []
    for name in species:
        light_need, moisture_need = NICHES[name]
        fit = numpy.exp(-0.5 * ((light_value - light_need) / LIGHT_WIDTH) ** 2)
        if moisture_need is INDIFFERENT:
            fit = fit * numpy.exp(-0.5 * ((moisture_value - INDIFFERENT_CENTRE) / INDIFFERENT_WIDTH) ** 2)
        else:
            fit = fit * numpy.exp(-0.5 * ((moisture_value - moisture_need) / MOISTURE_WIDTH) ** 2)
        weights.append(fit)
    return numpy.column_stack(weights)


def pick_species(species, light, moisture, draws):
    """One species per site, drawn in proportion to the niche weights with the site's own uniform number."""
    weights = niche_weights(species, light, moisture) + 1e-12
    cumulative = numpy.cumsum(weights / weights.sum(axis=1, keepdims=True), axis=1)
    return numpy.minimum((cumulative < numpy.asarray(draws)[:, None]).sum(axis=1), len(species) - 1)


def class_shares(q=DE_LIOCOURT_Q):
    """Expected share of mature, young and sapling trees: counts n, q n and q^2 n."""
    counts = numpy.array([1.0, q, q * q])
    return dict(zip(CLASSES, counts / counts.sum()))


def crown_radius(species, share):
    return CROWN_RADIUS[species] * share ** CROWN_EXPONENT


def grown_settings(species, share, detail):
    """grow_tree fields for a tree of species at share of its mature height: a narrower crown that starts lower, fewer
    attraction points or branches, a shorter growth step."""
    preset = PRESETS[species]
    step_share = max(LEAST_STEP_SHARE, share ** STEP_EXPONENT)
    settings = {"preset": species, "height": round(preset["height"] * share, 4),
                "trunk_height": round(preset["trunk_height"] * share ** BOLE_EXPONENT, 4),
                "tip_radius": round(preset["tip_radius"] * min(1.0, share ** TIP_EXPONENT), 5)}
    if preset["method"] == "colonization":
        settings.update({
            "crown_radius": round(preset["crown_radius"] * share ** CROWN_EXPONENT, 4),
            "points": max(LEAST_POINTS, int(round(preset["points"] * share ** POINTS_EXPONENT * detail))),
            "step": round(preset["step"] * step_share, 4),
            "influence": round(preset["influence"] * step_share, 4),
            "kill": round(preset["kill"] * step_share, 4),
        })
    else:
        branches = list(preset["branches"])
        branches[0] = max(LEAST_BRANCHES, int(round(branches[0] * share * detail)))
        if len(branches) > 1:
            branches[1] = max(LEAST_BRANCHES, int(round(branches[1] * math.sqrt(share))))
        settings["branches"] = branches
    return settings
