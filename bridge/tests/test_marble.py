import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import run
from texture_helpers import principled
from marble_stats import vein_profile
from texture_stats import luminance, vein_statistics

SIZE = 256
SCALE = 8.0
SLAB_METRES = 0.5
SLAB_PIXELS = 512
EDGE_CROP = 8
SOFT_VEINS = 4.0
HARD_EDGES = 2.5


def baked_statistics(bridge, **preset):
    bridge.ok("material_procedural", name="Sample", **preset)
    bridge.ok("assign_material", name="Sheet", material="Sample")
    bridge.ok("bake", names=["Sheet"], channels=["base_color"], size=SIZE, overwrite=True, samples={"base_color": 1}, prefix="Swatch")
    return vein_statistics(luminance("Swatch_base_color", SIZE))


def sheet(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=0.5)
    bridge.ok("uv_smart_project", name="Sheet")


def physical_swatch(bridge, **preset):
    bridge.ok("material_procedural", name="Physical", **preset)
    bridge.ok("assign_material", name="Slab", material="Physical")
    bridge.ok("bake", names=["Slab"], channels=["base_color"], size=SLAB_PIXELS, overwrite=True, samples={"base_color": 1}, prefix="Slab", device="cpu", margin=0)
    values = luminance("Slab_base_color", SLAB_PIXELS)
    return values, vein_profile(values[EDGE_CROP:-EDGE_CROP, EDGE_CROP:-EDGE_CROP], SLAB_METRES * 1000.0 / SLAB_PIXELS)


def slab(bridge):
    bridge.ok("add_primitive", type="plane", name="Slab", size=SLAB_METRES)
    bridge.ok("uv_smart_project", name="Slab", island_margin=0.0)


def test_the_profile_tells_a_hard_line_from_a_soft_one(bridge):
    hard = numpy.ones((200, 200))
    hard[:, 98:102] = 0.2
    soft = numpy.ones((200, 200))
    offsets = numpy.abs(numpy.arange(200) - 100.0)
    soft[:, :] = 1.0 - 0.8 * numpy.clip(1.0 - offsets / 12.0, 0.0, 1.0)
    assert vein_profile(hard, 1.0)["softness"] == 0.0
    assert vein_profile(soft, 1.0)["softness"] >= 0.5


def test_marble_veins_have_soft_edges_and_stone_cracks_do_not(bridge):
    slab(bridge)
    for seed in (1, 2, 3):
        _, measured = physical_swatch(bridge, marble={"seed": seed})
        assert measured["softness"] >= SOFT_VEINS, (seed, measured)
    _, cracks = physical_swatch(bridge, stone={"seed": 1, "cell_scale": 8.0})
    assert cracks["softness"] <= HARD_EDGES, cracks


def test_marble_veins_come_in_layers_of_plausible_width(bridge):
    slab(bridge)
    for seed in (1, 2, 3):
        _, measured = physical_swatch(bridge, marble={"seed": seed})
        assert 2.0 <= measured["width_p50"] <= 8.0, (seed, measured)
        assert measured["width_p90"] >= 6.0 * measured["width_p10"], (seed, measured)
        assert 0.02 <= measured["core_share"] <= 0.15, (seed, measured)


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
    slab(bridge)
    _, thin = physical_swatch(bridge, marble={"vein_width": 0.0})
    _, broad = physical_swatch(bridge, marble={"vein_width": 0.6})
    assert broad["width_p50"] > 1.5 * thin["width_p50"], (thin, broad)
    _, crisp = physical_swatch(bridge, marble={"vein_softness": 0.0})
    _, usual = physical_swatch(bridge, marble={"vein_softness": 0.5})
    assert usual["softness"] > 3.0 * crisp["softness"], (crisp, usual)
    pale, _ = physical_swatch(bridge, marble={"vein_color": [0.5, 0.5, 0.5]})
    dark, _ = physical_swatch(bridge, marble={"vein_color": [0.0, 0.0, 0.0]})
    assert numpy.percentile(pale, 1) > numpy.percentile(dark, 1) + 0.1
    straight, _ = physical_swatch(bridge, marble={"turbulence": 0.0})
    wandering, _ = physical_swatch(bridge, marble={"turbulence": 1.0})
    assert numpy.abs(straight - wandering).mean() > 0.01


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
