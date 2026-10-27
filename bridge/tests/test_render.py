import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run, snapshot

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ALL_VIEWS = ["front", "back", "left", "right", "top", "three-quarter"]


def pixels(image):
    data = base64.b64decode(image["data"])
    assert data[:8] == PNG_SIGNATURE
    path = os.path.join(tempfile.mkdtemp(prefix="blendworks-png-"), "view.png")
    with open(path, "wb") as handle:
        handle.write(data)
    loaded = bpy.data.images.load(path)
    try:
        width, height = loaded.size
        values = list(loaded.pixels)
    finally:
        bpy.data.images.remove(loaded)
    return width, height, values


def brightness(values, width, x, y):
    start = (y * width + x) * 4
    return sum(values[start : start + 3]) / 3


def crate(bridge):
    bridge.ok("add_primitive", type="cube", name="Crate", size=1.0)
    bridge.ok("add_material", name="Wood", base_color=[0.8, 0.5, 0.2])
    bridge.ok("assign_material", name="Crate", material="Wood")


def test_turntable_views_are_fitted_pngs(bridge):
    crate(bridge)
    before = snapshot()
    engine = bpy.context.scene.render.engine
    result = bridge.ok("render_preview", views=ALL_VIEWS, resolution=96, samples=4)
    assert result["engine"] == "cycles" and result["seed"] == 0
    assert [image["view"] for image in result["images"]] == ALL_VIEWS
    for image in result["images"]:
        assert image["mimeType"] == "image/png" and image["width"] == 96 and image["height"] == 96
        width, height, values = pixels(image)
        assert (width, height) == (96, 96)
        centre = brightness(values, width, 48, 48)
        corner = brightness(values, width, 2, 2)
        assert abs(centre - corner) > 0.05, (image["view"], centre, corner)
    assert snapshot() == before
    assert bpy.context.scene.render.engine == engine
    assert not any(obj.name.startswith("blendworks_preview_") for obj in bpy.data.objects)


def test_render_is_deterministic(bridge):
    crate(bridge)
    first = bridge.ok("render_preview", views=["three-quarter"], resolution=64, samples=4, device="cpu")
    second = bridge.ok("render_preview", views=["three-quarter"], resolution=64, samples=4, device="cpu")
    assert first["images"][0]["data"] == second["images"][0]["data"]


def test_active_and_named_cameras(bridge):
    crate(bridge)
    bridge.ok("add_camera", name="Main", location=[3.0, -3.0, 2.0], target=[0.0, 0.0, 0.0])
    bridge.ok("add_camera", name="Side", location=[4.0, 0.0, 0.0], target=[0.0, 0.0, 0.0], active=False)
    active = bridge.ok("render_preview", resolution=64, samples=2)
    assert [image["view"] for image in active["images"]] == ["Main"]
    named = bridge.ok("render_preview", camera="Side", resolution=64, samples=2)
    assert named["images"][0]["camera"] == "Side"
    assert active["images"][0]["data"] != named["images"][0]["data"]
    assert bpy.context.scene.camera.name == "Main"


def test_without_a_camera_it_renders_three_quarter(bridge):
    crate(bridge)
    result = bridge.ok("render_preview", resolution=64, samples=2)
    assert [image["view"] for image in result["images"]] == ["three-quarter"]


def test_render_preview_refuses_over_the_caps(bridge):
    crate(bridge)
    bridge.ok("add_light", type="point", name="Lamp")
    bridge.refuse("render_preview", "bad_args", resolution=1025)
    bridge.refuse("render_preview", "bad_args", samples=65)
    bridge.refuse("render_preview", "bad_args", views=["front", "front"])
    bridge.refuse("render_preview", "bad_args", views=["below"])
    bridge.refuse("render_preview", "bad_args", camera="Lamp")
    bridge.refuse("render_preview", "not_found", camera="Ghost")
    bridge.refuse("render_preview", "bad_args", camera="Lamp", views=["front"])
    bridge.refuse("render_preview", "bad_args", engine="eevee")


run(globals())
