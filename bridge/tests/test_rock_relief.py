import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from final_helpers import EXACT
from harness import run

from blendworks_bridge import exr_read, rock_relief

NEAR_RMS_AT_LEAST = 0.0004
FAR_AT_MOST = 5e-5
FAR_BUMP_AT_LEAST = 0.01
SIZE = 96


def strip(bridge, lithology):
    bridge.ok("mesh_from_data", name="Strip", vertices=[[-40.0, 0.5, 0.0], [40.0, 0.5, 0.0], [40.0, 60.0, 0.0], [-40.0, 60.0, 0.0]], faces=[[0, 1, 2, 3]])
    bridge.ok("material_procedural", name="Ground", stone={"lithology": lithology, "lichen": 0.0, "moss": 0.0})
    bridge.ok("assign_material", name="Strip", material="Ground")
    bridge.ok("add_camera", name="Eye", location=[0.0, 0.0, 1.6], target=[0.0, 16.0, 0.0], lens=20.0)
    bridge.ok("set_world", color=[1.0, 1.0, 1.0], strength=1.0)


def passes(bridge, name):
    result = bridge.ok("render_final", path=f"{name}.exr", camera="Eye", width=SIZE, height=SIZE, samples=1, passes=["depth", "normal"], **EXACT)
    image = exr_read.read_exr(os.path.join(bridge.workspace, f"{name}.passes.exr"))
    depth = next(value for key, value in image.channels.items() if key.endswith("Depth.Z"))
    normal = np.stack([next(value for key, value in image.channels.items() if key.endswith(f"Normal.{axis}")) for axis in "XYZ"], axis=-1)
    return depth, normal, result


def test_relief_displaces_the_surface_near_the_camera_and_only_bumps_it_far_away(bridge):
    """The same strip of ground rendered with granite and with the plain stone: within NEAR the granite's depth differs by
    its relief (an RMS of at least NEAR_RMS_AT_LEAST metres), beyond FAR the depth is the plain strip's to FAR_AT_MOST (float32 depth
    and the different tessellation, 1/40 of the relief), yet the
    normals there still differ (bump). Proven by setting the near share to 1 everywhere (the far depth then moves) and to 0
    (the near depth stays flat)."""
    strip(bridge, "granite")
    rough, rough_normal, result = passes(bridge, "granite")
    assert result["rock_detail"]["objects"] == 1 and result["rock_detail"]["pixel_size"] == rock_relief.DICING_PIXELS
    assert not any(modifier.name == rock_relief.MODIFIER for modifier in bpy.data.objects["Strip"].modifiers), "the render removes its subdivision"
    bridge.ok("material_procedural", name="Ground", stone={"lithology": "none"})
    flat, flat_normal, plain = passes(bridge, "plain")
    assert plain["rock_detail"] is None
    seen = np.isfinite(flat) & (flat < 1e3)
    near = seen & (flat < rock_relief.NEAR - 1.5)
    far = seen & (flat > rock_relief.FAR + 1.0)
    assert near.sum() > 200 and far.sum() > 200, (near.sum(), far.sum())
    change = rough - flat
    rms = float(np.sqrt(np.mean(change[near] ** 2)))
    assert rms >= NEAR_RMS_AT_LEAST, rms
    assert float(np.abs(change[far]).max()) <= FAR_AT_MOST, float(np.abs(change[far]).max())
    bent = np.linalg.norm(rough_normal[far] - flat_normal[far], axis=1)
    assert float(np.mean(bent)) >= FAR_BUMP_AT_LEAST, float(np.mean(bent))


def test_the_dicing_keeps_the_triangle_budget(bridge):
    """2 * pixels / size^2 triangles: under the budget at the stated dicing size, and a larger size that brings an estimate
    over budget back to it. Proven by returning the stated size always (the second case then exceeds the budget)."""
    size, estimate = rock_relief.dicing_for(1.0e6)
    assert size == rock_relief.DICING_PIXELS and estimate == 2.0e6
    size, estimate = rock_relief.dicing_for(2.0e7)
    assert size > rock_relief.DICING_PIXELS and estimate <= rock_relief.TRIANGLE_BUDGET * (1.0 + 1e-9)
    assert rock_relief.TRIANGLE_BUDGET * rock_relief.MEMORY_PER_TRIANGLE <= 1.1e9


