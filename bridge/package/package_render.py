import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))

import bpy
import numpy as np
from mathutils import Matrix

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
from judge_load import expose_everything, load_asset, run_importer
from judge_rig import VIEWS, Rig, basis, configure_scene, orientation, remove_foreign_rig
from judge_sheet import MARKER, MUTED, TEXT, load_png
from package_metrics import compare_renders
from package_plan import crop_angle, crop_pixels, projected_pixels
from package_sheet import compose_sheet
from package_surface import triangle_soup

USAGE = (
    "package_render.py -- <lods.json> <package dir> <out dir> [--views front,top] [--samples n]"
    " [--device CPU|AUTO|OPTIX|CUDA|HIP|METAL|ONEAPI] [--backends OPTIX,CUDA] [--max-triangles n] [--memory-mb n] [--memory-kind address-space|data]"
)
LEVEL_NAME = re.compile(r"_LOD(\d+)$")
DEFAULT_VIEWS = "front,back,left,right,top,three-quarter"
DEFAULT_SAMPLES = 16
SHEET = "lod-sheet.png"


def read_lods(path):
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        return document["levels"], document["files"]
    except (OSError, ValueError, KeyError, TypeError):
        raise JudgeError("usage", "the LOD record is missing or malformed") from None


def chosen_views(text):
    views = [view for view in text.split(",") if view]
    unknown = [view for view in views if view not in VIEWS]
    if unknown:
        raise JudgeError("usage", f"unknown views: {', '.join(unknown)}")
    return views


def import_package(folder, files, triangle_cap):
    load_asset(os.path.join(folder, files[0]["path"]), triangle_cap)
    for entry in files[1:]:
        run_importer(bpy.ops.import_scene.gltf, filepath=os.path.join(folder, entry["path"]), merge_vertices=True, import_pack_images=False)
    expose_everything(bpy.context.scene)


def group_levels(scene):
    levels = {}
    for obj in scene.objects:
        match = LEVEL_NAME.search(obj.name)
        if obj.type == "MESH" and match:
            levels.setdefault(int(match.group(1)), []).append(obj)
    return levels


def show_only(groups, level):
    for number, objects in groups.items():
        for obj in objects:
            obj.hide_render = number != level


def aim(rig, view, distance, angle):
    towards_viewer, up, _ = VIEWS[view]
    side, upward, depth = basis(towards_viewer, up)
    camera = rig.camera.data
    camera.type = "PERSP"
    camera.sensor_fit = "HORIZONTAL"
    camera.angle = angle
    camera.clip_start = max(distance - rig.radius * 2.0, distance * 1e-3)
    camera.clip_end = distance + rig.radius * 2.0
    rig.camera.matrix_world = Matrix.Translation(rig.centre + depth * distance) @ orientation(side, upward, depth)
    rig.place_lights(side, upward, depth)


def render_view(scene, rig, view, distance, angle, path):
    aim(rig, view, distance, angle)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise JudgeError("render_failed", f"the {view} view did not render")
    pixels, width, height = load_png(path)
    return np.frombuffer(pixels, dtype=np.float32).reshape(height, width, 4).astype(np.float64)


def prepare_scene(scene, samples):
    configure_scene(scene, 256, samples, outlines=False)
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"


def render_level(scene, rig, groups, level, entry, views, out_dir, diameter):
    distance = entry["distance"]
    crop = crop_pixels(projected_pixels(diameter, distance))
    angle = crop_angle(crop)
    scene.render.resolution_x = crop
    scene.render.resolution_y = crop
    results = []
    tiles = {"reference": [], "candidate": []}
    for view in views:
        show_only(groups, 0)
        reference_path = os.path.join(out_dir, f"lod{level}-{view}-lod0.png")
        reference = render_view(scene, rig, view, distance, angle, reference_path)
        show_only(groups, level)
        candidate_path = os.path.join(out_dir, f"lod{level}-{view}-lod{level}.png")
        candidate = render_view(scene, rig, view, distance, angle, candidate_path)
        metrics = compare_renders(reference, candidate)
        results.append({"view": view, "lod0": os.path.basename(reference_path), "lod": os.path.basename(candidate_path), **metrics})
        tiles["reference"].append({"label": view, "pixels": reference})
        tiles["candidate"].append({"label": f"IOU {metrics['silhouetteIou']:.3f} SSIM {metrics['similarity']:.3f}", "pixels": candidate})
    return crop, results, tiles


