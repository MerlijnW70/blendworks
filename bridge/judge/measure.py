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
)
from judge_geometry import Measurer, guaranteed_triangles
from judge_load import load_asset

USAGE = "measure.py -- <asset> <out.json> [--max-triangles n] [--memory-mb n] [--memory-kind address-space|data] [--uv-grid path]"


def measure(asset, options):
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    limits = memory_cap_from(options)
    loaded = load_asset(asset)
    scene = bpy.context.scene
    estimate = guaranteed_triangles(scene)
    if estimate > triangle_cap:
        raise JudgeError("too_many_triangles", f"the asset makes at least {estimate} triangles, over the judge's cap of {triangle_cap}")
    measurer = Measurer(triangle_cap)
    measurer.measure(bpy.context.evaluated_depsgraph_get())
    measurements = measurer.result()
    if options["uv-grid"]:
        measurer.uv_grid.save(os.path.abspath(options["uv-grid"]))
    measurements.update(loaded)
    measurements["objectsAll"] = len(scene.objects)
    return {"measurements": measurements, "limits": {**limits, "maxTriangles": triangle_cap}}


def main():
    positional, options = split_arguments(
        script_arguments(), {"max-triangles": str(DEFAULT_MAX_TRIANGLES), "memory-mb": str(DEFAULT_MEMORY_MB), "memory-kind": "address-space", "uv-grid": ""}
    )
    if len(positional) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    asset, out_path = positional
    run_guarded(out_path, lambda: measure(os.path.abspath(asset), options))


main()
