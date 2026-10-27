import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from texture_helpers import pixel, world_state

SIZE = 32
QUANTUM = 1.0 / 255


def srgb(value):
    encoded = value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return round(encoded * 255) / 255


def mean_pixel(image):
    values = list(image.pixels)
    count = len(values) // 4
    return [sum(values[channel::4]) / count for channel in range(4)]


def flat_plane(bridge, name="Sheet", material="Paint", **values):
    bridge.ok("add_primitive", type="plane", name=name, size=2.0)
    bridge.ok("add_material", name=material, **values)
    bridge.ok("assign_material", name=name, material=material)


def test_bake_values_match_hand_worked_colours(bridge):
    flat_plane(bridge, base_color=[0.5, 0.25, 0.1], roughness=0.3, metallic=1.0, emission_color=[0.2, 0.4, 0.6], emission_strength=1.0)
    result = bridge.ok(
        "bake",
        names=["Sheet"],
        channels=["base_color", "roughness", "metallic", "emission", "normal"],
        size=SIZE,
        device="cpu",
        samples={"base_color": 1, "roughness": 1},
    )
    assert result["device"]["device"] == "cpu" and result["device_label"] == "cpu"
    assert result["images"] == ["Sheet_base_color", "Sheet_roughness", "Sheet_metallic", "Sheet_emission", "Sheet_normal"]
    assert [entry["samples"] for entry in result["channels"]] == [1, 1, 4, 4, 8]
    assert all(entry["seconds"] >= 0.0 for entry in result["channels"])
    expected = {
        "Sheet_base_color": [srgb(0.5), srgb(0.25), srgb(0.1)],
        "Sheet_roughness": [0.3, 0.3, 0.3],
        "Sheet_metallic": [1.0, 1.0, 1.0],
        "Sheet_emission": [srgb(0.2), srgb(0.4), srgb(0.6)],
        "Sheet_normal": [0.5, 0.5, 1.0],
    }
    for name, values in expected.items():
        image = bpy.data.images[name]
        assert image.colorspace_settings.name == ("sRGB" if name.endswith(("base_color", "emission")) else "Non-Color"), name
        assert image.packed_file is not None, name
        close(pixel(image, SIZE // 2, SIZE // 2)[:3], values, QUANTUM)
        close(mean_pixel(image)[:3], values, QUANTUM)
    paint = bpy.data.materials["Paint"].node_tree
    assert not any(node.type in ("EMISSION", "TEX_IMAGE") for node in paint.nodes)
    assert bpy.data.objects["Sheet"].material_slots[0].material.name == "Paint"


def test_bake_procedural_colour_and_float_data(bridge):
    bridge.ok("add_primitive", type="plane", name="Board", size=2.0)
    bridge.ok("material_procedural", name="Flat", wood={"light_color": [0.3, 0.3, 0.3], "dark_color": [0.3, 0.3, 0.3], "roughness": 0.5})
    bridge.ok("assign_material", name="Board", material="Flat")
    bridge.ok("bake", names=["Board"], channels=["base_color", "metallic"], size=SIZE, device="cpu", float_buffer=True, prefix="Flat")
    close(mean_pixel(bpy.data.images["Flat_base_color"])[:3], [srgb(0.3)] * 3, QUANTUM)
    metallic = bpy.data.images["Flat_metallic"]
    assert metallic.is_float and bpy.data.images["Flat_base_color"].is_float is False
    close(mean_pixel(metallic)[:3], [0.0, 0.0, 0.0], 1e-6)


def test_bake_ao_darkens_under_an_occluder(bridge):
    bridge.ok("add_primitive", type="plane", name="Floor", size=2.0)
    bridge.ok("add_primitive", type="cube", name="Lid", size=1.0)
    bridge.ok("transform", name="Lid", location=[0.0, 0.0, 0.55])
    bridge.ok("bake", names=["Floor"], channels=["ao"], size=SIZE, device="cpu", ao_distance=1.0, samples={"ao": 32})
    image = bpy.data.images["Floor_ao"]
    assert pixel(image, SIZE // 2, SIZE // 2)[0] < 0.4
    assert pixel(image, 1, 1)[0] > pixel(image, SIZE // 2, SIZE // 2)[0] + 0.3
    assert len(bpy.data.objects["Floor"].material_slots) == 0
    assert "blendworks_bake_target" not in bpy.data.materials


def test_bake_overwrite_and_rewire(bridge):
    flat_plane(bridge, base_color=[1.0, 0.0, 0.0], roughness=0.8)
    bridge.ok("bake", names=["Sheet"], channels=["base_color"], size=SIZE, device="cpu")
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["base_color"], size=SIZE, device="cpu")
    bridge.ok("add_material", name="Paint", base_color=[0.0, 0.0, 1.0])
    result = bridge.ok("bake", names=["Sheet"], channels=["base_color", "roughness"], size=SIZE, device="cpu", overwrite=True, rewire=True)
    assert result["material"] == "Sheet_baked"
    assert pixel(bpy.data.images["Sheet_base_color"], 5, 5)[2] > 0.9
    assert "Sheet_base_color.001" not in bpy.data.images
    baked = bpy.data.materials["Sheet_baked"]
    assert [slot.material for slot in bpy.data.objects["Sheet"].material_slots] == [baked]
    images = {node.image.name for node in baked.node_tree.nodes if node.type == "TEX_IMAGE"}
    assert images == {"Sheet_base_color", "Sheet_roughness"}
    assert "Paint" in bpy.data.materials


def test_bake_shares_one_atlas_between_objects(bridge):
    flat_plane(bridge, name="Left", material="Red", base_color=[1.0, 0.0, 0.0])
    flat_plane(bridge, name="Right", material="Blue", base_color=[0.0, 0.0, 1.0])
    bridge.ok("transform", name="Right", location=[3.0, 0.0, 0.0])
    bridge.ok("uv_pack", names=["Left", "Right"], margin=0.02, rotate=False)
    result = bridge.ok("bake", names=["Left", "Right"], channels=["base_color"], size=64, device="cpu", prefix="Atlas", rewire=True)
    assert result["names"] == ["Left", "Right"] and result["images"] == ["Atlas_base_color"]
    image = bpy.data.images["Atlas_base_color"]
    for name, red, blue in (("Left", 1.0, 0.0), ("Right", 0.0, 1.0)):
        mesh = bpy.data.objects[name].data
        uvs = [item.uv for item in mesh.uv_layers.active.data]
        centre = [sum(uv[axis] for uv in uvs) / len(uvs) for axis in (0, 1)]
        close([pixel(image, int(centre[0] * 64), int(centre[1] * 64))[index] for index in (0, 2)], [red, blue], QUANTUM)
        assert [slot.material.name for slot in bpy.data.objects[name].material_slots] == ["Atlas_baked"]


def test_bake_refusals_leave_the_scene(bridge):
    flat_plane(bridge)
    bridge.ok("add_primitive", type="cube", name="Bare")
    bridge.ok("mesh_from_data", name="NoUV", vertices=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], faces=[[0, 1, 2]])
    bridge.ok("add_primitive", type="cube", name="Box")
    bpy.data.materials["Paint"].node_tree.nodes.remove(bpy.data.materials["Paint"].node_tree.nodes["Principled BSDF"])
    bridge.ok("assign_material", name="Box", material="Paint")
    before = world_state()
    bridge.refuse("bake", "bad_args", names=["NoUV"], channels=["normal"], size=SIZE)
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["specular"], size=SIZE)
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal", "normal"], size=SIZE)
    bridge.refuse("bake", "bad_args", names=["Sheet"], size=8192)
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal"], samples={"ao": 4})
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal"], samples={"gloss": 4})
    bridge.refuse("bake", "bad_args", names=["Sheet", "Bare"], source=["Box"], channels=["normal"])
    bridge.refuse("bake", "bad_args", names=["Sheet"], cage_extrusion=0.2, channels=["normal"])
    bridge.refuse("bake", "bad_args", names=["Bare"], channels=["base_color"])
    assert "Principled" in bridge.refuse("bake", "bad_args", names=["Box"], channels=["roughness"])
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal"], time_limit=601.0)
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal"], device="tpu")
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal"], uv_map="Missing")
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal"], material="Named")
    bridge.refuse("bake", "not_found", names=["Ghost"], channels=["normal"])
    bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal"], prefix="x" * 60)
    assert world_state() == before


def test_bake_selected_to_active_catches_bevels(bridge):
    bridge.ok("add_primitive", type="cube", name="High", size=1.0)
    bridge.ok("bevel", name="High", width=0.12, segments=6)
    bridge.ok("shade_smooth", name="High")
    bridge.ok("add_primitive", type="cube", name="Low", size=1.0)
    bridge.ok("uv_smart_project", name="Low", island_margin=0.05)
    size = 128
    result = bridge.ok("bake", names=["Low"], source=["High"], channels=["normal"], size=size, device="cpu", cage_extrusion=0.1, margin=4)
    assert result["source"] == ["High"] and result["names"] == ["Low"]
    image = bpy.data.images["Low_normal"]
    low = bpy.data.objects["Low"].data
    layer = low.uv_layers.active
    deviations = []
    for polygon in low.polygons:
        uvs = [layer.data[index].uv for index in polygon.loop_indices]
        centre = [sum(uv[axis] for uv in uvs) / len(uvs) for axis in (0, 1)]
        close(pixel(image, int(centre[0] * size), int(centre[1] * size))[:3], [0.5, 0.5, 1.0], 0.03)
        for corner in uvs:
            edge = [centre[axis] + (corner[axis] - centre[axis]) * 0.92 for axis in (0, 1)]
            value = pixel(image, int(edge[0] * size), int(edge[1] * size))
            deviations.append(max(abs(value[0] - 0.5), abs(value[1] - 0.5)))
    assert min(deviations) > 0.08, deviations
    assert len(low.materials) == 0


if __name__ == "__main__":
    run(globals())
