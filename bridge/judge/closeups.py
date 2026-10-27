import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from judge_closeup import compose_closeups, render_shots, world_points
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
from judge_rig import Rig, configure_scene, remove_foreign_rig
from judge_sheet import MARKER, MUTED, TEXT

USAGE = (
    "closeups.py -- <asset> <out dir> [--res px] [--samples n] [--title text]"
    " [--device CPU|AUTO|OPTIX|CUDA|HIP|METAL|ONEAPI] [--backends OPTIX,CUDA] [--max-triangles n] [--memory-mb n] [--memory-kind address-space|data]"
)
DEFAULT_RESOLUTION = 1200
DEFAULT_SAMPLES = 16
MAX_RESOLUTION = 4096
MAX_SAMPLES = 4096
SHEET = "closeup-sheet.png"


def bounded(text, name, highest):
    value = positive_int(text, name)
    if value > highest:
        raise JudgeError("usage", f"--{name} must be at most {highest}")
    return value


def device_text(device):
    if device["backend"] == CPU:
        return "RENDER: CPU"
    return f"RENDER: GPU {device['backend']} ({', '.join(device['devices'])})"


def closeups(asset, out_dir, options):
    resolution = bounded(options["res"], "res", MAX_RESOLUTION)
    samples = bounded(options["samples"], "samples", MAX_SAMPLES)
    backend = device_backend(options["device"])
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    memory_cap_from(options)
    backend, found = resolve_backend(backend, options["backends"])
    load_asset(asset, triangle_cap)
    scene = bpy.context.scene
    remove_foreign_rig(scene)
    measurer = Measurer(triangle_cap, integrity=False)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    measurer.measure(depsgraph)
    measured = measurer.result()
    points = world_points(depsgraph)
    configure_scene(scene, resolution, samples, outlines=False)
    device = use_device(scene, backend, found)
    rig = Rig(scene, measured["bounds"]["min"], measured["bounds"]["max"], measured["origin"]["point"])
    render_time = stopwatch()
    images = render_shots(rig, points, out_dir)
    for image in images:
        if not os.path.isfile(image["path"]) or os.path.getsize(image["path"]) == 0:
            raise JudgeError("render_failed", f"the {image['name']} close-up did not render")
    render_seconds = render_time()
    sheet_time = stopwatch()
    size = measured["size"]
    title = options["title"] or os.path.basename(asset)
    header = [
        (title, TEXT),
        (f"{measured['triangles']} TRIS   {size[0]:.3f} X {size[1]:.3f} X {size[2]:.3f} M   {measured['objects']} OBJECTS", MUTED),
        (f"CLOSE-UPS {resolution} PX   {samples} SAMPLES   DENOISED   {device_text(device)}", MARKER),
    ]
    sheet = os.path.join(out_dir, SHEET)
    width, height = compose_closeups(images, resolution, header, sheet)
    return {
        "images": images,
        "sheet": sheet,
        "sheetSize": [width, height],
        "device": device,
        "probes": found["probes"],
        "timings": {"device": found["probeSeconds"], "render": render_seconds, "sheet": sheet_time()},
    }


def main():
    positional, options = split_arguments(
        script_arguments(),
        {
            "res": str(DEFAULT_RESOLUTION),
            "samples": str(DEFAULT_SAMPLES),
            "title": "",
            "device": CPU,
            "backends": ",".join(GPU_BACKENDS),
            "max-triangles": str(DEFAULT_MAX_TRIANGLES),
            "memory-mb": str(DEFAULT_MEMORY_MB),
            "memory-kind": "address-space",
        },
    )
    if len(positional) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    asset, out_dir = positional
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    run_guarded(os.path.join(out_dir, "closeups.json"), lambda: closeups(os.path.abspath(asset), out_dir, options))


main()
