import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import close, run
from blendworks_bridge import leaf_optics
from natural_stats import baked_pixels, hard_edge_share, luminance_of, to_linear, variation
from texture_helpers import linked_from, principled, world_state

NATURAL = ["bark", "moss", "leaf", "soil", "sand", "grass_ground"]
SIZE = 16
RED = [0.6, 0.05, 0.05]
BLUE = [0.05, 0.1, 0.6]
WHITE = [1.0, 1.0, 1.0]
FLAT_BLUE_WOOD = {"light_color": BLUE, "dark_color": BLUE}
FLAT_WHITE_WOOD = {"light_color": WHITE, "dark_color": WHITE}
PATCH_PIXELS = 256
MINIMUM_VARIATION = 0.15
HARD_SHARE_MINIMUM = 0.4
SOFT_SHARE_MAXIMUM = 0.12
BOUNDARY_PIXELS_MINIMUM = 2000


def srgb(value):
    encoded = value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return round(encoded * 255) / 255


def bake(bridge, name, size, channel="base_color"):
    bridge.ok("bake", names=[name], channels=[channel], size=size, device="cpu", overwrite=True, samples={channel: 1}, time_limit=600.0)
    return f"{name}_{channel}"


def mean_colour(bridge, name):
    image = bake(bridge, name, SIZE)
    return list(baked_pixels(image, SIZE).reshape(-1, 3).mean(axis=0))


def expected(colour):
    return [srgb(value) for value in colour]


def paint_plane(bridge, name="Sheet", material="Paint", **transform):
    bridge.ok("add_primitive", type="plane", name=name, size=2.0)
    if transform:
        bridge.ok("transform", name=name, **transform)
    bridge.ok("add_material", name=material, base_color=RED, roughness=0.4)
    bridge.ok("assign_material", name=name, material=material)


def layer(bridge, **args):
    return bridge.ok("material_layer", material="Paint", wood=FLAT_BLUE_WOOD, **args)


def test_every_natural_preset_builds_and_bakes(bridge):
    for name in NATURAL:
        result = bridge.ok("material_procedural", name=f"M_{name}", **{name: {"seed": 3}})
        assert result["preset"] == name and result["nodes"] > 12, result
        shader = principled(bpy.data.materials[f"M_{name}"])
        assert shader.inputs["Base Color"].is_linked and shader.inputs["Roughness"].is_linked, name
        bridge.ok("add_primitive", type="plane", name=f"P_{name}", size=1.0)
        bridge.ok("assign_material", name=f"P_{name}", material=f"M_{name}")
        bridge.ok("bake", names=[f"P_{name}"], channels=["base_color", "roughness"], size=32, device="cpu", overwrite=True, samples={"base_color": 1, "roughness": 1}, time_limit=600.0)
        for channel in ("base_color", "roughness"):
            pixels = numpy.array(bpy.data.images[f"P_{name}_{channel}"].pixels[:])
            assert numpy.isfinite(pixels).all() and pixels.std() > 0.002, (name, channel)


def test_natural_presets_vary_like_scans_over_one_metre(bridge):
    for name in NATURAL:
        params = {"grain": "y"} if name == "bark" else {}
        bridge.ok("material_procedural", name=f"M_{name}", **{name: params})
        bridge.ok("add_primitive", type="plane", name=f"P_{name}", size=1.0)
        bridge.ok("assign_material", name=f"P_{name}", material=f"M_{name}")
        values = luminance_of(baked_pixels(bake(bridge, f"P_{name}", PATCH_PIXELS), PATCH_PIXELS))
        assert variation(values) >= MINIMUM_VARIATION, (name, variation(values))


