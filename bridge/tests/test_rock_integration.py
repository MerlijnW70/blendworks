import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run
from liquid_helpers import dimple

from blendworks_bridge import rock_relief
from blendworks_bridge.fragments import FRESH_FLAG


def test_chip_and_fracture_give_a_rock_its_fresh_variant_and_plain_meshes_keep_freshbreak(bridge):
    """A cube with a stone material of a lithology gets the material's fresh variant (no rind, lichen or moss, rough break
    relief) as its fresh slot from chip, and fracture's pieces reuse it; a cube with a plain material still gets FreshBreak.
    Proven by leaving the rock check out of slot_layout (the rock then gets FreshBreak)."""
    bridge.ok("material_procedural", name="Granite", stone={"lithology": "granite"})
    bridge.ok("add_primitive", type="cube", name="Block", size=1.0)
    bridge.ok("assign_material", name="Block", material="Granite")
    result = bridge.ok("chip", name="Block", count=3, depth=0.2, seed=2)
    names = [slot.name for slot in bpy.data.objects["Block"].data.materials]
    assert names == ["Granite", "Granite_fresh"] and result["fresh_slot"] == 1, names
    fresh = bpy.data.materials["Granite_fresh"]
    assert fresh.get(FRESH_FLAG) and rock_relief.is_rock_material(fresh)
    assert '"fresh": true' in fresh[rock_relief.ROCK_FLAG] and fresh.displacement_method == "BOTH"
    pieces = bridge.ok("fracture", name="Block", pieces=3, mode="binary", seed=1, min_size=0.1)["pieces"]
    assert all([slot.name for slot in bpy.data.objects[piece].data.materials] == ["Granite", "Granite_fresh"] for piece in pieces)
    bridge.ok("add_primitive", type="cube", name="Plain", size=1.0)
    bridge.ok("add_material", name="Grey", base_color=[0.4, 0.4, 0.4])
    bridge.ok("assign_material", name="Plain", material="Grey")
    bridge.ok("chip", name="Plain", count=2, depth=0.2, seed=2)
    assert [slot.name for slot in bpy.data.objects["Plain"].data.materials] == ["Grey", "FreshBreak"]


def test_shore_stones_are_granite_with_histories_and_render_with_relief(bridge):
    """shore_stones without a material builds granite (a stone material with a lithology) and its fresh variant, reports
    each variant's history and shape, and render_final dices the stones near the camera. Proven by the old plain stone
    default (no rock flag, so no relief in the render)."""
    dimple("Ground", 30.0, 120, 3.0, 6.0)
    bridge.ok("add_material", name="Soil", base_color=[0.2, 0.17, 0.12])
    bridge.ok("assign_material", name="Ground", material="Soil")
    bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[0.0, 0.0, 0.0], name="Pond")
    result = bridge.ok("shore_stones", target="Ground", classes=3, variants=1, max_count=40, seed=3)
    material = bpy.data.materials["ShoreStones_stone"]
    assert rock_relief.is_rock_material(material) and '"lithology": "granite"' in material[rock_relief.ROCK_FLAG]
    assert [shape["history"] for shape in result["shapes"]] == ["talus", "shore", "river"]
    assert result["shapes"][0]["roundness"] < result["shapes"][2]["roundness"]
    near = next(item for item in result["stones"])
    position = near["position"]
    bridge.ok("add_camera", name="Eye", location=[position[0] + 1.5, position[1] - 1.5, position[2] + 1.2], target=position, lens=35.0)
    render = bridge.ok("render_final", path="shore.png", camera="Eye", width=64, height=64, samples=1, denoise=False, preview=False, device="cpu")
    assert render["rock_detail"]["objects"] >= 1, render["rock_detail"]


run(globals())
