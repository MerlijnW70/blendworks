"""Entry point that builds the LOD package inside Blender."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))

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
from judge_geometry import DEGENERATE_AREA, GEOMETRY_TYPES, triangle_areas, world_coordinates
from judge_load import load_asset
from judge_uv import UvGrid
from package_export import export_glb
from package_levels import LodError, build_lods, lod_name
from package_surface import triangle_soup

USAGE = "package_lods.py -- <asset> <out dir> --config <config.json> [--layout single|separate] [--stem name] [--max-triangles n] [--memory-mb n] [--memory-kind address-space|data]"
LAYOUTS = ("single", "separate")
FOLDER = "uncompressed"


def read_config(path):
    try:
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        raise JudgeError("usage", "the LOD config is missing or malformed") from None
    if not isinstance(config, dict):
        raise JudgeError("usage", "the LOD config must be an object")
    return config


def uv_overlap(objects, depsgraph):
    grid = UvGrid()
    seen = set()
    for obj in objects:
        key = obj.data.as_pointer()
        if key in seen:
            continue
        seen.add(key)
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            areas = triangle_areas(mesh, world_coordinates(mesh, evaluated.matrix_world))
            grid.add_mesh(mesh, areas, DEGENERATE_AREA)
        finally:
            evaluated.to_mesh_clear()
    return round(grid.overlap(), 6)


def source_objects():
    scene = bpy.context.scene
    unsupported = sorted({obj.type for obj in scene.objects if obj.type in GEOMETRY_TYPES and obj.type != "MESH"})
    if unsupported:
        raise JudgeError("unsupported_asset", f"the asset has {', '.join(unsupported)} objects; convert them to meshes first")
    return [obj for obj in scene.objects if obj.type == "MESH"]


def exports(built, out_dir, stem, layout):
    folder = os.path.join(out_dir, FOLDER)
    os.makedirs(folder, exist_ok=True)
    objects = built["objects"]
    if layout == "single":
        path = os.path.join(folder, f"{stem}.glb")
        export_glb(path, [obj for level in sorted(objects) for obj in objects[level]])
        return [{"level": None, "path": f"{FOLDER}/{stem}.glb"}]
    files = []
    for level in sorted(objects):
        name = f"{lod_name(stem, level)}.glb"
        export_glb(os.path.join(folder, name), objects[level])
        files.append({"level": level, "path": f"{FOLDER}/{name}"})
    return files


def lods(asset, out_dir, options):
    layout = options["layout"]
    if layout not in LAYOUTS:
        raise JudgeError("usage", f"--layout must be one of {', '.join(LAYOUTS)}")
    config = read_config(options["config"])
    memory_cap_from(options)
    loaded = load_asset(asset, positive_int(options["max-triangles"], "max-triangles"))
    sources = source_objects()
    stem = options["stem"] or os.path.splitext(os.path.basename(asset))[0]
    timer = stopwatch()
    try:
        built = build_lods(sources, config, rename_source=config.get("count", 0) > 0)
    except LodError as error:
        raise JudgeError(error.code, error.message) from None
    except ValueError as error:
        raise JudgeError("usage", str(error)) from None
    seconds = timer()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for level in built["levels"]:
        level["uvOverlap"] = uv_overlap(built["objects"][level["level"]], depsgraph)
    files = exports(built, out_dir, stem, layout)
    return {
        "stem": stem,
        "layout": layout,
        "format": loaded["format"],
        "diagonal": built["diagonal"],
        "radius": built["radius"],
        "levels": built["levels"],
        "files": files,
        "seconds": seconds,
    }


def main():
    positional, options = split_arguments(
        script_arguments(),
        {
            "config": "",
            "layout": "single",
            "stem": "",
            "max-triangles": str(DEFAULT_MAX_TRIANGLES),
            "memory-mb": str(DEFAULT_MEMORY_MB),
            "memory-kind": "address-space",
        },
    )
    if len(positional) != 2 or not options["config"]:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    asset, out_dir = positional
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    run_guarded(os.path.join(out_dir, "lods.json"), lambda: lods(os.path.abspath(asset), out_dir, options))


main()
