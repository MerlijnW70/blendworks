import json
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
    run_guarded,
    script_arguments,
    split_arguments,
    stopwatch,
)
from judge_device import CPU, GPU_BACKENDS, device_backend, resolve_backend, use_device
from judge_geometry import Measurer
from judge_load import load_asset
from judge_rig import VIEWS, Rig, configure_scene, remove_foreign_rig
from judge_sheet import MARKER, MUTED, TEXT, compose, load_png, texture_line, uv_tile
from judge_uv import UvGrid

USAGE = (
    "render.py -- <asset> <measurements.json> <out dir> [--views front,top] [--title text] [--mode full|preview]"
    " [--device CPU|AUTO|OPTIX|CUDA|HIP|METAL|ONEAPI] [--backends OPTIX,CUDA] [--max-triangles n] [--memory-mb n] [--memory-kind address-space|data] [--uv-grid path]"
)
MODES = ("full", "preview")
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


def chosen_mode(text):
    if text not in MODES:
        raise JudgeError("usage", f"--mode must be one of {', '.join(MODES)}")
    return text


def header_lines(title, measurements, preview):
    size = measurements["size"]
    summary = (
        f"{measurements['triangles']} TRIS   {size[0]:.3f} X {size[1]:.3f} X {size[2]:.3f} M   "
        f"{measurements['materials']['count']} MATERIALS   {measurements['objects']} OBJECTS"
    )
    legend = "PREVIEW: VIEWS SKIPPED   UV LAYOUT: GREY USED, RED OVERLAP" if preview else "+ ORIGIN   UV LAYOUT: GREY USED, RED OVERLAP"
    return [(title, TEXT), (summary, MUTED), (texture_line(measurements.get("textures")), MUTED), (legend, MARKER)]


def render_views(scene, views, low, high, origin, out_dir, backend, found):
    configure_scene(scene)
    device = use_device(scene, backend, found)
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
    return device, tiles, rendered


def uv_grid_for(path, triangle_cap):
    if path:
        return UvGrid.load(os.path.abspath(path))
    measurer = Measurer(triangle_cap)
    measurer.measure(bpy.context.evaluated_depsgraph_get())
    return measurer.uv_grid


def render(asset, measurements_path, out_dir, options):
    views = chosen_views(options["views"])
    mode = chosen_mode(options["mode"])
    backend = device_backend(options["device"])
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    memory_cap_from(options)
    measurements, low, high, origin = read_measurements(measurements_path)
    found = {"probes": [], "probeSeconds": None}
    if mode == "full":
        backend, found = resolve_backend(backend, options["backends"])
    if mode == "full" or not options["uv-grid"]:
        load_asset(asset)
        remove_foreign_rig(bpy.context.scene)
    scene = bpy.context.scene
    uv_grid = uv_grid_for(options["uv-grid"], triangle_cap)
    device = None
    tiles = []
    rendered = []
    views_time = stopwatch()
    if mode == "full":
        device, tiles, rendered = render_views(scene, views, low, high, origin, out_dir, backend, found)
    views_seconds = views_time()
    sheet_time = stopwatch()
    pixels, size, _ = uv_tile(uv_grid)
    tiles.append({"label": "uv layout", "pixels": pixels, "size": size})
    sheet = os.path.join(out_dir, "contact-sheet.png")
    title = options["title"] or os.path.basename(asset)
    width, height = compose(tiles, header_lines(title, measurements, mode == "preview"), sheet)
    timings = {"views": views_seconds if mode == "full" else None, "sheet": sheet_time()}
    timings["device"] = found["probeSeconds"]
    return {
        "views": rendered,
        "contactSheet": sheet,
        "contactSheetSize": [width, height],
        "device": device,
        "probes": found["probes"],
        "timings": timings,
    }


def main():
    positional, options = split_arguments(
        script_arguments(),
        {
            "views": DEFAULT_VIEWS,
            "title": "",
            "mode": "full",
            "device": CPU,
            "backends": ",".join(GPU_BACKENDS),
            "max-triangles": str(DEFAULT_MAX_TRIANGLES),
            "memory-mb": str(DEFAULT_MEMORY_MB),
            "memory-kind": "address-space",
            "uv-grid": "",
        },
    )
    if len(positional) != 3:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    asset, measurements_path, out_dir = positional
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    run_guarded(os.path.join(out_dir, "render.json"), lambda: render(os.path.abspath(asset), measurements_path, out_dir, options))


main()
