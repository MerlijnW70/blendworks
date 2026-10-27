import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from texture_helpers import graph_signature, linked_from, principled, world_state

from blendworks_bridge.commands import procedural as procedural_command
from blendworks_bridge.nodes import find_socket
from blendworks_bridge.presets import PRESETS

SIZE = 16
BLUE = [0.05, 0.1, 0.6]
RED = [0.6, 0.05, 0.05]
FLAT_BLUE_WOOD = {"light_color": BLUE, "dark_color": BLUE}


def srgb(value):
    encoded = value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return round(encoded * 255) / 255


def baked_colour(bridge, name):
    bridge.ok("bake", names=[name], channels=["base_color"], size=SIZE, device="cpu", overwrite=True, samples={"base_color": 1})
    values = list(bpy.data.images[f"{name}_base_color"].pixels)
    count = len(values) // 4
    return [sum(values[channel::4]) / count for channel in range(3)]


def output_of(material):
    return next(node for node in material.node_tree.nodes if node.type == "OUTPUT_MATERIAL")


def test_every_preset_builds_a_bakeable_material(bridge):
    assert sorted(PRESETS) == ["bark", "brass", "concrete", "dirt", "fabric", "grass_ground", "leaf", "marble", "moss", "rust", "sand", "soil", "stone", "wood", "worn_metal"]
    for name in PRESETS:
        result = bridge.ok("material_procedural", name=f"M_{name}", **{name: {"seed": 7, "scale": 2.0}})
        assert result["created"] is True and result["preset"] == name and result["nodes"] > 8, result
        assert result["params"]["seed"] == 7 and result["params"]["coordinates"] == ("uv" if name == "leaf" else "object")
        material = bpy.data.materials[f"M_{name}"]
        shader = principled(material)
        assert linked_from(output_of(material).inputs["Surface"])[0] == shader
        for socket in ("Base Color", "Roughness"):
            assert shader.inputs[socket].is_linked, (name, socket)
        node, _ = linked_from(output_of(material).inputs["Displacement"])
        assert node.type == "DISPLACEMENT" and material.displacement_method == "BUMP"
        assert not any(node.type in ("SCRIPT", "TEX_IMAGE") for node in material.node_tree.nodes)


def test_preset_parameters_change_the_graph(bridge):
    bridge.ok("material_procedural", name="A", rust={"seed": 1})
    bridge.ok("material_procedural", name="B", rust={"seed": 2})
    assert graph_signature(bpy.data.materials["A"]) != graph_signature(bpy.data.materials["B"])
    result = bridge.ok("material_procedural", name="A", wood={"grain": "z", "bump": 0.0, "coordinates": "uv"})
    assert result["created"] is False and result["preset"] == "wood"
    material = bpy.data.materials["A"]
    assert not output_of(material).inputs["Displacement"].is_linked
    waves = [node for node in material.node_tree.nodes if node.type == "TEX_WAVE"]
    assert waves[0].rings_direction == "Z"
    assert any(node.type == "TEX_COORD" and node.outputs["UV"].is_linked for node in material.node_tree.nodes)


def test_material_procedural_refuses_bad_presets(bridge):
    bridge.ok("material_procedural", name="Kept", stone={})
    before = world_state()
    assert "knots" in bridge.refuse("material_procedural", "bad_args", name="Kept", wood={"knots": 3})
    assert "exactly one" in bridge.refuse("material_procedural", "bad_args", name="Kept", wood={}, rust={})
    bridge.refuse("material_procedural", "bad_args", name="Kept")
    bridge.refuse("material_procedural", "bad_args", name="Kept", granite={})
    bridge.refuse("material_procedural", "bad_args", name="Kept", wood={"scale": -1.0})
    bridge.refuse("material_procedural", "bad_args", name="Kept", wood={"grain": "w"})
    bridge.refuse("material_procedural", "bad_args", name="Kept", wood={"light_color": [2.0, 0.0, 0.0]})
    bridge.refuse("material_procedural", "bad_args", name="Kept", fabric={"threads": "many"})
    assert world_state() == before


def flat_sheet(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=2.0)
    bridge.ok("add_material", name="Paint", base_color=RED, roughness=0.4)
    bridge.ok("assign_material", name="Sheet", material="Paint")


