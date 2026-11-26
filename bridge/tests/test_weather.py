import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import close, run
from sky_helpers import ground, luminance, ortho_down, render

from blendworks_bridge import weather_continuum

STORMS = (0.0, 0.25, 0.5, 0.75, 1.0)
TOP = 128
SUN = {"elevation": 45.0, "azimuth": 180.0}


def boxes(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0, location=[0.0, 0.0, 0.0])
    bridge.ok("transform", name="Box", scale=[120.0, 120.0, 200.0])
    bridge.ok("apply_transform", name="Box", scale=True)
    points = [[x, y, 100.0] for x in range(-2700, 2701, 600) for y in range(-2700, 2701, 600)]
    bridge.ok("instances", source="Box", points=points, realize=True, name="Boxes")
    bridge.ok("delete", names=["Box"])


def test_light_and_shadow_contrast_fall_with_storm(bridge):
    ground(bridge)
    boxes(bridge)
    ortho_down(bridge, "Top", 6000.0, 1000.0)
    means, contrasts = [], []
    shadow = open_ground = None
    for storm in STORMS:
        bridge.ok("weather", storm=storm, sun=SUN, form="sheet", haze=False, exposure="keep", rain_foreground=False, seed=1)
        pixels = luminance(render(bridge, f"storm_{int(storm * 100)}", TOP, 8, "Top"))
        if shadow is None:
            median = np.median(pixels)
            shadow = pixels < 0.5 * median
            open_ground = np.abs(pixels - median) < 0.1 * median
            assert shadow.sum() > 50 and open_ground.sum() > 2000, (shadow.sum(), open_ground.sum(), np.percentile(pixels, [1, 5, 25, 50, 75, 95, 99]))
        means.append(float(pixels.mean()))
        contrasts.append(float(pixels[open_ground].mean() / pixels[shadow].mean()))
    assert all(a > b for a, b in zip(means, means[1:])), means
    assert all(a > b for a, b in zip(contrasts, contrasts[1:])), contrasts
    assert contrasts[0] > 3.0 and contrasts[-1] < 1.5, contrasts


def test_presets_are_points_of_the_continuum_or_overrides(bridge):
    bridge.ok("add_camera", name="Eye", location=[0.0, 0.0, 1.7], target=[0.0, 100.0, 5.0])
    for name, entry in weather_continuum.PRESETS.items():
        result = bridge.ok("weather", preset=name, form="sheet", haze=False)
        assert result["storm"] == entry["storm"], name
        expected = weather_continuum.state(entry["storm"], 0)
        assert [layer["genus"] for layer in result["layers"]] == [layer["genus"] for layer in expected["layers"]], name
        for layer, wanted in zip(result["layers"], expected["layers"]):
            close(layer["coverage"], wanted.get("coverage", layer["coverage"]), 1e-6)
        overrides = {key: entry[key] for key in weather_continuum.OVERRIDES if key in entry}
        assert result["source"]["overrides"].get("dust") == overrides.get("dust"), name
        assert (result["lightning"] is not None) == overrides.get("lightning", False), name
        if "time_of_day" in entry:
            close(result["sun"]["elevation"], weather_continuum.TIMES[entry["time_of_day"]]["elevation"], 1e-6)


def test_rain_wet_ground_and_lightning_are_off_unless_asked(bridge):
    ground(bridge, 200.0)
    bridge.ok("add_camera", name="Eye", location=[0.0, 0.0, 1.7], target=[0.0, 100.0, 5.0])
    clear = bridge.ok("weather", preset="scattered", form="sheet", haze=False)
    assert clear["rain"]["rate"] == 0.0 and clear["lightning"] is None and clear["wet"]["materials"] == []
    kinds = {obj.get("blendworks_weather") for obj in bpy.context.scene.objects}
    assert not kinds & {"rain_streaks", "rain_veil", "lightning", "flash"}
    rainy = bridge.ok("weather", preset="heavy_rain", form="sheet", haze=False, seed=4)
    assert rainy["rain"]["veil"] and rainy["rain"]["foreground"]["streaks"] > 100
    assert rainy["wet"]["materials"] == ["Grey"] and rainy["lightning"] is None
    first = [tuple(v.co) for v in bpy.data.objects["Rain streaks"].data.vertices[:20]]
    bridge.ok("weather", preset="heavy_rain", form="sheet", haze=False, seed=4)
    assert [tuple(v.co) for v in bpy.data.objects["Rain streaks"].data.vertices[:20]] == first
    bridge.ok("weather", preset="heavy_rain", form="sheet", haze=False, seed=5)
    assert [tuple(v.co) for v in bpy.data.objects["Rain streaks"].data.vertices[:20]] != first
    nodes = bpy.data.materials["Grey"].node_tree.nodes
    assert any(node.name.startswith("wx_wet_") for node in nodes)
    dry = bridge.ok("weather", preset="heavy_rain", form="sheet", haze=False, wet=0.0, rain_foreground=False, seed=4)
    assert dry["wet"]["materials"] == [] and not any(node.name.startswith("wx_wet_") for node in nodes)
    assert "Rain streaks" not in bpy.data.objects
    storm = bridge.ok("weather", preset="thunderstorm", form="sheet", haze=False, seed=4)
    assert storm["lightning"]["bolt"] == "Lightning" and storm["lightning"]["flash"]
    bolt = [tuple(point.co) for point in bpy.data.objects["Lightning"].data.splines[0].points]
    calm = bridge.ok("weather", preset="thunderstorm", form="sheet", haze=False, lightning=False, seed=4)
    assert calm["lightning"] is None and "Lightning" not in bpy.data.objects
    bridge.ok("weather", preset="thunderstorm", form="sheet", haze=False, seed=9)
    assert [tuple(point.co) for point in bpy.data.objects["Lightning"].data.splines[0].points] != bolt


