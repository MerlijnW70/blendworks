import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import run
from texture_stats import luminance

PIXELS = 1024
TOP = 0.002
DEPTH = 0.0006
GLYPHS = 0.014
OPEN_MARGIN = 0.003


def engraved_plate(bridge):
    bridge.ok("add_primitive", type="cube", name="Plate", size=1.0)
    bridge.ok("transform", name="Plate", scale=[0.06, 0.06, 2 * TOP])
    bridge.ok("apply_transform", name="Plate", scale=True)
    bridge.ok("uv_smart_project", name="Plate", island_margin=0.002)
    bridge.ok("engrave", name="Plate", text="808", plane={"origin": [0, 0, TOP], "normal": [0, 0, 1]}, size=GLYPHS, depth=DEPTH)


def texel_classes():
    mesh = bpy.data.objects["Plate"].data
    mesh.calc_loop_triangles()
    layer = mesh.uv_layers.active.uv
    recess = numpy.zeros((PIXELS, PIXELS), dtype=bool)
    open_top = numpy.zeros((PIXELS, PIXELS), dtype=bool)
    rows, columns = numpy.mgrid[0:PIXELS, 0:PIXELS]
    centres = numpy.stack([(columns + 0.5) / PIXELS, (rows + 0.5) / PIXELS], axis=-1)
    for triangle in mesh.loop_triangles:
        polygon = mesh.polygons[triangle.polygon_index]
        if polygon.normal.z < 0.999:
            continue
        centre = polygon.center
        if abs(centre.z - (TOP - DEPTH)) < 1e-6:
            target = recess
        elif abs(centre.z - TOP) < 1e-6 and max(abs(centre.x), abs(centre.y)) > GLYPHS + OPEN_MARGIN and max(abs(centre.x), abs(centre.y)) < 0.03 - OPEN_MARGIN:
            target = open_top
        else:
            continue
        a, b, c = (numpy.array(layer[loop].vector) for loop in triangle.loops)
        v0, v1 = b - a, c - a
        denominator = v0[0] * v1[1] - v0[1] * v1[0]
        if abs(denominator) < 1e-14:
            continue
        low = numpy.floor(numpy.minimum.reduce([a, b, c]) * PIXELS).astype(int)
        high = numpy.ceil(numpy.maximum.reduce([a, b, c]) * PIXELS).astype(int)
        window = centres[low[1]:high[1], low[0]:high[0]] - a
        u = (window[..., 0] * v1[1] - window[..., 1] * v1[0]) / denominator
        v = (v0[0] * window[..., 1] - v0[1] * window[..., 0]) / denominator
        inside = (u >= 0) & (v >= 0) & (u + v <= 1)
        target[low[1]:high[1], low[0]:high[0]] |= inside
    return recess, open_top


def albedo_ratio(bridge, age):
    bridge.ok("material_procedural", name=f"Brass_{age}", brass={"age": age})
    bridge.ok("assign_material", name="Plate", material=f"Brass_{age}")
    bridge.ok("bake", names=["Plate"], channels=["base_color"], size=PIXELS, overwrite=True, samples={"base_color": 16}, prefix="Plate", device="cpu", margin=0, float_buffer=True, time_limit=600.0)
    values = luminance("Plate_base_color", PIXELS)
    recess, open_top = texel_classes()
    assert recess.sum() > 2000 and open_top.sum() > 20000, (recess.sum(), open_top.sum())
    return float(values[recess].mean() / values[open_top].mean())


def test_aged_brass_darkens_engraved_recesses_and_new_brass_does_not(bridge):
    engraved_plate(bridge)
    ratios = {age: albedo_ratio(bridge, age) for age in ("new", "handled", "aged", "dull")}
    assert ratios["new"] >= 0.9, ratios
    assert ratios["aged"] <= 0.5, ratios
    assert ratios["aged"] < ratios["handled"] < ratios["new"], ratios
    assert ratios["dull"] < ratios["new"], ratios


def test_age_tarnishes_the_open_metal_from_new_to_dull(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=0.2)
    bridge.ok("uv_smart_project", name="Sheet")
    means = {}
    for age in ("new", "handled", "aged", "dull"):
        bridge.ok("material_procedural", name=age, brass={"age": age, "color": [0.6, 0.4, 0.12]})
        bridge.ok("assign_material", name="Sheet", material=age)
        bridge.ok("bake", names=["Sheet"], channels=["base_color", "roughness"], size=256, overwrite=True, samples={"base_color": 4, "roughness": 4}, prefix=f"Sheet_{age}", device="cpu", margin=0, float_buffer=True, time_limit=600.0)
        colour = numpy.array(bpy.data.images[f"Sheet_{age}_base_color"].pixels[:]).reshape(256, 256, 4)[32:-32, 32:-32, :3].mean(axis=(0, 1))
        rough = numpy.array(bpy.data.images[f"Sheet_{age}_roughness"].pixels[:]).reshape(256, 256, 4)[32:-32, 32:-32, 0].mean()
        means[age] = (float(colour.mean()), float(colour[0] - colour[2]), float(rough))
    assert means["new"][0] > means["handled"][0] > means["aged"][0], means
    assert means["new"][1] > means["aged"][1], means
    assert means["dull"][2] > means["aged"][2] > means["new"][2], means


run(globals())
