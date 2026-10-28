import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from texture_helpers import pixel

COLOURS = {"Red": [0.8, 0.1, 0.1], "Green": [0.1, 0.7, 0.1], "Blue": [0.1, 0.1, 0.8]}
SIZES = {"Red": 2048, "Green": 1024, "Blue": 512}
BYTES = {2048: 22_369_620, 1024: 5_592_404, 512: 1_398_100, 256: 349_524, 128: 87_380, 64: 21_844}
QUANTUM = 1.0 / 255
CHANNELS = ["base_color", "roughness"]
SAMPLES = {"base_color": 1, "roughness": 1}


def srgb(value):
    encoded = value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return round(encoded * 255) / 255


def three_materials(bridge, name="Trio"):
    vertices = [[x, y, 0.0] for x in range(4) for y in (0, 1)]
    faces = [[0, 2, 3, 1], [2, 4, 5, 3], [4, 6, 7, 5]]
    uv = [[0, 0], [1, 0], [1, 1], [0, 1]]
    for colour, values in COLOURS.items():
        bridge.ok("add_material", name=colour, base_color=values, roughness=0.5)
    bridge.ok(
        "mesh_from_data",
        name=name,
        vertices=vertices,
        faces=faces,
        uvs=uv * 3,
        material_indices=[0, 1, 2],
        materials=list(COLOURS),
    )


def rules():
    return [{"materials": [colour], "size": size} for colour, size in SIZES.items()]


def test_three_materials_bake_at_their_own_sizes_and_report_the_gpu_estimate(bridge):
    three_materials(bridge)
    result = bridge.ok("bake", names=["Trio"], channels=CHANNELS, size=64, atlas_sizes=rules(), samples=SAMPLES, prefix="Maps", rewire=True, time_limit=600.0)
    expected = {f"Maps_{colour}_{channel}": size for colour, size in SIZES.items() for channel in CHANNELS}
    assert sorted(result["images"]) == sorted(expected)
    for name, size in expected.items():
        assert list(bpy.data.images[name].size) == [size, size], name
    assert result["gpu_bytes"] == 2 * (BYTES[2048] + BYTES[1024] + BYTES[512]) == 58_720_248
    by_image = {entry["image"]: entry for entry in result["textures"]}
    for name, size in expected.items():
        assert by_image[name]["gpu_bytes"] == BYTES[size] and by_image[name]["size"] == [size, size]
        assert by_image[name]["material"] == name.split("_")[1] and by_image[name]["channel"] == name.split("_", 2)[2]
    assert result["materials"] == ["Red_baked", "Green_baked", "Blue_baked"] and result["material"] is None


def test_each_material_lands_in_its_own_image_and_the_object_keeps_its_slots(bridge):
    three_materials(bridge)
    bridge.ok("bake", names=["Trio"], channels=CHANNELS, size=64, atlas_sizes=rules(), samples=SAMPLES, prefix="Maps", rewire=True, time_limit=600.0)
    for colour, values in COLOURS.items():
        image = bpy.data.images[f"Maps_{colour}_base_color"]
        size = image.size[0]
        close(pixel(image, size // 2, size // 2)[:3], [srgb(value) for value in values], QUANTUM)
    slots = [slot.material.name for slot in bpy.data.objects["Trio"].material_slots]
    assert slots == ["Red_baked", "Green_baked", "Blue_baked"]
    assert [polygon.material_index for polygon in bpy.data.objects["Trio"].data.polygons] == [0, 1, 2]
    for colour, size in SIZES.items():
        material = bpy.data.materials[f"{colour}_baked"]
        textures = [node for node in material.node_tree.nodes if node.type == "TEX_IMAGE"]
        assert textures and all(node.image.size[0] == size for node in textures)
    original = bpy.data.materials["Red"].node_tree
    assert not any(node.type == "TEX_IMAGE" for node in original.nodes)


def test_a_channel_set_can_have_its_own_size(bridge):
    three_materials(bridge)
    result = bridge.ok(
        "bake",
        names=["Trio"],
        channels=["base_color", "roughness", "normal"],
        size=64,
        atlas_sizes=[{"channels": ["normal"], "size": 256}],
        samples={"base_color": 1, "roughness": 1, "normal": 1},
        prefix="Maps",
    )
    assert result["images"] == ["Maps_base_color", "Maps_roughness", "Maps_normal"]
    assert [list(bpy.data.images[name].size) for name in result["images"]] == [[64, 64], [64, 64], [256, 256]]
    assert result["gpu_bytes"] == 2 * BYTES[64] + BYTES[256]
    assert result["materials"] is None


def test_the_last_matching_rule_wins(bridge):
    three_materials(bridge)
    result = bridge.ok(
        "bake",
        names=["Trio"],
        channels=["base_color"],
        size=64,
        atlas_sizes=[{"materials": ["Red", "Green"], "size": 128}, {"materials": ["Green"], "size": 256}],
        samples={"base_color": 1},
    )
    sizes = {entry["material"]: entry["size"][0] for entry in result["textures"]}
    assert sizes == {"Red": 128, "Green": 256, "Blue": 64}
    assert result["gpu_bytes"] == BYTES[128] + BYTES[256] + BYTES[64]


def test_a_bake_without_atlas_sizes_still_reports_its_estimate(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=2.0)
    bridge.ok("add_material", name="Paint", base_color=[0.5, 0.5, 0.5])
    bridge.ok("assign_material", name="Sheet", material="Paint")
    result = bridge.ok("bake", names=["Sheet"], channels=["base_color"], size=64, samples={"base_color": 1}, device="cpu", time_limit=600.0)
    assert result["gpu_bytes"] == BYTES[64] and result["textures"][0]["material"] is None


def test_atlas_sizes_refuse_what_does_not_apply(bridge):
    three_materials(bridge)
    base = dict(names=["Trio"], channels=["base_color"], size=64)
    bridge.refuse("bake", "bad_args", **base, atlas_sizes=[{"size": 128}])
    bridge.refuse("bake", "bad_args", **base, atlas_sizes=[{"materials": ["Missing"], "size": 128}])
    bridge.refuse("bake", "bad_args", **base, atlas_sizes=[{"channels": ["normal"], "size": 128}])
    bridge.refuse("bake", "bad_args", **base, atlas_sizes=[{"materials": ["Red"], "size": 8}])
    bridge.refuse("bake", "bad_args", **base, atlas_sizes=[{"materials": ["Red"], "size": 8192}])
    bridge.refuse("bake", "bad_args", **base, atlas_sizes=[{"materials": ["Red"], "size": 128}], rewire=True, material="One")
    bridge.refuse("bake", "bad_args", **base, atlas_sizes=[])
    bridge.ok("add_primitive", type="cube", name="Bare", size=1.0)
    bridge.refuse("bake", "bad_args", names=["Bare"], channels=["base_color"], size=64, atlas_sizes=[{"materials": ["Red"], "size": 128}])


run(globals())