def test_wet_ground_darkens_and_glosses(bridge):
    ground(bridge, 200.0, 0.5)
    ortho_down(bridge, "Top", 100.0, 50.0)
    bridge.ok("weather", preset="overcast", form="sheet", haze=False, exposure="keep")
    dry = float(luminance(render(bridge, "dry", 16, 4, "Top")).mean())
    bridge.ok("weather", preset="overcast", form="sheet", haze=False, exposure="keep", wet=1.0)
    wet = float(luminance(render(bridge, "wet", 16, 4, "Top")).mean())
    assert wet < 0.85 * dry, (dry, wet)


def test_remove_leaves_the_clear_sky(bridge):
    ground(bridge, 200.0)
    bridge.ok("add_camera", name="Eye", location=[0.0, 0.0, 1.7], target=[0.0, 100.0, 5.0])
    bridge.ok("weather", preset="thunderstorm", form="auto")
    removed = bridge.ok("weather", remove=True)["removed"]
    assert "Lightning" in removed["objects"] and removed["clouds"]["removed"]["layers"]
    kinds = {obj.get("blendworks_weather") for obj in bpy.context.scene.objects} - {None}
    assert kinds == {"sun"}, kinds
    assert bpy.context.scene.world.get("blendworks_sky") is not None
    bridge.refuse("weather", "bad_args", remove=True, preset="clear")
    bridge.refuse("weather", "bad_args", preset="clear", storm=0.5)


def test_render_final_uses_volumes_for_auto_clouds_and_restores(bridge):
    bridge.ok("add_camera", name="Eye", location=[0.0, 0.0, 1.7], target=[0.0, 1000.0, 600.0])
    bridge.ok("sky", sun=SUN, exposure="keep")
    result = bridge.ok("clouds", layers=[{"genus": "cumulus", "coverage": 0.4, "thickness": 400.0}], form="auto", radius=3000.0, bounces=2)
    volume = bpy.data.objects[result["objects"]["volumes"][0]]
    cycles = bpy.context.scene.cycles
    before = (cycles.volume_biased, cycles.volume_bounces, volume.hide_render)
    final = bridge.ok("render_final", path="auto.exr", camera="Eye", width=24, height=24, samples=2, denoise=False, noise_threshold=0.0, preview=False, device="cpu")
    assert final["clouds"]["rendered_as"]["form"] == "volume"
    assert (cycles.volume_biased, cycles.volume_bounces, volume.hide_render) == before
    assert before[2] is True
    auto = render(bridge, "auto_again", 24, 2, "Eye")
    layers = [{"genus": "cumulus", "coverage": 0.4, "thickness": 400.0}]
    bridge.ok("clouds", layers=layers, form="volume", radius=3000.0, bounces=2)
    volume = render(bridge, "volume", 24, 2, "Eye")
    bridge.ok("clouds", layers=layers, form="sheet", radius=3000.0)
    sheet = render(bridge, "sheet", 24, 2, "Eye")
    assert float(np.abs(auto - volume).mean()) < 0.02 * float(volume.mean()), (auto.mean(), volume.mean())
    assert float(np.abs(auto - sheet).mean()) > 0.05 * float(sheet.mean()), (auto.mean(), sheet.mean())


run(globals())