def test_a_crowded_view_is_diced_coarser_within_the_budget(bridge):
    """Rocks that fill a big frame would need more triangles than the budget at one pixel; render_final coarsens the dicing
    so the estimate fits, counts only rocks within FAR, and leaves to the bump a mesh so finely divided that its patches
    alone (six triangles for each of its triangles) would take more than half the budget. Proven by dropping the patch
    floor (the fine sphere is then diced). Measured with the budget lowered, since a full-size frame of rock
    would take long to render on the CPU."""
    bridge.ok("add_primitive", type="ico_sphere", name="Near", radius=1.0, subdivisions=3, location=[0.0, 3.0, 0.0])
    bridge.ok("add_primitive", type="ico_sphere", name="Away", radius=1.0, subdivisions=3, location=[0.0, 60.0, 0.0])
    bridge.ok("add_primitive", type="ico_sphere", name="Fine", radius=0.5, subdivisions=6, location=[1.5, 4.0, 0.0])
    bridge.ok("material_procedural", name="Granite", stone={"lithology": "granite"})
    for name in ("Near", "Away", "Fine"):
        bridge.ok("assign_material", name=name, material="Granite")
    bridge.ok("add_camera", name="Eye", location=[0.0, 0.0, 0.0], target=[0.0, 3.0, 0.0], lens=35.0)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    budget = rock_relief.TRIANGLE_BUDGET
    try:
        rock_relief.TRIANGLE_BUDGET = 100_000
        with rock_relief.RenderDetail(scene, bpy.context.view_layer, bpy.data.objects["Eye"]) as detail:
            report = detail.report["rock_detail"]
            modifiers = {name: [m for m in bpy.data.objects[name].modifiers if m.name == rock_relief.MODIFIER] for name in ("Near", "Away", "Fine")}
    finally:
        rock_relief.TRIANGLE_BUDGET = budget
    assert report["objects"] == 1 and report["bump_only"] == 2, report
    assert modifiers["Near"] and not modifiers["Away"] and not modifiers["Fine"]
    assert report["pixel_size"] > 1.0 and report["estimated_triangles"] <= 100_000, report
    assert modifiers["Near"][0].adaptive_pixel_size == report["pixel_size"] or abs(modifiers["Near"][0].adaptive_pixel_size - report["pixel_size"]) < 1e-3
    assert not [m for m in bpy.data.objects["Near"].modifiers if m.name == rock_relief.MODIFIER]


def test_rock_memory_stays_within_the_stated_bytes_per_triangle(bridge):
    """Cycles' own memory report (Mem in the render statistics) grows with the diced rock by at most MEMORY_PER_TRIANGLE
    bytes per estimated triangle (plus a fixed allowance for the displacement shader and BVH build). Proven by halving
    MEMORY_PER_TRIANGLE, which the measured growth then exceeds."""
    bridge.ok("add_primitive", type="ico_sphere", name="Boulder", radius=0.6, subdivisions=3, location=[0.0, 1.6, 0.0])
    bridge.ok("material_procedural", name="Granite", stone={"lithology": "granite"})
    bridge.ok("assign_material", name="Boulder", material="Granite")
    bridge.ok("add_camera", name="Eye", location=[0.0, 0.0, 0.0], target=[0.0, 1.6, 0.0], lens=35.0)
    peaks = []

    def measured(statistics):
        for piece in statistics.split("|"):
            piece = piece.strip()
            if piece.startswith("Mem:"):
                text = piece[4:].split(",")[0].strip()
                peaks[-1] = max(peaks[-1], float(text.rstrip("M")) * 2**20 if text.endswith("M") else float(text.rstrip("G")) * 2**30)

    bpy.app.handlers.render_stats.append(measured)
    try:
        peaks.append(0.0)
        bridge.ok("material_procedural", name="Plain", stone={"lithology": "none"})
        bridge.ok("assign_material", name="Boulder", material="Plain")
        bridge.ok("render_final", path="plain.png", camera="Eye", width=256, height=256, samples=1, **EXACT)
        peaks.append(0.0)
        bridge.ok("assign_material", name="Boulder", material="Granite")
        result = bridge.ok("render_final", path="rock.png", camera="Eye", width=256, height=256, samples=1, **EXACT)
    finally:
        bpy.app.handlers.render_stats.remove(measured)
    triangles = result["rock_detail"]["estimated_triangles"]
    growth = peaks[1] - peaks[0]
    assert triangles > 20_000, triangles
    print("rock memory", growth, triangles, growth / triangles)
    assert growth <= rock_relief.MEMORY_PER_TRIANGLE * triangles + 32 * 2**20, (growth, triangles, growth / triangles)


run(globals())
