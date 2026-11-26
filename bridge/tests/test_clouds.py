import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from sky_helpers import fisheye_directions, fisheye_up, ground, luminance, ortho_down, render

FISHEYE = 96
COVER_FISHEYE = 256
ZENITH_LIMIT = math.radians(60.0)
COVERAGE_TOLERANCE = 0.07
CLOUD_CONTRAST = 0.2
SHADOW_FACTOR = 2.0
BASE_SPREAD = 28.0
BASE_RAISED = 0.3


def sky_cover(bridge, name, layer, form="sheet"):
    """Share of the sky within 60 degrees of the zenith, by solid angle, whose colour the clouds change."""
    bridge.ok("clouds", remove=True)
    clear = luminance(render(bridge, name + "_clear", COVER_FISHEYE, 1, "Up"))
    bridge.ok("clouds", layers=[layer], form=form)
    cloudy = luminance(render(bridge, name, COVER_FISHEYE, 1, "Up"))
    _, zenith, inside = fisheye_directions(COVER_FISHEYE)
    region = inside & (zenith <= ZENITH_LIMIT)
    weight = np.where(zenith > 1e-6, np.sin(zenith) / np.maximum(zenith, 1e-6), 1.0)[region]
    changed = (np.abs(cloudy - clear) / np.maximum(clear, 1e-6) > CLOUD_CONTRAST)[region]
    return float((changed * weight).sum() / weight.sum())


def test_measured_cover_matches_the_coverage(bridge):
    fisheye_up(bridge)
    bridge.ok("sky", sun={"elevation": 50.0, "azimuth": 180.0}, exposure="keep")
    for coverage in (0.2, 0.5, 0.8):
        layers = [{"genus": "altocumulus", "coverage": coverage, "cell": 500.0, "thickness": 30.0, "seed": seed} for seed in (1, 3)]
        measured = sum(sky_cover(bridge, f"cover_{int(coverage * 10)}_{index}", layer) for index, layer in enumerate(layers)) / len(layers)
        assert abs(measured - coverage) <= COVERAGE_TOLERANCE, (coverage, measured)
    overcast = sky_cover(bridge, "cover_stratus", {"genus": "stratus", "coverage": 1.0})
    assert overcast >= 0.97, overcast
    assert sky_cover(bridge, "cover_none", {"genus": "cumulus", "coverage": 0.0}) <= 0.01


def test_same_seed_same_sky_other_seed_other_sky(bridge):
    fisheye_up(bridge)
    bridge.ok("sky", sun={"elevation": 40.0, "azimuth": 200.0}, exposure="keep")
    images = []
    for seed in (4, 4, 5):
        bridge.ok("clouds", layers=[{"genus": "cumulus", "coverage": 0.4, "seed": seed}], form="sheet")
        images.append(render(bridge, f"seed_{len(images)}", 48, 1, "Up"))
    assert np.array_equal(images[0], images[1])
    assert float(np.abs(images[0] - images[2]).mean()) > 0.01 * float(images[0].mean())


def ground_spread(bridge, name, form):
    pixels = luminance(render(bridge, name, 64, 4, "Top"))
    return float(np.percentile(pixels, 95)), float(np.percentile(pixels, 5))


def test_clouds_shadow_the_ground(bridge):
    ground(bridge)
    ortho_down(bridge, "Top", 6000.0)
    bridge.ok("sky", sun={"elevation": 70.0, "azimuth": 180.0}, exposure="keep")
    lit, shaded = ground_spread(bridge, "no_clouds", "sheet")
    assert lit / shaded < 1.1, (lit, shaded)
    for form in ("sheet", "volume"):
        bridge.ok("clouds", layers=[{"genus": "cumulus", "coverage": 0.5, "thickness": 600.0, "seed": 2}], form=form, radius=6000.0, bounces=1)
        lit, shaded = ground_spread(bridge, "shadows_" + form, form)
        assert lit / shaded > SHADOW_FACTOR, (form, lit, shaded)


