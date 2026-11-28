import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from final_helpers import EXACT
from harness import run

from blendworks_bridge import exr_read, ground_form, ground_relief

CLASS_RANGES = {"turf": (0.008, 0.03), "gravel": (0.01, 0.04), "mud": (0.001, 0.008)}
FAR_AT_MOST = 1e-4


def ground(bridge, form, surface):
    bridge.ok("heightfield", name="Ground", size=[60.0, 60.0], resolution=61, height=0.001, scale=50.0, octaves=1, tile=[-1, 0], form=form)
    bridge.ok("add_material", name="Soil", base_color=[0.25, 0.2, 0.15], roughness=0.9)
    bridge.ok("assign_material", name="Ground", material="Soil")
    if form == "worn":
        mesh = bpy.data.objects["Ground"].data
        values = np.full(len(mesh.vertices), ground_form.ROUGHNESS[surface], dtype=np.float32)
        mesh.attributes[ground_form.RELIEF_ATTRIBUTE].data.foreach_set("value", values)
    bridge.ok("add_camera", name="Eye", location=[-30.0, 1.0, 1.2], target=[-30.0, 16.0, 0.0], lens=24.0)
    bridge.ok("set_world", color=[1.0, 1.0, 1.0], strength=1.0)


def depth(bridge, name):
    result = bridge.ok("render_final", path=f"{name}.exr", camera="Eye", width=96, height=96, samples=1, passes=["depth"], **EXACT)
    image = exr_read.read_exr(os.path.join(bridge.workspace, f"{name}.passes.exr"))
    return next(value for key, value in image.channels.items() if key.endswith("Depth.Z")), result


def test_near_ground_has_the_micro_relief_of_its_class_and_none_far_away(bridge):
    """Formed flat ground rendered against the same ground unformed: near the camera (depth under 4 m, where the depth
    change is the height change over the cosine of the view) the RMS height change lies in the cited range of its surface
    class (turf, gravel, mud: docs/research/bank-form.md), gravel rougher than turf rougher than mud, and beyond FAR there is
    none. The smooth fBm terrain of before has no relief at this scale at all. Proven by a SPREAD of 0 (no relief) and by
    the near share set to 1 everywhere (the far depth then moves)."""
    found = {}
    for surface in CLASS_RANGES:
        bridge.ok("new_scene")
        ground(bridge, "none", surface)
        flat, plain = depth(bridge, f"plain_{surface}")
        assert plain["ground_detail"] is None
        bridge.ok("new_scene")
        ground(bridge, "worn", surface)
        rough, result = depth(bridge, f"worn_{surface}")
        assert result["ground_detail"]["objects"] == 1
        seen = np.isfinite(flat) & (flat < 1e3)
        near, far = seen & (flat < 4.0), seen & (flat > ground_relief.FAR + 2.0)
        assert near.sum() > 300 and far.sum() > 50, (near.sum(), far.sum())
        rows = np.nonzero(near.any(axis=1))[0]
        slant = 1.2 / np.maximum(flat, 1e-3)
        change = (rough - flat) * slant
        found[surface] = float(np.sqrt(np.mean(change[near] ** 2)))
        low, high = CLASS_RANGES[surface]
        assert low <= found[surface] <= high, (surface, found[surface])
        assert float(np.abs(rough - flat)[far].max()) <= FAR_AT_MOST
        assert len(rows)
    assert found["gravel"] > found["turf"] > found["mud"], found


def test_the_ground_dicing_keeps_its_budget(bridge):
    """A big ground seen from a metre above would dice far past the budget at one pixel; the estimate caps each triangle at
    the frame and the frame at OVERDRAW, and the dicing grows coarser until floor and pixels fit GROUND_BUDGET. Proven by
    dropping the frame cap (the pixel size then runs to thousands)."""
    ground(bridge, "worn", "turf")
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    with ground_relief.RenderDetail(scene, bpy.data.objects["Eye"]) as detail:
        report = detail.report["ground_detail"]
        diced = [m for m in bpy.data.objects["Ground"].modifiers if m.name == ground_relief.MODIFIER]
    assert diced and report["estimated_triangles"] <= ground_relief.GROUND_BUDGET * (1.0 + 1e-9)
    assert report["pixel_size"] < 3.0, report
    assert not [m for m in bpy.data.objects["Ground"].modifiers if m.name == ground_relief.MODIFIER]
    assert not [n for n in bpy.data.materials["Soil"].node_tree.nodes if n.name.startswith(ground_relief.PREFIX)]


run(globals())