def test_layer_amount_sets_how_much_overlay_shows(bridge):
    flat_sheet(bridge)
    close(baked_colour(bridge, "Sheet"), [srgb(value) for value in RED], 1.5 / 255)
    bridge.ok("material_layer", material="Paint", wood=FLAT_BLUE_WOOD, mask="noise", amount=0.0)
    close(baked_colour(bridge, "Sheet"), [srgb(value) for value in RED], 1.5 / 255)
    bridge.ok("material_layer", material="Paint", wood=FLAT_BLUE_WOOD, mask="noise", amount=1.0, softness=0.0)
    close(baked_colour(bridge, "Sheet"), [srgb(value) for value in BLUE], 1.5 / 255)


def test_layer_masks_by_vertex_colour(bridge):
    flat_sheet(bridge)
    bridge.ok("vertex_colors", name="Sheet", color=[1.0, 1.0, 1.0], layer="Wear")
    result = bridge.ok("material_layer", material="Paint", wood=FLAT_BLUE_WOOD, mask="vertex_color", layer="Wear", amount=0.5, softness=0.0)
    assert result["mask"] == "vertex_color"
    close(baked_colour(bridge, "Sheet"), [srgb(value) for value in BLUE], 1.5 / 255)
    bridge.ok("vertex_colors", name="Sheet", color=[0.0, 0.0, 0.0], layer="Wear")
    close(baked_colour(bridge, "Sheet"), [srgb(value) for value in RED], 1.5 / 255)


def test_layer_masks_edges_and_cavities(bridge):
    for index, (mask, extra) in enumerate((("edges", {"edge_source": "ao"}), ("edges", {"edge_source": "pointiness"}), ("cavity", {}), ("noise", {}))):
        name = f"Layered{index}"
        bridge.ok("material_procedural", name=name, worn_metal={})
        shader = principled(bpy.data.materials[name])
        original = linked_from(shader.inputs["Base Color"])[1]
        bridge.ok("material_layer", material=name, rust={"coverage": 0.7}, mask=mask, distance=0.05, **extra)
        mix, _ = linked_from(shader.inputs["Base Color"])
        assert mix.type == "MIX" and linked_from(find_socket(mix.inputs, "A_Color"))[1] == original
        nodes = {node.type for node in bpy.data.materials[name].node_tree.nodes}
        if mask == "edges" and extra["edge_source"] == "pointiness":
            assert "NEW_GEOMETRY" in nodes
        elif mask in ("edges", "cavity"):
            assert "AMBIENT_OCCLUSION" in nodes
        displacement, _ = linked_from(output_of(bpy.data.materials[name]).inputs["Displacement"])
        assert displacement.type == "VECT_MATH"


def test_failed_layer_restores_the_material(bridge):
    flat_sheet(bridge)
    bridge.ok("material_layer", material="Paint", rust={}, mask="noise")
    before = world_state()
    original = procedural_command.mask_value

    def broken(graph, args):
        original(graph, args)
        raise RuntimeError("injected layer failure")

    procedural_command.mask_value = broken
    try:
        bridge.refuse("material_layer", "failed", material="Paint", dirt={}, mask="cavity")
        bridge.refuse("material_layer", "failed", material="Paint", wood={}, mask="edges")
    finally:
        procedural_command.mask_value = original
    assert world_state() == before


def test_material_layer_refusals_leave_the_material(bridge):
    flat_sheet(bridge)
    bridge.ok("material_pbr", name="Empty", base_color=bridge.ok("image_new", name="Px", width=4, height=4)["name"])
    bpy.data.materials["Empty"].node_tree.nodes.remove(principled(bpy.data.materials["Empty"]))
    before = world_state()
    bridge.refuse("material_layer", "not_found", material="Ghost", dirt={})
    bridge.refuse("material_layer", "bad_args", material="Paint")
    bridge.refuse("material_layer", "bad_args", material="Paint", dirt={"depth": 2})
    assert "Wear" in bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="vertex_color", layer="Wear")
    bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="vertex_color")
    bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="noise", layer="Wear")
    bridge.refuse("material_layer", "bad_args", material="Paint", dirt={}, mask="scratches")
    assert "Principled" in bridge.refuse("material_layer", "bad_args", material="Empty", dirt={})
    assert world_state() == before


if __name__ == "__main__":
    run(globals())