def test_clouds_dim_the_visible_sun(bridge):
    bridge.ok("add_camera", name="AtSun", location=[0.0, 0.0, 1.0], rotation=[90.0 - 0.0, 0.0, 0.0], lens=600.0)
    bridge.ok("sky", sun={"elevation": 1.0e-3 + 60.0, "azimuth": 0.0}, exposure="keep")
    bridge.ok("look_at", name="AtSun", point=[0.0, 1000.0 * math.cos(math.radians(60.0)), 1.0 + 1000.0 * math.sin(math.radians(60.0))])
    clear = float(luminance(render(bridge, "sun_clear", 16, 4, "AtSun")).max())
    bridge.ok("clouds", layers=[{"genus": "altostratus", "coverage": 1.0}], form="sheet")
    veiled = float(luminance(render(bridge, "sun_veiled", 16, 4, "AtSun")).max())
    bridge.ok("clouds", layers=[{"genus": "nimbostratus", "coverage": 1.0}], form="sheet")
    hidden = float(luminance(render(bridge, "sun_hidden", 16, 4, "AtSun")).max())
    assert clear > veiled > hidden, (clear, veiled, hidden)
    assert veiled > 0.01 * clear and hidden < 0.01 * clear


def test_forms_and_objects(bridge):
    bridge.ok("sky", sun={"elevation": 40.0, "azimuth": 200.0}, exposure="keep")
    bridge.ok("add_camera", name="Eye", location=[0.0, 0.0, 1.7], target=[0.0, 100.0, 10.0])
    result = bridge.ok("clouds", layers=[{"genus": "cumulus"}, {"genus": "cirrus"}, {"genus": "cumulonimbus"}], form="auto")
    volumes = [bpy.data.objects[name] for name in result["objects"]["volumes"]]
    assert len(volumes) == 2 and all(obj.hide_render for obj in volumes)
    assert len(result["objects"]["shadows"]) == 2
    assert result["cameras"]["Eye"] > 15000.0
    storm = next(layer for layer in result["layers"] if layer["genus"] == "cumulonimbus")
    assert storm["centre"][1] > 20000.0 and storm["centre"][0] < -3000.0
    assert "render_final" in result["cost"]
    for obj in volumes:
        assert not obj.visible_get()
    bridge.refuse("clouds", "bad_args", layers=[{"genus": "cumulus", "centre": [0.0, 0.0]}])
    bridge.refuse("clouds", "bad_args", layers=[{"genus": "fog"}])
    removed = bridge.ok("clouds", remove=True)
    assert removed["removed"]["layers"] and not any(obj.get("blendworks_weather") for obj in bpy.context.scene.objects if obj.name != "Sun")


def cloud_bases(pixels, metres_per_pixel, bottom):
    """Height of the lowest cloud pixel in every column that has cloud, in metres."""
    mask = pixels > 0.3 * float(np.percentile(pixels, 99))
    rows = pixels.shape[0]
    bases = []
    for column in range(pixels.shape[1]):
        filled = np.nonzero(mask[:, column])[0]
        if filled.size:
            bases.append(bottom + (rows - 1 - filled.max()) * metres_per_pixel)
    return np.array(bases)


def test_cloud_bases_are_ragged_and_uneven(bridge):
    bridge.ok("sky", sun={"elevation": 60.0, "azimuth": 180.0}, exposure="keep")
    width, height, bottom = 10000.0, 1200.0, 900.0
    bridge.ok("add_camera", name="Side", location=[0.0, -2000.0, bottom + height / 2.0], rotation=[90.0, 0.0, 0.0], orthographic_scale=width)
    data = bpy.data.objects["Side"].data
    data.clip_start = 1940.0
    data.clip_end = 2060.0
    bridge.ok("clouds", layers=[{"genus": "cumulus", "coverage": 0.3, "base": 1200.0, "thickness": 600.0, "cell": 600.0, "seed": 4}], form="volume", radius=6000.0, bounces=1)
    bpy.context.scene.world.node_tree.nodes["Sky Background"].inputs["Strength"].default_value = 0.0
    pixels = luminance(render(bridge, "side", 340, 16, "Side", height=41))
    bases = cloud_bases(pixels, width / 340, bottom)
    assert bases.size >= 100, bases.size
    spread = float(np.std(bases))
    raised = float(np.mean(bases >= bases.min() + 2.5 * width / 340))
    assert spread >= BASE_SPREAD, spread
    assert raised >= BASE_RAISED, raised


def test_clouds_need_the_sky(bridge):
    bridge.refuse("clouds", "bad_args", layers=[{"genus": "cumulus"}])


run(globals())
