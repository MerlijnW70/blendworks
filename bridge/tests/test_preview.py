import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from fingerprint import differences, fingerprint
from harness import close, run

SHADINGS = ["shaded", "clay", "wireframe", "normals", "uv_checker", "material_id"]
OUTPUT = os.environ.get("BLENDWORKS_PREVIEW_OUT")


def decoded(image, name):
    data = base64.b64decode(image["data"])
    folder = OUTPUT or tempfile.mkdtemp(prefix="blendworks-preview-")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "wb") as handle:
        handle.write(data)
    loaded = bpy.data.images.load(path)
    try:
        values = list(loaded.pixels)
        size = tuple(loaded.size)
    finally:
        bpy.data.images.remove(loaded)
    if OUTPUT is None:
        os.remove(path)
    return data, size, values


def spread(values):
    grey = [sum(values[index : index + 3]) / 3 for index in range(0, len(values), 4)]
    return max(grey) - min(grey), len({round(value, 2) for value in grey})


LIT_SHADINGS = ["shaded", "clay", "uv_checker"]
ALL_VIEWS = ["front", "back", "left", "right", "top", "bottom", "three-quarter"]
FOCUS_DIRECTIONS = [[0.0, 0.0, -1.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, -1.0, -1.0], [1.0, 0.3, -0.2], [0.0, -1.0, 0.0]]
DARKEST_SHARE = 0.7
FLAT_TEXEL = (0.3, 0.3)


def centre_luminance(values, size):
    width, height = size
    margin_x, margin_y = width // 3, height // 3
    total = count = 0
    for y in range(margin_y, height - margin_y):
        for x in range(margin_x, width - margin_x):
            offset = (y * width + x) * 4
            total += 0.2126 * values[offset] + 0.7152 * values[offset + 1] + 0.0722 * values[offset + 2]
            count += 1
    return total / count


def grey_cube(bridge):
    bridge.ok("add_primitive", type="cube", name="Cube", size=1.0)
    bridge.ok("add_material", name="Grey", base_color=[0.5, 0.5, 0.5])
    bridge.ok("assign_material", name="Cube", material="Grey")
    bridge.ok("uv_smart_project", name="Cube")
    for layer in bpy.data.objects["Cube"].data.uv_layers:
        for loop_uv in layer.uv:
            loop_uv.vector = FLAT_TEXEL


def luminances(bridge, shading, **arguments):
    result = bridge.ok("render_preview", shading=shading, resolution=96, samples=4, device="cpu", **arguments)
    by_view = {}
    for image in result["images"]:
        _, size, values = decoded(image, f"cube-{shading}-{image['view']}.png")
        by_view[image["view"]] = centre_luminance(values, size)
    return by_view


def prop(bridge):
    bridge.ok("add_primitive", type="cube", name="Body", size=1.0)
    bridge.ok("add_primitive", type="cylinder", name="Knob", radius=0.15, depth=0.3, segments=16, location=[0.0, -0.6, 0.2], rotation=[90.0, 0.0, 0.0])
    bridge.ok("add_material", name="Red", base_color=[0.8, 0.1, 0.1])
    bridge.ok("add_material", name="Brass", base_color=[0.8, 0.6, 0.2], metallic=1.0)
    bridge.ok("assign_material", name="Body", material="Red")
    bridge.ok("assign_material", name="Knob", material="Brass")
    bridge.ok("uv_smart_project", name="Body")


def test_every_shading_renders_a_close_up_with_detail(bridge):
    prop(bridge)
    before = fingerprint()
    for shading in SHADINGS:
        result = bridge.ok("render_preview", focus={"object": "Knob", "width": 0.6}, shading=shading, resolution=96, samples=2, device="cpu")
        assert result["shading"] == shading
        assert result["device"]["device"] == "cpu" and result["device_label"] == "cpu"
        assert result["focus"]["width"] == 0.6
        _, size, values = decoded(result["images"][0], f"knob-{shading}.png")
        contrast, levels = spread(values)
        assert size == (96, 96) and contrast > 0.1 and levels > 5, (shading, contrast, levels)
    after = fingerprint()
    assert after == before, differences(before, after)
    assert not any(block.name.startswith("blendworks_preview_") for kind in ("objects", "materials", "meshes", "images", "node_groups") for block in getattr(bpy.data, kind))


def test_material_ids_come_with_a_legend_and_uv_checker_names_unwrapped_gaps(bridge):
    prop(bridge)
    ids = bridge.ok("render_preview", views=["front"], shading="material_id", resolution=64, samples=1, device="cpu")
    assert sorted(ids["material_colors"]) == ["Brass", "Red"]
    assert all(len(color) == 7 and color.startswith("#") for color in ids["material_colors"].values())
    assert bpy.data.objects["Body"].material_slots[0].material.name == "Red"
    checker = bridge.ok("render_preview", views=["front"], shading="uv_checker", resolution=64, samples=1, device="cpu")
    assert checker["objects_without_uv"] == [] or "Body" not in checker["objects_without_uv"]
    wire = bridge.ok("render_preview", views=["front"], shading="wireframe", resolution=64, samples=1, device="cpu")
    assert wire["wire_edges"] == len(bpy.data.objects["Body"].data.edges) + len(bpy.data.objects["Knob"].data.edges)


