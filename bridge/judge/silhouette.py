import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from judge_common import (
    DEFAULT_MAX_TRIANGLES,
    DEFAULT_MEMORY_MB,
    JudgeError,
    memory_cap_from,
    positive_int,
    rounded,
    run_guarded,
    script_arguments,
    split_arguments,
)
from judge_device import CPU, apply_device
from judge_geometry import Measurer
from judge_load import MEASURE_FRAME, load_asset
from judge_rig import STAMPS, VIEWS, Rig, remove_foreign_rig

USAGE = "silhouette.py -- <asset> <out dir> --views front:512,left:256 [--frame asset|x0,y0,z0,x1,y1,z1] [--origin x,y,z] [--max-triangles n] [--memory-mb n]"
MIN_SIZE = 16
MAX_SIZE = 2048
FILTER_WIDTH = 0.01


def chosen_views(text):
    views = []
    for item in [part for part in text.split(",") if part]:
        view, _, size = item.partition(":")
        if view not in VIEWS or view in (entry[0] for entry in views):
            raise JudgeError("usage", f"unknown or repeated view {view}")
        try:
            pixels = int(size)
        except ValueError:
            raise JudgeError("usage", f"the size of the {view} view must be a whole number") from None
        if not MIN_SIZE <= pixels <= MAX_SIZE:
            raise JudgeError("usage", f"the size of the {view} view must be {MIN_SIZE} to {MAX_SIZE} pixels")
        views.append((view, pixels))
    if not views:
        raise JudgeError("usage", "--views names no view")
    return views


def numbers(text, count, name):
    try:
        values = [float(part) for part in text.split(",")]
    except ValueError:
        raise JudgeError("usage", f"--{name} must be {count} numbers") from None
    if len(values) != count or not all(math.isfinite(value) for value in values):
        raise JudgeError("usage", f"--{name} must be {count} finite numbers")
    return values


def framing(text, origin_text, triangle_cap):
    if text == "asset":
        measurer = Measurer(triangle_cap, integrity=False)
        measurer.measure(bpy.context.evaluated_depsgraph_get())
        measured = measurer.result()
        return measured["bounds"]["min"], measured["bounds"]["max"], measured["origin"]["point"]
    values = numbers(text, 6, "frame")
    low, high = values[:3], values[3:]
    if any(low[axis] > high[axis] for axis in range(3)):
        raise JudgeError("usage", "--frame needs the low corner first")
    origin = numbers(origin_text, 3, "origin") if origin_text else [(low[axis] + high[axis]) / 2 for axis in range(3)]
    return low, high, origin


def silhouette_material():
    material = bpy.data.materials.new("judge-silhouette")
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    return material


def configure(scene):
    scene.render.engine = "CYCLES"
    apply_device(scene, CPU)
    cycles = scene.cycles
    cycles.samples = 1
    cycles.use_adaptive_sampling = False
    cycles.seed = 0
    cycles.use_animated_seed = False
    cycles.use_denoising = False
    cycles.pixel_filter_type = "BOX"
    cycles.filter_width = FILTER_WIDTH
    cycles.max_bounces = 0
    cycles.transparent_max_bounces = 0
    scene.render.film_transparent = True
    scene.render.resolution_percentage = 100
    scene.render.dither_intensity = 0.0
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.use_freestyle = False
    for stamp in STAMPS:
        setattr(scene.render, stamp, False)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_layers[0].material_override = silhouette_material()
    scene.frame_set(MEASURE_FRAME)


def silhouettes(asset, out_dir, options):
    views = chosen_views(options["views"])
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    memory_cap_from(options)
    load_asset(asset, triangle_cap)
    scene = bpy.context.scene
    remove_foreign_rig(scene)
    low, high, origin = framing(options["frame"], options["origin"], triangle_cap)
    configure(scene)
    rig = Rig(scene, low, high, origin)
    folder = os.path.join(out_dir, "silhouettes")
    os.makedirs(folder, exist_ok=True)
    rendered = []
    for view, size in views:
        scene.render.resolution_x = size
        scene.render.resolution_y = size
        path = os.path.join(folder, f"{view}.png")
        rig.render(view, path)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise JudgeError("render_failed", f"the {view} silhouette did not render")
        rendered.append({"view": view, "path": path, "size": size})
    return {"views": rendered, "frame": {"min": rounded(list(rig.low)), "max": rounded(list(rig.high))}}


def main():
    positional, options = split_arguments(
        script_arguments(),
        {"views": "", "frame": "asset", "origin": "", "max-triangles": str(DEFAULT_MAX_TRIANGLES), "memory-mb": str(DEFAULT_MEMORY_MB), "memory-kind": "address-space"},
    )
    if len(positional) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    asset, out_dir = positional
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    run_guarded(os.path.join(out_dir, "silhouettes.json"), lambda: silhouettes(os.path.abspath(asset), out_dir, options))


main()