def package_levels(groups):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    found = []
    for level in sorted(groups):
        soup = triangle_soup(groups[level], depsgraph)
        low, high = soup.bounds()
        found.append(
            {
                "level": level,
                "objects": len(groups[level]),
                "triangles": int(len(soup.triangles)),
                "bounds": {"min": [float(value) for value in low], "max": [float(value) for value in high]},
            }
        )
    return found


def device_text(device):
    if device["backend"] == CPU:
        return "RENDER: CPU"
    return f"RENDER: GPU {device['backend']} ({', '.join(device['devices'])})"


def level_summary(entry, crop, results):
    return {
        "level": entry["level"],
        "distance": entry["distance"],
        "crop": crop,
        "views": results,
        "silhouetteIou": min(item["silhouetteIou"] for item in results),
        "similarity": min(item["similarity"] for item in results),
        "similarityMean": float(np.mean([item["similarity"] for item in results])),
    }


def render(lods_path, folder, out_dir, options):
    views = chosen_views(options["views"])
    samples = positive_int(options["samples"], "samples")
    backend = device_backend(options["device"])
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    memory_cap_from(options)
    found = {"probes": [], "probeSeconds": None}
    if views:
        backend, found = resolve_backend(backend, options["backends"])
    levels, files = read_lods(lods_path)
    import_package(folder, files, triangle_cap)
    scene = bpy.context.scene
    remove_foreign_rig(scene)
    groups = group_levels(scene)
    if not groups:
        groups = {0: [obj for obj in scene.objects if obj.type == "MESH"]}
    expected = {entry["level"] for entry in levels}
    if set(groups) != expected:
        raise JudgeError("package_mismatch", f"the package holds the levels {sorted(groups)}, not {sorted(expected)}")
    measured = package_levels(groups)
    bounds = next(entry for entry in measured if entry["level"] == 0)["bounds"]
    low, high = bounds["min"], bounds["max"]
    diameter = float(np.linalg.norm(np.array(high) - np.array(low)))
    device = None
    rendered = []
    sections = []
    cell = 0
    render_clock = stopwatch()
    if views:
        prepare_scene(scene, samples)
        device = use_device(scene, backend, found)
        rig = Rig(scene, low, high, [(low[axis] + high[axis]) / 2 for axis in range(3)])
        for entry in levels:
            if entry["level"] == 0:
                continue
            crop, results, tiles = render_level(scene, rig, groups, entry["level"], entry, views, out_dir, diameter)
            cell = max(cell, crop)
            rendered.append(level_summary(entry, crop, results))
            title = f"LOD{entry['level']}  {entry['triangles']} TRIS  {entry['distance']:.2f} M  {crop} PX"
            sections.append({"title": title, "rows": [{"tiles": tiles["reference"], "colour": MUTED}, {"tiles": tiles["candidate"], "colour": MARKER}]})
    seconds = render_clock()
    sizes = None
    if sections:
        header = [("LOD CHECK: LOD0 ABOVE, THE LOD BELOW", TEXT), (f"{len(views)} VIEWS   {samples} SAMPLES   {device_text(device)}", MUTED)]
        sizes = compose_sheet(header, sections, cell, os.path.join(out_dir, SHEET))
    return {
        "device": device,
        "probes": found["probes"],
        "package": measured,
        "levels": rendered,
        "sheet": SHEET if sections else None,
        "sheetSize": list(sizes) if sizes else None,
        "samples": samples,
        "timings": {"device": found["probeSeconds"], "render": seconds},
    }


def main():
    positional, options = split_arguments(
        script_arguments(),
        {
            "views": DEFAULT_VIEWS,
            "samples": str(DEFAULT_SAMPLES),
            "device": CPU,
            "backends": ",".join(GPU_BACKENDS),
            "max-triangles": str(DEFAULT_MAX_TRIANGLES),
            "memory-mb": str(DEFAULT_MEMORY_MB),
            "memory-kind": "address-space",
        },
    )
    if len(positional) != 3:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    lods_path, folder, out_dir = positional
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    run_guarded(os.path.join(out_dir, "render.json"), lambda: render(os.path.abspath(lods_path), os.path.abspath(folder), out_dir, options))


main()
