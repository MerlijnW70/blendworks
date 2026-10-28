import base64
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from final_helpers import EXACT, Recorded, camera_on_y, channels, halves_contrast, linear, split_card
from harness import close, run, snapshot

from blendworks_bridge import atmosphere_haze, render_outputs

VISIBILITY = 60.0
SIGMA = -math.log(0.02) / VISIBILITY
DISTANCES = (5.0, 10.0, 20.0, 40.0)
WHITE = 4.0
BOUNDS = {"min": [-60.0, -5.0, -20.0], "max": [60.0, 70.0, 60.0]}
VIEW = 36.0 / 50.0


def card_at(bridge, distance, height=0.0):
    bridge.ok("new_scene")
    bridge.ok("set_world", color=[0.5, 0.5, 0.5], strength=1.0)
    split_card(bridge, "Card", distance, VIEW * distance * 1.2, z=height, white=WHITE)
    camera_on_y(bridge, location=(0.0, 0.0, height))


def contrast(bridge, name, samples):
    bridge.ok("render_final", path=f"{name}.exr", width=32, height=32, samples=samples, **EXACT)
    return halves_contrast(linear(bridge, f"{name}.exr"))[0] / WHITE


def haze(bridge, **settings):
    options = {"visibility": VISIBILITY, "tint": [1.0, 1.0, 1.0], "anisotropy": 0.0, "bounds": BOUNDS}
    options.update(settings)
    return bridge.ok("atmosphere", **options)


def test_haze_reduces_contrast_with_distance_as_koschmieder_predicts(bridge):
    for method, samples, tolerance in (("depth", 4, 0.03), ("volume", 48, 0.15)):
        measured = []
        for distance in DISTANCES:
            card_at(bridge, distance)
            clear = contrast(bridge, f"clear_{distance}", 4)
            assert abs(clear - 1.0) < 0.02, (distance, clear)
            haze(bridge, method=method, airlight=[0.5, 0.5, 0.5])
            measured.append(contrast(bridge, f"{method}_{distance}", samples))
        predicted = [math.exp(-SIGMA * distance) for distance in DISTANCES]
        print(f"haze contrast by distance ({method}): " + ", ".join(f"{d:g} m {m:.3f} (predicted {p:.3f})" for d, m, p in zip(DISTANCES, measured, predicted)))
        assert all(near > far for near, far in zip(measured, measured[1:])), measured
        for value, expected in zip(measured, predicted):
            assert abs(value - expected) <= tolerance * expected + 0.01, (method, measured, predicted)


def test_density_falls_with_height_and_ground_fog_adds_to_it(bridge):
    distance = 20.0
    values = {}
    for name, height, settings in (
        ("low", 0.0, {}),
        ("high", 20.0, {}),
        ("fog", 0.0, {"ground_fog": {"visibility": 30.0, "height": 2.0}}),
    ):
        card_at(bridge, distance, height)
        result = haze(bridge, method="depth", height_falloff=10.0, airlight=[0.5, 0.5, 0.5], **settings)
        assert result["object"] == "Atmosphere"
        values[name] = contrast(bridge, name, 4)
    sigma_fog = -math.log(0.02) / 30.0
    close(values["low"], math.exp(-SIGMA * distance), 0.01)
    close(values["high"], math.exp(-SIGMA * math.exp(-2.0) * distance), 0.01)
    close(values["fog"], math.exp(-(SIGMA + sigma_fog) * distance), 0.01)
    card_at(bridge, distance, 20.0)
    haze(bridge, method="volume", height_falloff=10.0)
    lifted = contrast(bridge, "high_volume", 48)
    assert abs(lifted - values["high"]) < 0.12 * values["high"], (lifted, values["high"])


def test_optical_depth_matches_a_numerical_integral(bridge):
    settings = {"visibility": 500.0, "base_height": 2.0, "height_falloff": 15.0, "ground_fog": {"visibility": 50.0, "height": 3.0}, "tint": [1.0, 1.0, 1.0]}
    start, end, distance = 1.0, 31.0, 80.0
    steps = 20000
    heights = start + (end - start) * (np.arange(steps) + 0.5) / steps
    integral = sum(atmosphere_haze.density_at(settings, z) for z in heights) * distance / steps
    close(float(atmosphere_haze.optical_depth(settings, start, end, distance)), integral, 1e-4 * integral)
    close(float(atmosphere_haze.optical_depth(settings, 5.0, 5.0, distance)), atmosphere_haze.density_at(settings, 5.0) * distance, 1e-9)


