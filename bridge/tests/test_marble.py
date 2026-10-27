import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run
from texture_helpers import principled
from texture_stats import luminance, vein_statistics

SIZE = 256
SCALE = 8.0


def baked_statistics(bridge, **preset):
    bridge.ok("material_procedural", name="Sample", **preset)
    bridge.ok("assign_material", name="Sheet", material="Sample")
    bridge.ok("bake", names=["Sheet"], channels=["base_color"], size=SIZE, overwrite=True, samples={"base_color": 1}, prefix="Swatch")
    return vein_statistics(luminance("Swatch_base_color", SIZE))


def sheet(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=0.5)
    bridge.ok("uv_smart_project", name="Sheet")


def test_a_marble_swatch_has_elongated_high_contrast_bands(bridge):
    sheet(bridge)
    for seed in (1, 2, 3):
        measured = baked_statistics(bridge, marble={"scale": SCALE, "seed": seed})
        assert measured["orientation"] >= 0.12, (seed, measured)
        assert measured["elongation"] >= 0.5, (seed, measured)
        assert measured["contrast"] >= 0.25, (seed, measured)
        assert 0.03 <= measured["dark_share"] <= 0.2, (seed, measured)


def test_voronoi_cracks_do_not_read_as_veins(bridge):
    sheet(bridge)
    for seed in (1, 2, 3):
        measured = baked_statistics(bridge, stone={"cell_scale": SCALE, "seed": seed})
        assert measured["orientation"] <= 0.08, (seed, measured)
        assert measured["contrast"] <= 0.25, (seed, measured)


def test_stone_veins_add_directional_structure_and_cracks_can_be_dropped(bridge):
    sheet(bridge)
    plain = baked_statistics(bridge, stone={"cracks": False, "scale": SCALE})
    veined = baked_statistics(bridge, stone={"cracks": False, "veins": {}, "scale": SCALE})
    assert plain["orientation"] < 0.05 and plain["dark_share"] == 0.0
    assert veined["orientation"] >= 0.06 and veined["orientation"] > 3 * plain["orientation"], (plain, veined)
    assert veined["dark_share"] > 0.02
    cracked = baked_statistics(bridge, stone={"scale": SCALE})
    assert cracked["dark_share"] > 0.03 and cracked["orientation"] < veined["orientation"]


def test_the_same_seed_bakes_the_same_swatch_and_another_seed_a_different_one(bridge):
    sheet(bridge)
    first = baked_statistics(bridge, marble={"scale": SCALE, "seed": 5})
    again = baked_statistics(bridge, marble={"scale": SCALE, "seed": 5})
    other = baked_statistics(bridge, marble={"scale": SCALE, "seed": 6})
    for key in first:
        assert abs(first[key] - again[key]) < 1e-6, key
    assert abs(first["orientation"] - other["orientation"]) > 1e-3


def test_vein_parameters_change_the_veins(bridge):
    sheet(bridge)
    thin = baked_statistics(bridge, marble={"scale": SCALE, "vein_width": 0.0})
    broad = baked_statistics(bridge, marble={"scale": SCALE, "vein_width": 0.6})
    assert broad["dark_share"] > 1.5 * thin["dark_share"]
    pale = baked_statistics(bridge, marble={"scale": SCALE, "vein_color": [0.5, 0.5, 0.5]})
    dark = baked_statistics(bridge, marble={"scale": SCALE, "vein_color": [0.0, 0.0, 0.0]})
    assert dark["contrast"] > pale["contrast"] + 0.1
    straight = baked_statistics(bridge, marble={"scale": SCALE, "turbulence": 0.0})
    wandering = baked_statistics(bridge, marble={"scale": SCALE, "turbulence": 1.0})
    assert abs(straight["orientation"] - wandering["orientation"]) > 0.02


def test_marble_graph_has_no_voronoi_and_stone_cracks_are_an_option(bridge):
    bridge.ok("material_procedural", name="Marble", marble={})
    kinds = {node.type for node in bpy.data.materials["Marble"].node_tree.nodes}
    assert "TEX_VORONOI" not in kinds and "TEX_NOISE" in kinds
    bridge.ok("material_procedural", name="Cracked", stone={})
    bridge.ok("material_procedural", name="Seamless", stone={"cracks": False})
    edge_cells = lambda name: [node for node in bpy.data.materials[name].node_tree.nodes if node.type == "TEX_VORONOI" and node.feature == "DISTANCE_TO_EDGE"]
    assert len(edge_cells("Cracked")) == 1 and edge_cells("Seamless") == []
    assert principled(bpy.data.materials["Marble"]).inputs["Roughness"].is_linked


def test_marble_parameters_are_typed_and_refuse_nonsense(bridge):
    result = bridge.ok("material_procedural", name="M", marble={"seed": 9, "vein_color": [0.1, 0.1, 0.1], "vein_width": 0.3, "turbulence": 0.9})
    assert result["preset"] == "marble" and result["params"]["vein_width"] == 0.3
    bridge.ok("material_layer", material="M", stone={"veins": {"width": 0.5}}, mask="noise", amount=0.5)
    bridge.refuse("material_procedural", "bad_args", name="M", marble={"vein_width": 2.0})
    bridge.refuse("material_procedural", "bad_args", name="M", marble={"vein_color": [0.1, 0.1]})
    bridge.refuse("material_procedural", "bad_args", name="M", marble={"cell_scale": 2.0})
    bridge.refuse("material_procedural", "bad_args", name="M", stone={"veins": {"colour": [0, 0, 0]}})
    bridge.refuse("material_procedural", "bad_args", name="M", stone={"cracks": "yes"})


run(globals())
