import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from harness import run
from liquid_helpers import dark_world, edge_position, emitter, ortho, tank
from sky_helpers import render

from blendworks_bridge import liquid_presets, liquid_shader

HALF = 0.04
VIEW = 40.0


def refraction_shift(bridge, preset):
    """Orthographic rays at VIEW degrees to the face of a tank pass 2 HALF of liquid; the edge behind moves sideways."""
    dark_world(bridge)
    tank(bridge, "Tank", HALF, 0.12)
    bridge.ok("transform", name="Tank", scale=[4.0, 1.0, 1.0])
    bridge.ok("apply_transform", name="Tank", scale=True)
    bridge.ok("liquid_fill", container="Tank", preset=preset, level=0.07, name="Liquid", meniscus=False)
    emitter(bridge, "Back", 0.6, (0.6 * math.tan(math.radians(VIEW)) - 0.3, 0.6, 0.06), 1.0, (90.0, 0.0, 0.0))
    yaw = math.radians(VIEW)
    distance = 1.0
    location = (-math.sin(yaw) * distance, -math.cos(yaw) * distance, 0.06)
    ortho(bridge, "Side", location, (90.0, 0.0, -VIEW), 0.12)
    pixels = render(bridge, f"shift_{preset}", 240, 8, "Side")[..., 1]
    rows = pixels.shape[0]
    air = [edge_position(pixels[row]) for row in range(int(rows * 0.08), int(rows * 0.2))]
    liquid = [edge_position(pixels[row]) for row in range(int(rows * 0.55), int(rows * 0.75))]
    air = np.median([value for value in air if value is not None])
    liquid = np.median([value for value in liquid if value is not None])
    return (liquid - air) * 0.12 / 240.0


def expected_shift(ior):
    incidence = math.radians(VIEW)
    refracted = math.asin(math.sin(incidence) / ior)
    return 2.0 * HALF * math.sin(incidence - refracted) / math.cos(refracted)


def test_refraction_through_a_filled_tank_shifts_an_edge_by_the_index(bridge):
    for preset in ("water_fresh", "oil"):
        bridge.ok("new_scene")
        measured = abs(refraction_shift(bridge, preset))
        wanted = expected_shift(liquid_presets.PRESETS[preset]["ior"])
        assert abs(measured - wanted) <= 0.08 * wanted, (preset, measured, wanted)


def depth_pair(bridge, preset, shallow, deep):
    dark_world(bridge)
    for name, level, x in (("Shallow", shallow, -0.06), ("Deep", deep, 0.06)):
        tank(bridge, name, 0.04, deep + 0.03, location=(x, 0.0, 0.0))
        bridge.ok("liquid_fill", container=name, preset=preset, level=level + 0.003, name=f"{name}_liquid", meniscus=False, foam=0.0, bubbles=0)
    emitter(bridge, "Under", 1.0, (0.0, 0.0, -0.05), 1.0)
    ortho(bridge, "Top", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 0.24)
    pixels = render(bridge, f"depth_{preset}", 96, 16, "Top")
    centre = pixels.shape[0] // 2
    left = pixels[centre - 4:centre + 4, 18:30].reshape(-1, 3).mean(axis=0)
    right = pixels[centre - 4:centre + 4, 66:78].reshape(-1, 3).mean(axis=0)
    return left, right


def test_light_through_clear_liquid_falls_with_depth_by_beer_lambert(bridge):
    shallow, deep = 0.02, 0.06
    left, right = depth_pair(bridge, "beer", shallow, deep)
    absorption, scattering = liquid_shader.coefficients(liquid_presets.PRESETS["beer"])
    wanted = np.exp(-(np.array(absorption) + np.array(scattering)) * (deep - shallow))
    measured = right / left
    assert np.all(np.abs(measured - wanted) <= 0.05 * wanted + 0.004), (measured, wanted)
    assert measured[0] > measured[1] > measured[2]


GOLDEN = {"red": (0.25, 0.5), "green": (0.07, 0.22), "blue": (0.0, 0.01), "green_to_red": (0.25, 0.55)}


def test_honey_glows_golden_amber_through_five_centimetres(bridge):
    """5 cm of extra light amber honey passes a golden share of white light: about a third of the red, a seventh of the green, no blue."""
    dark_world(bridge)
    tank(bridge, "Jar", 0.04, 0.08, location=(-0.06, 0.0, 0.0))
    bridge.ok("liquid_fill", container="Jar", preset="honey", level=0.053, name="Honey", meniscus=False)
    tank(bridge, "Empty", 0.04, 0.08, location=(0.06, 0.0, 0.0))
    emitter(bridge, "Under", 1.0, (0.0, 0.0, -0.05), 1.0)
    ortho(bridge, "Top", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 0.24)
    pixels = render(bridge, "honey_golden", 96, 16, "Top")
    centre = pixels.shape[0] // 2
    honey = pixels[centre - 4:centre + 4, 18:30].reshape(-1, 3).mean(axis=0)
    empty = pixels[centre - 4:centre + 4, 66:78].reshape(-1, 3).mean(axis=0)
    passed = honey / empty
    absorption, _ = liquid_shader.coefficients(liquid_presets.PRESETS["honey"])
    expected = np.exp(-np.array(absorption) * 0.05)
    for value, key in ((passed, "measured"), (expected, "preset")):
        for channel, share in zip(("red", "green", "blue"), value):
            low, high = GOLDEN[channel]
            assert low <= share <= high, (key, channel, share, value)
        low, high = GOLDEN["green_to_red"]
        assert low <= value[1] / value[0] <= high, (key, value)
    assert np.all(np.abs(passed - expected) <= 0.12 * expected + 0.01), (passed, expected)