def test_focus_on_a_point_with_a_direction_and_the_bottom_view(bridge):
    prop(bridge)
    point = bridge.ok("render_preview", focus={"point": [0.0, -0.5, 0.2], "width": 0.4, "direction": [0.0, -1.0, 0.2]}, resolution=64, samples=2, device="cpu")
    assert [image["view"] for image in point["images"]] == ["focus"]
    close(point["focus"]["centre"], [0.0, -0.5, 0.2])
    bottom = bridge.ok("render_preview", views=["top", "bottom"], resolution=64, samples=2, device="cpu")
    assert [image["view"] for image in bottom["images"]] == ["top", "bottom"]
    top_data, _, _ = decoded(bottom["images"][0], "top.png")
    bottom_data, _, bottom_values = decoded(bottom["images"][1], "bottom.png")
    assert top_data != bottom_data and spread(bottom_values)[0] > 0.05
    around = bridge.ok("render_preview", focus={"object": "Body"}, views=["front", "left"], resolution=64, samples=1, device="cpu")
    assert [image["view"] for image in around["images"]] == ["front", "left"]


def test_every_turntable_view_is_lit_evenly(bridge):
    grey_cube(bridge)
    for shading in LIT_SHADINGS:
        by_view = luminances(bridge, shading, views=ALL_VIEWS)
        assert sorted(by_view) == sorted(ALL_VIEWS)
        assert min(by_view.values()) >= DARKEST_SHARE * max(by_view.values()), (shading, by_view)


def test_every_focus_direction_is_lit_evenly(bridge):
    grey_cube(bridge)
    for shading in LIT_SHADINGS:
        by_direction = []
        for direction in FOCUS_DIRECTIONS:
            by_direction.append(luminances(bridge, shading, focus={"object": "Cube", "direction": direction})["focus"])
        assert min(by_direction) >= DARKEST_SHARE * max(by_direction), (shading, by_direction)


def test_flat_shadings_do_not_depend_on_the_view(bridge):
    grey_cube(bridge)
    for shading in ("normals", "material_id"):
        by_view = luminances(bridge, shading, views=["front", "bottom", "top"])
        assert min(by_view.values()) > 0.0, (shading, by_view)
    ids = luminances(bridge, "material_id", views=ALL_VIEWS)
    assert max(ids.values()) - min(ids.values()) < 0.01, ids


def test_jpeg_output_is_smaller_than_png(bridge):
    prop(bridge)
    png = bridge.ok("render_preview", resolution=256, samples=4, device="cpu")
    jpeg = bridge.ok("render_preview", resolution=256, samples=4, device="cpu", format="jpeg", quality=70)
    image = jpeg["images"][0]
    assert image["mimeType"] == "image/jpeg"
    data, size, values = decoded(image, "view.jpg")
    assert data[:3] == b"\xff\xd8\xff" and size == (256, 256) and spread(values)[0] > 0.1
    assert len(image["data"]) < len(png["images"][0]["data"])


def test_the_device_follows_the_design_and_is_reported(bridge):
    prop(bridge)
    result = bridge.ok("render_preview", resolution=64, samples=1)
    assert result["device"]["device"] in ("cpu", "gpu")
    assert result["device_label"].startswith(result["device"]["device"])
    previous = os.environ.get("BLENDWORKS_DEVICE")
    os.environ["BLENDWORKS_DEVICE"] = "cpu"
    try:
        assert bridge.ok("render_preview", resolution=64, samples=1)["device"] == {"device": "cpu", "backend": None, "names": [], "fallback": None}
        os.environ["BLENDWORKS_DEVICE"] = "quantum"
        bridge.refuse("render_preview", "bad_args", resolution=64, samples=1)
    finally:
        if previous is None:
            os.environ.pop("BLENDWORKS_DEVICE", None)
        else:
            os.environ["BLENDWORKS_DEVICE"] = previous


def test_preview_refusals(bridge):
    prop(bridge)
    bridge.ok("add_camera", name="Cam", location=[3.0, -3.0, 2.0], target=[0.0, 0.0, 0.0])
    bridge.refuse("render_preview", "bad_args", focus={})
    bridge.refuse("render_preview", "bad_args", focus={"object": "Body", "point": [0.0, 0.0, 0.0]})
    bridge.refuse("render_preview", "bad_args", focus={"point": [0.0, 0.0, 0.0], "direction": [0.0, 0.0, 0.0]})
    bridge.refuse("render_preview", "bad_args", focus={"point": [0.0, 0.0, 0.0], "direction": [1.0, 0.0, 0.0]}, views=["front"])
    bridge.refuse("render_preview", "bad_args", focus={"object": "Body"}, camera="Cam")
    bridge.refuse("render_preview", "bad_args", focus={"point": [0.0, 0.0, 0.0], "width": 0.0})
    bridge.refuse("render_preview", "bad_args", focus={"object": "Body", "zoom": 2})
    bridge.refuse("render_preview", "not_found", focus={"object": "Ghost"})
    bridge.refuse("render_preview", "bad_args", shading="xray")
    bridge.refuse("render_preview", "bad_args", quality=50)
    bridge.refuse("render_preview", "bad_args", format="gif")
    bridge.refuse("render_preview", "bad_args", device="tpu")


run(globals())