def test_atmosphere_builds_a_box_or_world_volume_and_removes_it(bridge):
    card_at(bridge, 10.0)
    result = haze(bridge, height_falloff=25.0, tint=[1.0, 0.9, 0.8])
    close(result["extinction_per_metre"], SIGMA, 1e-8)
    domain = bpy.data.objects["Atmosphere"]
    material = domain.data.materials[0]
    assert material.node_tree.nodes[atmosphere_haze.VOLUME_NODE].inputs["Anisotropy"].default_value == 0.0
    assert domain.hide_select and atmosphere_haze.stored(bpy.context.scene)["height_falloff"] == 25.0
    again = haze(bridge)
    assert again["object"] == "Atmosphere" and len([obj for obj in bpy.data.objects if obj.name.startswith("Atmosphere")]) == 1
    assert bridge.ok("atmosphere", remove=True)["removed"]
    assert "Atmosphere" not in bpy.data.objects and atmosphere_haze.stored(bpy.context.scene) is None
    world = bridge.ok("atmosphere", visibility=200.0, domain="world")
    node = bpy.context.scene.world.node_tree.nodes[atmosphere_haze.VOLUME_NODE]
    close(node.inputs["Density"].default_value, -math.log(0.02) / 200.0, 1e-6)
    assert world["object"] is None and world["bounds"] is None
    bridge.ok("atmosphere", remove=True)
    assert atmosphere_haze.VOLUME_NODE not in bpy.context.scene.world.node_tree.nodes


def test_previews_show_depth_haze_and_leave_the_scene_alone(bridge):
    card_at(bridge, 20.0)
    haze(bridge, method="volume", airlight=[0.5, 0.5, 0.5])
    before = snapshot()
    shaded = bridge.ok("render_preview", resolution=64, samples=2, device="cpu")
    assert shaded["atmosphere"] == "depth haze"
    clay = bridge.ok("render_preview", resolution=64, samples=2, shading="clay", device="cpu")
    assert clay["atmosphere"] == "hidden"
    assert snapshot() == before and not bpy.data.objects["Atmosphere"].hide_render
    hazed = preview_contrast(bridge, shaded)
    bridge.ok("atmosphere", remove=True)
    clear = preview_contrast(bridge, bridge.ok("render_preview", resolution=64, samples=2, device="cpu"))
    print(f"preview contrast at 20 m: clear {clear:.3f}, depth haze {hazed:.3f}")
    assert hazed < 0.7 * clear, (hazed, clear)


def preview_contrast(bridge, result):
    path = os.path.join(bridge.workspace, "preview.png")
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(result["images"][0]["data"]))
    image = bpy.data.images.load(path, check_existing=False)
    try:
        width, height = image.size
        values = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(values)
    finally:
        bpy.data.images.remove(image)
    return halves_contrast(values.reshape(height, width, 4)[..., :3].mean(axis=-1))[0]


def channel_contrasts(bridge, name):
    image = channels(bridge, name)
    return [halves_contrast(image[..., index])[0] / WHITE for index in range(3)]


def test_the_scatter_tint_sets_the_extinction_of_each_colour_channel(bridge):
    distance = 20.0
    tint = [1.0, 0.5, 0.25]
    predicted = [math.exp(-SIGMA * distance * value) for value in tint]
    for method, samples, tolerance in (("depth", 4, 0.02), ("volume", 64, 0.15)):
        card_at(bridge, distance)
        haze(bridge, method=method, tint=tint, airlight=[0.5, 0.5, 0.5])
        bridge.ok("render_final", path=f"tint_{method}.exr", width=32, height=32, samples=samples, **EXACT)
        measured = channel_contrasts(bridge, f"tint_{method}.exr")
        print(f"tinted haze contrast by channel ({method}): {[round(v, 3) for v in measured]}, predicted {[round(v, 3) for v in predicted]}")
        for value, expected in zip(measured, predicted):
            assert abs(value - expected) <= tolerance * expected + 0.01, (method, measured, predicted)
        assert measured[0] < measured[1] < measured[2]


def test_depth_haze_works_for_a_camera_outside_the_box(bridge):
    distance = 20.0
    cases = (
        ("starts at 10 m", {"min": [-60.0, 10.0, -20.0], "max": [60.0, 70.0, 60.0]}, math.exp(-SIGMA * 10.0)),
        ("spans the card", {"min": [-60.0, 5.0, -20.0], "max": [60.0, 15.0, 60.0]}, math.exp(-SIGMA * 10.0)),
        ("behind the card", {"min": [-60.0, 30.0, -20.0], "max": [60.0, 70.0, 60.0]}, 1.0),
        ("beside the view", {"min": [100.0, -5.0, -20.0], "max": [160.0, 70.0, 60.0]}, 1.0),
    )
    for label, bounds, expected in cases:
        card_at(bridge, distance)
        haze(bridge, method="depth", airlight=[0.5, 0.5, 0.5], bounds=bounds)
        measured = contrast(bridge, "outside", 4)
        print(f"camera outside a box that {label}: contrast {measured:.4f}, predicted {expected:.4f}")
        close(measured, expected, 0.01)


def test_the_haze_box_stays_out_of_exports(bridge):
    card_at(bridge, 10.0)
    haze(bridge)
    assert bpy.data.objects["Atmosphere"].visible_get()
    listed = bridge.ok("export", path="scene.glb")["objects"]
    assert "Atmosphere" not in listed and listed
    hidden = bridge.ok("export", path="all.glb", include_hidden=True)["objects"]
    assert "Atmosphere" not in hidden
    assert "Atmosphere" not in bridge.ok("export", path="fbx.fbx")["objects"]
    bridge.ok("atmosphere", remove=True)
    assert bridge.ok("export", path="plain.glb")["objects"] == listed


