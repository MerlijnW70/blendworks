"""The judge passes: chooses stages, runs each and digests the files."""

import hashlib
import json
import os
import time

import bpy

from judge_common import (
    DEFAULT_MAX_TRIANGLES,
    DEFAULT_MEMORY_MB,
    FileLockError,
    JudgeError,
    apply_memory_cap,
    cap_address_space,
    exit_on_lock,
    failure_payload,
    lift_address_space,
    memory_kind,
    memory_payload,
    positive_int,
    read_bytes,
    shared_access,
    write_json,
    write_payload,
)
from judge_device import CPU, GPU_BACKENDS
from judge_load import load_asset
from judge_measure_stage import measure, read_measurements, uv_grid_file
from judge_render_stages import CLOSEUPS_FOLDER, closeups_stage, reference_stage, sheet_stage, views_stage
from judge_rig import RESOLUTION, SAMPLES, remove_foreign_rig
from judge_skin import DEFAULT_WEIGHT_TOLERANCE

ORDER = ("measure", "reference", "views", "sheet", "closeups")
SCENE_STAGES = ("reference", "views", "closeups")
VERIFIED_STAGES = ("measure", "reference")
OUTPUTS = {
    "measure": "measurements.json",
    "reference": "silhouettes.json",
    "views": "render.json",
    "sheet": "sheet.json",
    "closeups": os.path.join(CLOSEUPS_FOLDER, "closeups.json"),
}
PROGRESS = "progress.log"
PASS_DEFAULTS = {
    "stages": "",
    "max-triangles": str(DEFAULT_MAX_TRIANGLES),
    "memory-mb": str(DEFAULT_MEMORY_MB),
    "memory-kind": "address-space",
    "measure-address-space": "no",
    "floating-tolerance": "",
    "objects": "no",
    "extras": "",
    "weight-tolerance": str(DEFAULT_WEIGHT_TOLERANCE),
    "natural": "",
    "visibility-seed": "",
    "natural-instances": "*",
    "natural-sizes": "sphere:*",
    "reference-views": "",
    "natural-views": "",
    "reference-frame": "asset",
    "reference-origin": "",
    "views": "front,back,left,right,top,three-quarter",
    "title": "",
    "device": CPU,
    "backends": ",".join(GPU_BACKENDS),
    "gpu-fallback": "no",
    "render-max-triangles": "",
    "res": str(RESOLUTION),
    "samples": str(SAMPLES),
    "closeup-res": "1200",
    "closeup-samples": "16",
    "closeup-title": "",
}


def chosen_stages(text):
    stages = [stage for stage in text.split(",") if stage]
    if not stages or any(stage not in ORDER for stage in stages):
        raise JudgeError("usage", f"--stages takes {', '.join(ORDER)}")
    if [stage for stage in ORDER if stage in stages] != stages:
        raise JudgeError("usage", f"--stages must keep the order {', '.join(ORDER)}")
    return stages


class Progress:
    def __init__(self, path):
        self.path = path

    def mark(self, event, stage, seconds=None, digest=None):
        line = json.dumps({"event": event, "stage": stage, "at": time.time(), "seconds": seconds, "digest": digest}, allow_nan=False) + "\n"

        def append():
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line)

        shared_access(append)


class Context:
    def __init__(self, asset, out_dir, options):
        self.asset = asset
        self.out_dir = out_dir
        self.options = options
        self.scene = None
        self.uv_grid_path = uv_grid_file(out_dir)
        self.limits = None
        self.address_space = None
        self.document = None
        self.device = None
        self.tiles = None
        self.rendered_device = None

    def cap_memory(self):
        memory_bytes = positive_int(self.options["memory-mb"], "memory-mb") * 1024 * 1024
        self.limits = apply_memory_cap(memory_bytes, memory_kind(self.options["memory-kind"]))
        if self.options["measure-address-space"] == "yes" and os.name == "posix":
            self.address_space = cap_address_space(memory_bytes)

    def lift_memory_for_gpu(self, backend):
        if backend != CPU and self.address_space is not None:
            lift_address_space()
            self.address_space = None

    def framing(self):
        if self.document is None:
            self.document = read_measurements(os.path.join(self.out_dir, OUTPUTS["measure"]))
        return self.document

    def load_scene(self):
        if self.scene is not None:
            return
        load_asset(self.asset, positive_int(self.options["max-triangles"], "max-triangles"))
        self.prepare_scene()

    def prepare_scene(self):
        self.scene = bpy.context.scene
        remove_foreign_rig(self.scene)


def measure_stage(context):
    return measure(context.asset, context.options, context.limits, context.uv_grid_path)


STAGES = {"measure": measure_stage, "reference": reference_stage, "views": views_stage, "sheet": sheet_stage, "closeups": closeups_stage}


def stage_files(out_dir, stage):
    files = [OUTPUTS[stage]]
    if stage == "reference":
        folder = os.path.join(out_dir, "silhouettes")
        if os.path.isdir(folder):
            files += [os.path.join("silhouettes", name) for name in sorted(os.listdir(folder))]
    return files


def stage_digest(out_dir, stage, written):
    if stage not in VERIFIED_STAGES:
        return None
    digest = hashlib.sha256()
    for name in stage_files(out_dir, stage):
        digest.update(name.replace(os.sep, "/").encode("utf-8") + b"|")
        data = written if name == OUTPUTS[stage] else read_bytes(os.path.join(out_dir, name))
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def run_stage(context, progress, stage):
    output = os.path.join(context.out_dir, OUTPUTS[stage])
    os.makedirs(os.path.dirname(output), exist_ok=True)
    progress.mark("start", stage)
    started = time.perf_counter()
    try:
        if stage in SCENE_STAGES:
            context.load_scene()
        payload = {"ok": True, **STAGES[stage](context)}
    except JudgeError as error:
        payload = failure_payload(error)
    except MemoryError:
        payload = memory_payload()
    written, payload = write_payload(output, payload)
    progress.mark("end" if payload["ok"] else "failed", stage, round(time.perf_counter() - started, 3), stage_digest(context.out_dir, stage, written))
    if stage == "measure" and payload["ok"]:
        context.prepare_scene()
    return payload


def continues(context, stage, payload, stages):
    if payload["ok"]:
        return True
    if stage != "views":
        return False
    if payload["error"]["code"] == "gpu_unavailable" and context.options["gpu-fallback"] == "yes":
        return False
    context.tiles = None
    if "closeups" in stages:
        stages.remove("closeups")
    return True


def run_stages(context, progress, stages):
    try:
        context.cap_memory()
    except JudgeError as error:
        write_json(os.path.join(context.out_dir, OUTPUTS[stages[0]]), failure_payload(error))
        progress.mark("failed", stages[0], 0.0)
        return
    remaining = list(stages)
    while remaining:
        stage = remaining.pop(0)
        payload = run_stage(context, progress, stage)
        if not continues(context, stage, payload, remaining):
            return


def run_pass(asset, out_dir, options):
    progress = Progress(os.path.join(out_dir, PROGRESS))
    stages = chosen_stages(options["stages"])
    try:
        run_stages(Context(asset, out_dir, options), progress, stages)
        progress.mark("finish", None)
    except FileLockError as error:
        exit_on_lock(error)