def test_leaf_alpha_cutout_and_translucency_reach_the_shader(bridge):
    bridge.ok("material_procedural", name="Plain", leaf={})
    shader = principled(bpy.data.materials["Plain"])
    assert not shader.inputs["Alpha"].is_linked and shader.inputs["Alpha"].default_value == 1.0
    assert shader.inputs["Transmission Weight"].default_value == 0.0 and shader.inputs["Subsurface Weight"].default_value == 0.0
    plain = bpy.data.materials["Plain"].node_tree.nodes
    close(plain[leaf_optics.MIX_NODE].inputs["Fac"].default_value, leaf_optics.mix_factor("broadleaf"), 1e-5)
    bridge.ok("material_procedural", name="Cut", leaf={"cutout": True, "alpha": 0.8, "translucency": 0.6})
    material = bpy.data.materials["Cut"]
    shader = principled(material)
    assert shader.inputs["Alpha"].is_linked
    close(material.node_tree.nodes[leaf_optics.MIX_NODE].inputs["Fac"].default_value, leaf_optics.mix_factor("broadleaf", 0.6), 1e-5)
    bridge.ok("material_procedural", name="Faint", leaf={"alpha": 0.5})
    assert abs(principled(bpy.data.materials["Faint"]).inputs["Alpha"].default_value - 0.5) < 1e-6


def test_slope_mask_follows_the_world_angle(bridge):
    paint_plane(bridge)
    layer(bridge, mask="slope", angle_min=30.0)
    close(mean_colour(bridge, "Sheet"), expected(RED), 1.5 / 255)
    bridge.ok("transform", name="Sheet", rotation=[60.0, 0.0, 0.0])
    close(mean_colour(bridge, "Sheet"), expected(BLUE), 1.5 / 255)
    bridge.ok("transform", name="Sheet", rotation=[15.0, 0.0, 0.0])
    close(mean_colour(bridge, "Sheet"), expected(RED), 1.5 / 255)


def test_slope_angle_max_covers_flat_ground_and_not_steep_walls(bridge):
    paint_plane(bridge)
    layer(bridge, mask="slope", angle_max=20.0)
    close(mean_colour(bridge, "Sheet"), expected(BLUE), 1.5 / 255)
    bridge.ok("transform", name="Sheet", rotation=[60.0, 0.0, 0.0])
    close(mean_colour(bridge, "Sheet"), expected(RED), 1.5 / 255)


def test_height_mask_is_zero_below_z_min_and_one_above_the_soft_edge(bridge):
    paint_plane(bridge)
    layer(bridge, mask="height", z_min=1.0, z_edge=0.5)
    for z, colour in ((-2.0, RED), (0.9, RED), (1.6, BLUE), (5.0, BLUE)):
        bridge.ok("transform", name="Sheet", location=[0.0, 0.0, z])
        close(mean_colour(bridge, "Sheet"), expected(colour), 1.5 / 255)
    bridge.ok("transform", name="Sheet", location=[0.0, 0.0, 1.25])
    middle = mean_colour(bridge, "Sheet")
    assert abs(middle[0] - expected(RED)[0]) > 0.1 and abs(middle[2] - expected(BLUE)[2]) > 0.1, middle


def test_height_mask_with_z_max_covers_low_ground(bridge):
    paint_plane(bridge)
    layer(bridge, mask="height", z_min=-1.0, z_max=2.0, z_edge=0.5)
    for z, colour in ((0.5, BLUE), (2.5, RED), (-3.0, RED)):
        bridge.ok("transform", name="Sheet", location=[0.0, 0.0, z])
        close(mean_colour(bridge, "Sheet"), expected(colour), 1.5 / 255)


def test_up_facing_mask_is_one_up_zero_down_and_strength_sets_the_reach(bridge):
    paint_plane(bridge)
    layer(bridge, mask="up_facing")
    close(mean_colour(bridge, "Sheet"), expected(BLUE), 1.5 / 255)
    bridge.ok("transform", name="Sheet", rotation=[180.0, 0.0, 0.0])
    close(mean_colour(bridge, "Sheet"), expected(RED), 1.5 / 255)
    bridge.ok("transform", name="Sheet", rotation=[60.0, 0.0, 0.0])
    close(mean_colour(bridge, "Sheet"), expected(RED), 1.5 / 255)
    bridge.ok("material_layer", material="Paint", wood=FLAT_BLUE_WOOD, mask="up_facing", strength=1.0)
    tilted = mean_colour(bridge, "Sheet")
    assert all(abs(a - b) > 0.05 for a, b in zip(tilted, expected(RED))), tilted