def test_a_world_volume_that_was_there_stays_and_comes_back_on_remove(bridge):
    card_at(bridge, 10.0)
    tree = bpy.context.scene.world.node_tree
    output = next(node for node in tree.nodes if node.type == "OUTPUT_WORLD")
    own = tree.nodes.new("ShaderNodeVolumeAbsorption")
    own.name = "Own Fog"
    tree.links.new(own.outputs[0], output.inputs["Volume"])
    bridge.ok("atmosphere", visibility=200.0, domain="world")
    combined = tree.nodes[atmosphere_haze.ADD_NODE]
    assert output.inputs["Volume"].links[0].from_node == combined
    assert {link.from_node.name for link in combined.inputs[0].links + combined.inputs[1].links} == {"Own Fog", atmosphere_haze.VOLUME_NODE}
    bridge.ok("atmosphere", visibility=100.0, domain="world")
    assert len([node for node in tree.nodes if node.name.startswith(atmosphere_haze.ADD_NODE)]) == 1
    assert bridge.ok("atmosphere", remove=True)["removed"]
    assert output.inputs["Volume"].links[0].from_node.name == "Own Fog"
    assert atmosphere_haze.VOLUME_NODE not in tree.nodes and atmosphere_haze.ADD_NODE not in tree.nodes
    assert tree.nodes["Own Fog"].outputs[0].links[0].to_node == output
    tree.nodes.remove(own)


def test_volume_haze_with_passes_keeps_the_haze_in_the_beauty_and_bounds_the_pass_render(bridge):
    card_at(bridge, 20.0)
    haze(bridge, method="volume", airlight=[0.5, 0.5, 0.5])
    options = dict(path="plain.exr", width=32, height=32, samples=48, **EXACT)
    bridge.ok("render_final", **options)
    with Recorded() as recorded:
        result = bridge.ok("render_final", **dict(options, path="with_passes.exr", passes=["depth", "normal"]))
    plain = halves_contrast(linear(bridge, "plain.exr"))[0] / WHITE
    passed = halves_contrast(linear(bridge, "with_passes.exr"))[0] / WHITE
    expected = math.exp(-SIGMA * 20.0)
    print(f"volume haze contrast: plain {plain:.3f}, with passes {passed:.3f}, predicted {expected:.3f}")
    assert abs(plain - expected) < 0.15 * expected and abs(passed - plain) < 0.1 * expected
    beauty, surfaces = recorded.calls
    assert beauty["time_limit"] == 600.0 and surfaces["time_limit"] == render_outputs.SURFACE_SECONDS
    assert not surfaces["denoising"] and not surfaces["adaptive"] and surfaces["samples"] <= render_outputs.SURFACE_SAMPLES
    depth = result["passes"]["depth"]["range"]
    close(depth[0], 20.0, 0.1)


def test_the_sky_estimate_reads_the_upper_hemisphere_without_copying_the_image(bridge):
    width, height = 64, 32
    rows = np.linspace(0.1, 4.0, height)[:, None, None]
    columns = np.linspace(0.5, 1.5, width)[None, :, None]
    pixels = np.concatenate([rows * columns * np.array([1.0, 0.5, 0.25]), np.ones((height, width, 1))], axis=-1).astype(np.float32)
    image = bpy.data.images.new("sky_test", width, height, alpha=True, float_buffer=True)
    try:
        image.pixels.foreach_set(pixels.ravel())
        count = len(bpy.data.images)
        measured = atmosphere_haze.sky_radiance(image)
        assert len(bpy.data.images) == count
    finally:
        bpy.data.images.remove(image)
    upper = pixels[height // 2 :, :, :3].astype(np.float64)
    latitude = (np.arange(height // 2) + 0.5) / (height // 2) * (math.pi / 2.0)
    weights = np.cos(latitude)
    expected = (upper.mean(axis=1) * weights[:, None]).sum(axis=0) / weights.sum()
    close(measured.tolist(), expected.tolist(), 1e-5)


def test_atmosphere_refuses_bad_settings(bridge):
    card_at(bridge, 10.0)
    bridge.refuse("atmosphere", "bad_args")
    bridge.refuse("atmosphere", "bad_args", visibility=100.0, domain="world", height_falloff=10.0)
    bridge.refuse("atmosphere", "bad_args", visibility=100.0, bounds={"min": [0.0, 0.0, 0.0], "max": [1.0, -1.0, 1.0]})
    bridge.refuse("atmosphere", "bad_args", visibility=100.0, airlight=[1.0, 1.0, 1.0], preview="volume")
    bridge.refuse("atmosphere", "bad_args", remove=True, visibility=100.0)
    bridge.refuse("atmosphere", "bad_args", visibility=0.0)


run(globals())
