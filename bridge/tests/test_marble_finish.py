import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import run

from blendworks_bridge.presets import PRESETS

VIEW_DISTANCE = 1.0
VIEW_FIELD_DEGREES = 40.0
VIEW_PIXELS = 512
PIXEL_METRES = 2.0 * VIEW_DISTANCE * math.tan(math.radians(VIEW_FIELD_DEGREES / 2.0)) / VIEW_PIXELS
VISIBLE_TILT_DEGREES = math.degrees(PIXEL_METRES / (2.0 * VIEW_DISTANCE))
SLAB_METRES = 0.5
BAKE_SIZE = 512
SEEDS = (0, 3)


def slab(bridge):
    bridge.ok("add_primitive", type="plane", name="Slab", size=SLAB_METRES)
    bridge.ok("uv_smart_project", name="Slab", island_margin=0.0)


def tilts(bridge, **marble):
    bridge.ok("material_procedural", name="Stone", marble=marble)
    bridge.ok("assign_material", name="Slab", material="Stone")
    bridge.ok("bake", names=["Slab"], channels=["normal"], size=BAKE_SIZE, overwrite=True, samples={"normal": 1}, prefix="Slab", device="cpu", margin=0, float_buffer=True, time_limit=600.0)
    pixels = numpy.array(bpy.data.images["Slab_normal"].pixels[:], dtype=numpy.float64).reshape(BAKE_SIZE, BAKE_SIZE, 4)
    normals = pixels[..., :3] * 2.0 - 1.0
    cosine = normals[..., 2] / numpy.linalg.norm(normals, axis=2)
    return numpy.degrees(numpy.arccos(numpy.clip(cosine, -1.0, 1.0)))


def test_the_visible_tilt_is_worked_out_from_one_pixel_at_one_metre(bridge):
    assert 0.03 < VISIBLE_TILT_DEGREES < 0.05, VISIBLE_TILT_DEGREES


def test_polished_marble_is_optically_flat_and_honed_and_rough_are_not(bridge):
    slab(bridge)
    finish = PRESETS["marble"].properties["finish"]
    assert finish["default"] == "polished" and finish["enum"] == ["polished", "honed", "rough"] and "flat" in finish["description"]
    for seed in SEEDS:
        default = tilts(bridge, seed=seed)
        assert default.max() <= VISIBLE_TILT_DEGREES, (seed, default.max())
        assert tilts(bridge, seed=seed, finish="polished").max() <= VISIBLE_TILT_DEGREES
    honed, rough = tilts(bridge, seed=3, finish="honed"), tilts(bridge, seed=3, finish="rough")
    assert honed.max() > VISIBLE_TILT_DEGREES, honed.max()
    assert rough.max() > 2.0 * honed.max() or rough.max() > 5.0 * VISIBLE_TILT_DEGREES, (honed.max(), rough.max())
    assert rough.mean() > honed.mean() > 0.0


def test_the_finish_changes_neither_veins_nor_colour(bridge):
    slab(bridge)
    colours = []
    for finish in ("polished", "honed", "rough"):
        bridge.ok("material_procedural", name="Stone", marble={"seed": 3, "finish": finish})
        bridge.ok("assign_material", name="Slab", material="Stone")
        bridge.ok("bake", names=["Slab"], channels=["base_color"], size=128, overwrite=True, samples={"base_color": 1}, prefix="Tone", device="cpu", margin=0, float_buffer=True, time_limit=600.0)
        colours.append(numpy.array(bpy.data.images["Tone_base_color"].pixels[:]))
    assert numpy.abs(colours[0] - colours[1]).max() < 1e-6 and numpy.abs(colours[0] - colours[2]).max() < 1e-6
    bridge.refuse("material_procedural", "bad_args", name="Bad", marble={"finish": "glossy"})


run(globals())
