import hashlib
import json
import os

import bpy

from judge_armature import measure_rig
from judge_common import JudgeError, positive_int, read_bytes
from judge_geometry import Measurer
from judge_load import load_asset
from judge_motion import measure_motion
from judge_natural import measure_natural, natural_parts
from judge_skin import measure_skin
from judge_textures import measure_textures

MAX_FLOATING_TOLERANCE = 1.0
EXTRAS = ("rig", "skin", "animation", "colours")
MAX_WEIGHT_TOLERANCE = 0.5


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


def extras_wanted(text):
    wanted = [item for item in text.split(",") if item]
    unknown = [item for item in wanted if item not in EXTRAS]
    if unknown:
        raise JudgeError("usage", f"--extras takes {', '.join(EXTRAS)}, not {', '.join(unknown)}")
    return set(wanted)


def weight_tolerance(text):
    try:
        value = float(text)
    except ValueError:
        raise JudgeError("usage", "--weight-tolerance must be a number") from None
    if not 0 < value <= MAX_WEIGHT_TOLERANCE:
        raise JudgeError("usage", f"--weight-tolerance must be above 0 and at most {MAX_WEIGHT_TOLERANCE}")
    return value


def visibility_seed(text, asset):
    if text:
        return text
    return hashlib.sha256(read_bytes(asset)).hexdigest()


def measure_extras(measurements, asset, file_format, extras, weights, depsgraph):
    scene = bpy.context.scene
    if "rig" in extras:
        measurements["rig"] = measure_rig(scene)
    if "skin" in extras:
        extent = max(measurements["size"])
        measurements["skin"] = measure_skin(scene, asset, file_format, weights, extent, depsgraph)
    if "animation" in extras:
        measurements["animation"] = measure_motion(scene, file_format, measurements["bounds"], measurements["triangles"])


def measure(asset, options, limits, uv_grid_path):
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    tolerance = floating_tolerance(options["floating-tolerance"])
    objects = objects_wanted(options["objects"])
    extras = extras_wanted(options["extras"])
    weights = weight_tolerance(options["weight-tolerance"])
    natural = natural_parts(options["natural"])
    loaded = load_asset(asset, triangle_cap)
    scene = bpy.context.scene
    seed = visibility_seed(options["visibility-seed"], asset)
    measurer = Measurer(triangle_cap, tolerance, integrity=True, objects=objects, colours="colours" in extras, seed=seed)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    measurer.measure(depsgraph)
    measurements = measurer.result()
    measurer.uv_grid.save(uv_grid_path)
    measurements.update(loaded)
    measurements["textures"] = measure_textures(measurer.material_blocks, measurer.faces_without_material, loaded["externalFilesRefused"])
    measurements["objectsAll"] = len(scene.objects)
    measure_extras(measurements, asset, loaded["format"], extras, weights, depsgraph)
    if natural:
        measurements["natural"] = measure_natural(depsgraph, natural, options["natural-instances"], options["natural-sizes"])
    return {"measurements": measurements, "limits": {**limits, "maxTriangles": triangle_cap}}


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
    return {"measurements": measurements, "low": low, "high": high, "origin": origin}


def uv_grid_file(out_dir):
    return os.path.join(out_dir, "uv-grid.bin")
