import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from judge_common import DEFAULT_MEMORY_MB, JudgeError, memory_cap_from, positive_int, run_guarded, script_arguments, split_arguments
from judge_device import GPU_BACKENDS, device_backend, resolve_backend, use_device
from judge_load import empty_scene
from judge_rig import RESOLUTION, SAMPLES, Rig, configure_scene

USAGE = "gpu_warm.py -- <out dir> [--device AUTO|OPTIX|CUDA|HIP|METAL|ONEAPI] [--backends OPTIX,CUDA] [--res px] [--samples n]"
DEFAULTS = {
    "device": "AUTO",
    "backends": ",".join(GPU_BACKENDS),
    "res": str(RESOLUTION),
    "samples": str(SAMPLES),
    "memory-mb": str(DEFAULT_MEMORY_MB),
    "memory-kind": "data",
}


def warm_scene():
    scene = empty_scene()
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.5))
    material = bpy.data.materials.new("judge-warm")
    bpy.context.active_object.data.materials.append(material)
    return scene


def warm(out_dir, options):
    memory_cap_from(options)
    backend = device_backend(options["device"])
    if backend == "CPU":
        raise JudgeError("usage", "warming the GPU kernels needs a GPU device")
    scene = warm_scene()
    backend, found = resolve_backend(backend, options["backends"])
    configure_scene(scene, min(positive_int(options["res"], "res"), RESOLUTION), min(positive_int(options["samples"], "samples"), SAMPLES))
    device = use_device(scene, backend, found)
    rig = Rig(scene, [-0.5, -0.5, 0.0], [0.5, 0.5, 1.0], [0.0, 0.0, 0.0])
    path = os.path.join(out_dir, "warm.png")
    rig.render("three-quarter", path)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise JudgeError("render_failed", "the warm-up view did not render")
    return {"device": device, "probes": found["probes"]}


def main():
    positional, options = split_arguments(script_arguments(), DEFAULTS)
    if len(positional) != 1:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    out_dir = os.path.abspath(positional[0])
    os.makedirs(out_dir, exist_ok=True)
    run_guarded(os.path.join(out_dir, "warm.json"), lambda: warm(out_dir, options))


main()