def test_masks_combine_with_each_other_and_with_the_old_ones(bridge):
    cases = (
        (dict(with_masks=["height"], z_min=5.0), RED),
        (dict(with_masks=["height"], z_min=5.0, combine="any"), BLUE),
        (dict(with_masks=["noise"], amount=1.0, softness=0.0), BLUE),
        (dict(with_masks=["noise"], amount=0.0, softness=0.0), RED),
    )
    for index, (extra, colour) in enumerate(cases):
        paint_plane(bridge, f"Sheet{index}", f"Paint{index}", rotation=[60.0, 0.0, 0.0])
        bridge.ok("material_layer", material=f"Paint{index}", wood=FLAT_BLUE_WOOD, mask="slope", angle_min=30.0, **extra)
        close(mean_colour(bridge, f"Sheet{index}"), expected(colour), 1.5 / 255)


def test_attribute_mask_equals_the_heightfield_attribute(bridge):
    resolution = 17
    result = bridge.ok("heightfield", name="Tile", size=[10.0, 10.0], resolution=resolution, height=3.0, base_height=1.0, scale=30.0, octaves=2, seed=5, attributes=["height", "slope"])
    size = 64
    for attribute in ("height", "slope"):
        low, high = result["attributes"][attribute]
        assert high - low > 0.1, (attribute, low, high)
        bridge.ok("add_material", name=f"Black_{attribute}", base_color=[0.0, 0.0, 0.0])
        bridge.ok("assign_material", name="Tile", material=f"Black_{attribute}")
        bridge.ok("material_layer", material=f"Black_{attribute}", wood={"bump": 0.0, **FLAT_WHITE_WOOD}, mask="attribute", attribute=attribute, value_min=low, value_max=high)
        baked = to_linear(baked_pixels(bake(bridge, "Tile", size), size)[..., 0])
        values = numpy.empty(resolution * resolution)
        bpy.data.objects["Tile"].data.attributes[attribute].data.foreach_get("value", values)
        grid = values.reshape(resolution, resolution)
        centres = (numpy.arange(size) + 0.5) / size * (resolution - 1)
        rows = numpy.clip(numpy.floor(centres).astype(int), 0, resolution - 2)
        along = centres - rows
        interpolated = (
            grid[rows][:, rows] * (1 - along)[:, None] * (1 - along)[None, :]
            + grid[rows + 1][:, rows] * along[:, None] * (1 - along)[None, :]
            + grid[rows][:, rows + 1] * (1 - along)[:, None] * along[None, :]
            + grid[rows + 1][:, rows + 1] * along[:, None] * along[None, :]
        )
        wanted = (interpolated - low) / (high - low)
        inner = slice(6, size - 6)
        assert numpy.abs(baked[inner, inner] - wanted[inner, inner]).max() < 0.03, attribute
        assert baked[inner, inner].std() > 0.05, attribute


def test_mask_arguments_are_checked_and_leave_the_material(bridge):
    paint_plane(bridge)
    layer(bridge, mask="slope", angle_min=30.0)
    before = world_state()
    assert "angle_min" in bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="slope")
    assert "z_min" in bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="height")
    assert "attribute" in bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="attribute")
    assert "slope" in bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="noise", angle_min=10.0)
    assert "below" in bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="slope", angle_min=50.0, angle_max=40.0)
    bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="up_facing", with_masks=["height"])
    bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="slope", angle_min=10.0, strength=0.5)
    bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="slope", angle_min=500.0)
    assert world_state() == before


def stone_edge_statistic(bridge, **stone):
    bridge.ok("add_primitive", type="sphere", name="Boulder", radius=0.5, segments=64, rings=32)
    bridge.ok("material_procedural", name="Rock", stone=dict(cracks=False, **stone))
    bridge.ok("assign_material", name="Boulder", material="Rock")
    values = luminance_of(baked_pixels(bake(bridge, "Boulder", 512), 512))[176:336]
    return hard_edge_share(values)


def test_stone_patches_have_soft_boundaries_by_default_and_hard_ones_on_request(bridge):
    soft, soft_pixels = stone_edge_statistic(bridge)
    bridge.ok("delete", names=["Boulder"])
    hard, hard_pixels = stone_edge_statistic(bridge, hard_cells=True)
    assert soft_pixels >= BOUNDARY_PIXELS_MINIMUM and hard_pixels >= BOUNDARY_PIXELS_MINIMUM, (soft_pixels, hard_pixels)
    assert soft <= SOFT_SHARE_MAXIMUM, soft
    assert hard >= HARD_SHARE_MINIMUM, hard


if __name__ == "__main__":
    run(globals())
