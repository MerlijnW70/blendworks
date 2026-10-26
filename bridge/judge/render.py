import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from judge_common import (
    DEFAULT_MAX_TRIANGLES,
    DEFAULT_MEMORY_MB,
    JudgeError,
    apply_memory_cap,
    positive_int,
    run_guarded,
    script_arguments,
    split_arguments,
)
from judge_geometry import Measurer
from judge_load import load_asset
from judge_rig import VIEWS, Rig, configure_scene, remove_foreign_rig
from judge_sheet import MARKER, MUTED, TEXT, compose, load_png, uv_tile

USAGE = "render.py -- <asset> <measurements.json> <out dir> [--views front,top] [--title text] [--max-triangles n] [--memory-mb n]"
DEFAULT_VIEWS = "front,back,left,right,top,three-quarter"


def read_measurements(path):
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        measurements = document["measurements"]
        low = [float(value) for value in measurements["bounds"]["min"]]
        high = [float(value) for value in measurements["bounds"]["max"]]
        origin = [float(value) for value in measurements["origin"]["point"]]
    except (OSError, ValueError, KeyError, TypeError):
        raise JudgeError("usage", "the measurements file is missing or malformed") from None
    if len(low) != 3 or len(high) != 3 or len(origin) != 3:
        raise JudgeError("usage", "the measurements file has malformed bounds")
    return measurements, low, high, origin


def chosen_views(text):
    views = [view for view in text.split(",") if view]
    unknown = [view for view in views if view not in VIEWS]
    if unknown or not views:
        raise JudgeError("usage", f"unknown views: {', '.join(unknown) or 'none given'}")
    return views


def header_lines(title, measurements):
    size = measurements["size"]
    summary = (
        f"{measurements['triangles']} TRIS   {size[0]:.3f} X {size[1]:.3f} X {size[2]:.3f} M   "
        f"{measurements['materials']['count']} MATERIALS   {measurements['objects']} OBJECTS"
    )
    legend = "+ ORIGIN   UV LAYOUT: GREY USED, RED OVERLAP"
    return [(title, TEXT), (summary, MUTED), (legend, MARKER)]


def render(asset, measurements_path, out_dir, options):
    views = chosen_views(options["views"])
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    apply_memory_cap(positive_int(options["memory-mb"], "memory-mb") * 1024 * 1024)
    measurements, low, high, origin = read_measurements(measurements_path)
    load_asset(asset)
    scene = bpy.context.scene
    remove_foreign_rig(scene)
    measurer = Measurer(triangle_cap)
    measurer.measure(bpy.context.evaluated_depsgraph_get())
    configure_scene(scene)
    rig = Rig(scene, low, high, origin)
    view_dir = os.path.join(out_dir, "views")
    os.makedirs(view_dir, exist_ok=True)
    tiles = []
    rendered = []
    for view in views:
        path = os.path.join(view_dir, f"{view}.png")
        rig.render(view, path)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise JudgeError("render_failed", f"the {view} view did not render")
        pixels, width, height = load_png(path)
        width_metres = rig.tile_width(view)
        label = view if width_metres is None else f"{view}  {width_metres:.2f} M ACROSS"
        tiles.append({"label": label, "pixels": pixels, "size": width, "marker": rig.project(origin)})
        rendered.append({"view": view, "path": path})
    pixels, size, _ = uv_tile(measurer.uv_grid)
    tiles.append({"label": "uv layout", "pixels": pixels, "size": size})
    sheet = os.path.join(out_dir, "contact-sheet.png")
    title = options["title"] or os.path.basename(asset)
    width, height = compose(tiles, header_lines(title, measurements), sheet)
    return {"views": rendered, "contactSheet": sheet, "contactSheetSize": [width, height]}


def main():
    positional, options = split_arguments(
        script_arguments(),
        {"views": DEFAULT_VIEWS, "title": "", "max-triangles": str(DEFAULT_MAX_TRIANGLES), "memory-mb": str(DEFAULT_MEMORY_MB)},
    )
    if len(positional) != 3:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    asset, measurements_path, out_dir = positional
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    run_guarded(os.path.join(out_dir, "render.json"), lambda: render(os.path.abspath(asset), measurements_path, out_dir, options))


main()
