import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

from blendworks_bridge import liquid_presets

NOTE_10 = "USDA AMS, United States Standards for Grades of Extracted Honey (1985), table 1: the colour designations by the Pfund grader reading (mm) and by the optical density at 560 nm of a 3.15 cm layer (the upper limit of each class)."
USDA = (
    ("water_white", 8, 0.0945),
    ("extra_white", 17, 0.189),
    ("white", 34, 0.378),
    ("extra_light_amber", 50, 0.595),
    ("light_amber", 85, 1.389),
    ("amber", 114, 3.008),
    ("dark_amber", None, None),
)
CELL = 0.0315
HUE = 0.0137
GEOMETRIC_MEAN_TOLERANCE = 0.01


def density(name):
    """Optical density at 560 nm of a preset's honey in the 3.15 cm cell, from its absorption at 550 and 600 nm."""
    absorption = liquid_presets.PRESETS[f"honey_{name}"]["absorption"]
    at_560_from_600 = absorption[0] * math.exp(HUE * 40.0)
    at_560_from_550 = absorption[1] * math.exp(-HUE * 10.0)
    assert abs(at_560_from_600 - at_560_from_550) < 0.01 * at_560_from_600, "one caramel hue slope joins the channels"
    return at_560_from_600 * CELL / math.log(10.0)


def test_each_usda_colour_class_has_its_own_honey_within_the_cited_limits(bridge):
    lower = 0.0
    for name, pfund, upper in USDA:
        value = density(name)
        if upper is not None:
            assert lower < value <= upper, (name, value, lower, upper)
            if lower > 0.0:
                assert abs(value - math.sqrt(lower * upper)) < GEOMETRIC_MEAN_TOLERANCE * value, (name, value)
            lower = upper
        else:
            assert value > lower, (name, value)
    ladder = [density(name) for name, _, _ in USDA]
    assert ladder == sorted(ladder) and len(set(ladder)) == len(ladder), "each class is darker than the one before"


def test_honey_without_a_class_is_extra_light_amber_and_every_class_is_a_preset(bridge):
    assert liquid_presets.PRESETS["honey"]["absorption"] == liquid_presets.PRESETS["honey_extra_light_amber"]["absorption"]
    assert liquid_presets.DEFAULT_HONEY_CLASS == "extra_light_amber"
    described = {entry["name"]: entry for entry in bridge.ok("describe")["commands"]}
    allowed = described["material_liquid"]["schema"]["properties"]["preset"]["enum"]
    for name, _, _ in USDA:
        assert f"honey_{name}" in allowed
    for name, pfund, _ in USDA:
        report = bridge.ok("material_liquid", preset=f"honey_{name}", name=f"Honey_{name}")
        assert report["honey_class"] == name and len(report["pfund_mm"]) == 2
        assert report["sources"] == liquid_presets.PRESETS[f"honey_{name}"]["sources"]
    water_white = bridge.ok("material_liquid", preset="honey_water_white", name="A")
    dark = bridge.ok("material_liquid", preset="honey_dark_amber", name="B")
    assert water_white["transmittance_1cm"][1] > 0.8 > 0.2 > dark["transmittance_1cm"][1], "water white passes light, dark amber stops it"


def test_the_honey_light_through_five_centimetres_darkens_with_the_class(bridge):
    green = []
    for name, _, _ in USDA:
        absorption = liquid_presets.PRESETS[f"honey_{name}"]["absorption"]
        green.append(math.exp(-absorption[1] * 0.05))
    assert green == sorted(green, reverse=True)
    assert green[0] > 0.7 and green[-1] < 0.001


run(globals())
