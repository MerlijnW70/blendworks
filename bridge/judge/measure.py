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
from judge_geometry import Measurer
from judge_load import load_asset
from judge_textures import measure_textures

USAGE = (
    "measure.py -- <asset> <out.json> [--max-triangles n] [--memory-mb n] [--memory-kind address-space|data] [--uv-grid path]"
    " [--floating-tolerance metres] [--objects yes|no]"
)
MAX_FLOATING_TOLERANCE = 1.0


def floating_tolerance(text):
    if text == "":
        return None
    try:
        value = float(text)
    except ValueError:
        raise JudgeError("usage", "--floating-tolerance must be a number of metres") from None
    if not 0 <= value <= MAX_FLOATING_TOLERANCE:
        raise JudgeError("usage", f"--floating-tolerance must be between 0 and {MAX_FLOATING_TOLERANCE} m")
    return value


def objects_wanted(text):
    if text not in ("yes", "no"):
        raise JudgeError("usage", "--objects must be yes or no")
    return text == "yes"


def measure(asset, options):
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    tolerance = floating_tolerance(options["floating-tolerance"])
    objects = objects_wanted(options["objects"])
    limits = memory_cap_from(options)
    loaded = load_asset(asset, triangle_cap)
    scene = bpy.context.scene
    measurer = Measurer(triangle_cap, tolerance, integrity=True, objects=objects)
    measurer.measure(bpy.context.evaluated_depsgraph_get())
    measurements = measurer.result()
    if options["uv-grid"]:
        measurer.uv_grid.save(os.path.abspath(options["uv-grid"]))
    measurements.update(loaded)
    measurements["textures"] = measure_textures(measurer.material_blocks, measurer.faces_without_material, loaded["externalFilesRefused"])
    measurements["objectsAll"] = len(scene.objects)
    return {"measurements": measurements, "limits": {**limits, "maxTriangles": triangle_cap}}


def main():
    positional, options = split_arguments(
        script_arguments(), {"max-triangles": str(DEFAULT_MAX_TRIANGLES), "memory-mb": str(DEFAULT_MEMORY_MB), "memory-kind": "address-space", "uv-grid": "", "floating-tolerance": "", "objects": "no"}
    )
    if len(positional) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    asset, out_path = positional
    run_guarded(out_path, lambda: measure(os.path.abspath(asset), options))


main()