def background_contrast(bridge, preset, thickness):
    dark_world(bridge)
    tank(bridge, "Tray", 0.05, thickness + 0.02)
    if preset is not None:
        bridge.ok("liquid_fill", container="Tray", preset=preset, level=0.003 + thickness, name="Layer", meniscus=False)
    emitter(bridge, "White", 0.05, (-0.025, 0.0, -0.01), 1.0)
    bridge.ok("add_light", type="sun", name="Sun", rotation=[30.0, 0.0, 0.0], energy=2.0)
    ortho(bridge, "Top", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 0.1)
    pixels = render(bridge, f"layer_{preset}", 64, 16, "Top").mean(axis=-1)
    bright = pixels[24:40, 12:20].mean()
    dark = pixels[24:40, 44:52].mean()
    return (bright - dark) / max(bright + dark, 1e-9)


def test_milk_and_paint_hide_what_is_behind_them_and_water_does_not(bridge):
    contrasts = {}
    for preset, thickness in (("water_fresh", 0.01), ("milk", 0.01), ("paint", 0.001), (None, 0.01)):
        bridge.ok("new_scene")
        contrasts[preset] = background_contrast(bridge, preset, thickness)
    assert contrasts[None] > 0.9, contrasts
    assert contrasts["water_fresh"] > 0.8 * contrasts[None], contrasts
    assert contrasts["milk"] < 0.03 and contrasts["paint"] < 0.03, contrasts


def test_lava_glows_in_its_cracks_and_its_crust_stays_dark(bridge):
    dark_world(bridge)
    bridge.ok("add_primitive", type="plane", name="Flow", size=4.0)
    report = bridge.ok("material_liquid", preset="lava", objects=["Flow"], crust_scale=0.5)
    ortho(bridge, "Top", (0.0, 0.0, 5.0), (0.0, 0.0, 0.0), 4.0)
    pixels = render(bridge, "lava", 128, 8, "Top") @ np.array([0.2126, 0.7152, 0.0722])
    dark = pixels == 0.0
    lit = pixels > 0.01 * report["emission_strength"]
    assert abs(dark.mean() - report["crust"]) < 0.12, (dark.mean(), report["crust"])
    assert lit.mean() > 0.5 * (1.0 - report["crust"]), lit.mean()
    assert pixels.max() <= report["emission_strength"] * 1.05, (pixels.max(), report)
    assert np.percentile(pixels[lit], 99) > 0.3 * report["emission_strength"], (np.percentile(pixels[lit], 99), report)
    bridge.ok("material_liquid", preset="lava", objects=["Flow"], crust_scale=0.5, crust=0.35, name="Thin crust")
    thin = render(bridge, "lava_thin", 128, 8, "Top") @ np.array([0.2126, 0.7152, 0.0722])
    assert abs((thin == 0.0).mean() - 0.35) < 0.12, (thin == 0.0).mean()
    cold = bridge.ok("material_liquid", preset="lava", name="Cold", temperature=700.0)
    assert cold["emission_strength"] < report["emission_strength"] * 1e-3


def test_every_preset_states_its_physics_and_sources(bridge):
    required = ("water_fresh", "water_sea", "water_muddy", "wine", "beer", "oil", "milk", "juice", "coffee", "paint", "honey", "syrup", "mud", "lava", "molten_metal")
    for name in required:
        entry = liquid_presets.PRESETS[name]
        for key in ("ior", "roughness", "density", "viscosity", "surface_tension", "contact_angle", "sources"):
            assert key in entry, (name, key)
        if entry["mode"] == "clear":
            assert len(entry["absorption"]) == 3 and max(entry["absorption"]) > 0.0, name
        if name in ("milk", "paint", "mud"):
            assert entry["mode"] == "opaque", name
        if name in ("lava", "molten_metal"):
            assert entry["temperature"] > 1000.0 and 0.0 < entry["crust"] < 1.0, name
        result = bridge.ok("material_liquid", preset=name)
        assert result["sources"] == entry["sources"]
    research = open(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "research", "liquids.md"), encoding="utf-8").read()
    for name in required:
        for source in liquid_presets.PRESETS[name]["sources"]:
            assert f"`{source}`" in research, (name, source)
    assert liquid_presets.PRESETS["beer"]["foam"]["height"] > 0.0
    bridge.refuse("material_liquid", "bad_args", preset="water_fresh", temperature=1200.0)
    bridge.refuse("material_liquid", "bad_args", preset="wine", color=[1.0, 0.0, 0.0])


run(globals())
