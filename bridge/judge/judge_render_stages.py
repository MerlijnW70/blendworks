"""Render stages: views, silhouettes and cutouts."""

import math
import os

import bpy

from judge_closeup import compose_closeups, render_shots, world_points
from judge_common import JudgeError, positive_int, rounded, stopwatch
from judge_device import CPU, apply_device, device_backend, resolve_backend, use_device
from judge_geometry import measured_frame
from judge_load import MEASURE_FRAME
from judge_rig import RESOLUTION, SAMPLES, STAMPS, VIEWS, Rig, configure_scene
from judge_sheet import MARKER, MUTED, TEXT, compose, load_png, texture_line, uv_tile
from judge_stage_scene import stage_scene
from judge_uv import UvGrid

SILHOUETTE_SIZES = (16, 2048)
FILTER_WIDTH = 0.01
CLOSEUP_LIMITS = {"res": 4096, "samples": 4096}
CLOSEUPS_FOLDER = "closeups"
CLOSEUP_SHEET = "closeup-sheet.png"
NATURAL_PREFIX = "natural-"
NATURAL_TRANSPARENT_BOUNCES = 64


def chosen_views(text):
    views = [view for view in text.split(",") if view]
    unknown = [view for view in views if view not in VIEWS]
    if unknown or not views:
        raise JudgeError("usage", f"unknown views: {', '.join(unknown) or 'none given'}")
    return views


def silhouette_views(text):
    views = []
    low, high = SILHOUETTE_SIZES
    for item in [part for part in text.split(",") if part]:
        view, _, size = item.partition(":")
        if view not in VIEWS or view in (entry[0] for entry in views):
            raise JudgeError("usage", f"unknown or repeated view {view}")
        try:
            pixels = int(size)
        except ValueError:
            raise JudgeError("usage", f"the size of the {view} view must be a whole number") from None
        if not low <= pixels <= high:
            raise JudgeError("usage", f"the size of the {view} view must be {low} to {high} pixels")
        views.append((view, pixels))
    return views


def numbers(text, count, name):
    try:
        values = [float(part) for part in text.split(",")]
    except ValueError:
        raise JudgeError("usage", f"--{name} must be {count} numbers") from None
    if len(values) != count or not all(math.isfinite(value) for value in values):
        raise JudgeError("usage", f"--{name} must be {count} finite numbers")
    return values


def reference_framing(context, text, origin_text, triangle_cap):
    if text == "measured":
        framing = context.framing()
        return framing["low"], framing["high"], framing["origin"]
    if text == "asset":
        frame = measured_frame(bpy.context.evaluated_depsgraph_get(), triangle_cap)
        return frame["min"], frame["max"], frame["origin"]
    values = numbers(text, 6, "reference-frame")
    low, high = values[:3], values[3:]
    if any(low[axis] > high[axis] for axis in range(3)):
        raise JudgeError("usage", "--reference-frame needs the low corner first")
    origin = numbers(origin_text, 3, "reference-origin") if origin_text else [(low[axis] + high[axis]) / 2 for axis in range(3)]
    return low, high, origin


def configure_silhouettes(scene):
    scene.render.engine = "CYCLES"
    apply_device(scene, CPU)
    cycles = scene.cycles
    cycles.samples = 1
    cycles.use_adaptive_sampling = False
    cycles.seed = 0
    cycles.use_animated_seed = False
    cycles.use_denoising = False
    cycles.pixel_filter_type = "BOX"
    cycles.filter_width = FILTER_WIDTH
    cycles.max_bounces = 0
    cycles.transparent_max_bounces = 0
    scene.render.film_transparent = True
    scene.render.resolution_percentage = 100
    scene.render.dither_intensity = 0.0
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.use_freestyle = False
    for stamp in STAMPS:
        setattr(scene.render, stamp, False)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    material = bpy.data.materials.new("judge-silhouette")
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    scene.view_layers[0].material_override = material
    scene.frame_set(MEASURE_FRAME)


def render_silhouettes(scene, rig, views, folder, prefix):
    rendered = []
    for view, size in views:
        scene.render.resolution_x = size
        scene.render.resolution_y = size
        path = os.path.join(folder, f"{prefix}{view}.png")
        rig.render(view, path)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise JudgeError("render_failed", f"the {prefix}{view} silhouette did not render")
        rendered.append({"view": view, "path": path, "size": size})
    return rendered


def honour_cutouts(scene):
    scene.view_layers[0].material_override = None
    scene.cycles.transparent_max_bounces = NATURAL_TRANSPARENT_BOUNCES


def natural_rig(context, scene):
    framing = context.framing()
    centre = [(framing["low"][axis] + framing["high"][axis]) / 2 for axis in range(3)]
    return Rig(scene, framing["low"], framing["high"], centre)


def reference_stage(context):
    options = context.options
    views = silhouette_views(options["reference-views"])
    natural = silhouette_views(options["natural-views"])
    if not views and not natural:
        raise JudgeError("usage", "--reference-views and --natural-views name no view")
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    with stage_scene(context.scene, "judge-silhouettes") as scene:
        configure_silhouettes(scene)
        folder = os.path.join(context.out_dir, "silhouettes")
        os.makedirs(folder, exist_ok=True)
        result = {"views": []}
        if views:
            low, high, origin = reference_framing(context, options["reference-frame"], options["reference-origin"], triangle_cap)
            rig = Rig(scene, low, high, origin)
            result["views"] = render_silhouettes(scene, rig, views, folder, "")
            result["frame"] = {"min": rounded(list(rig.low)), "max": rounded(list(rig.high))}
        if natural:
            rig = natural_rig(context, scene)
            honour_cutouts(scene)
            result["natural"] = render_silhouettes(scene, rig, natural, folder, NATURAL_PREFIX)
            result["naturalFrame"] = {"min": rounded(list(rig.low)), "max": rounded(list(rig.high))}
            result.setdefault("frame", result["naturalFrame"])
        return result


def chosen_device(context):
    if context.device is not None:
        return context.device
    backend = device_backend(context.options["device"])
    context.lift_memory_for_gpu(backend)
    timer = stopwatch()
    backend, found = resolve_backend(backend, context.options["backends"])
    context.device = {"backend": backend, "found": found, "seconds": timer()}
    return context.device


def views_stage(context):
    options = context.options
    views = chosen_views(options["views"])
    resolution = min(positive_int(options["res"], "res"), RESOLUTION)
    samples = min(positive_int(options["samples"], "samples"), SAMPLES)
    framing = context.framing()
    if options["render-max-triangles"]:
        budget = positive_int(options["render-max-triangles"], "render-max-triangles")
        if framing["measurements"]["triangles"] > budget:
            raise JudgeError("over_budget", f"over the render budget: {framing['measurements']['triangles']} triangles, at most {budget}")
    chosen = chosen_device(context)
    found = chosen["found"]
    tiles = []
    rendered = []
    views_time = stopwatch()
    with stage_scene(context.scene, "judge-views") as scene:
        configure_scene(scene, resolution, samples)
        device = use_device(scene, chosen["backend"], found)
        rig = Rig(scene, framing["low"], framing["high"], framing["origin"])
        view_dir = os.path.join(context.out_dir, "views")
        os.makedirs(view_dir, exist_ok=True)
        for view in views:
            path = os.path.join(view_dir, f"{view}.png")
            rig.render(view, path)
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise JudgeError("render_failed", f"the {view} view did not render")
            pixels, width, _ = load_png(path)
            width_metres = rig.tile_width(view)
            label = view if width_metres is None else f"{view}  {width_metres:.2f} M ACROSS"
            tiles.append({"label": label, "pixels": pixels, "size": width, "marker": rig.project(framing["origin"])})
            rendered.append({"view": view, "path": path})
    context.tiles = tiles
    context.rendered_device = device
    return {"views": rendered, "device": device, "probes": found["probes"], "timings": {"device": found["probeSeconds"], "views": views_time()}}


def header_lines(title, measurements, preview):
    size = measurements["size"]
    summary = (
        f"{measurements['triangles']} TRIS   {size[0]:.3f} X {size[1]:.3f} X {size[2]:.3f} M   "
        f"{measurements['materials']['count']} MATERIALS   {measurements['objects']} OBJECTS"
    )
    legend = "PREVIEW: VIEWS SKIPPED   UV LAYOUT: GREY USED, RED OVERLAP" if preview else "+ ORIGIN   UV LAYOUT: GREY USED, RED OVERLAP"
    return [(title, TEXT), (summary, MUTED), (texture_line(measurements.get("textures")), MUTED), (legend, MARKER)]


def sheet_stage(context):
    sheet_time = stopwatch()
    preview = context.tiles is None
    measurements = context.framing()["measurements"]
    grid = UvGrid.load(context.uv_grid_path)
    tiles = list(context.tiles or [])
    pixels, size, _ = uv_tile(grid)
    tiles.append({"label": "uv layout", "pixels": pixels, "size": size})
    sheet = os.path.join(context.out_dir, "contact-sheet.png")
    title = context.options["title"] or os.path.basename(context.asset)
    width, height = compose(tiles, header_lines(title, measurements, preview), sheet)
    return {"contactSheet": sheet, "contactSheetSize": [width, height], "preview": preview, "timings": {"sheet": sheet_time()}}


def bounded(text, name, highest):
    value = positive_int(text, name)
    if value > highest:
        raise JudgeError("usage", f"--{name} must be at most {highest}")
    return value


def device_text(device):
    if device["backend"] == CPU:
        return "RENDER: CPU"
    return f"RENDER: GPU {device['backend']} ({', '.join(device['devices'])})"


def closeups_stage(context):
    options = context.options
    resolution = bounded(options["closeup-res"], "closeup-res", CLOSEUP_LIMITS["res"])
    samples = bounded(options["closeup-samples"], "closeup-samples", CLOSEUP_LIMITS["samples"])
    triangle_cap = positive_int(options["max-triangles"], "max-triangles")
    chosen = chosen_device(context)
    found = chosen["found"]
    folder = os.path.join(context.out_dir, CLOSEUPS_FOLDER)
    os.makedirs(folder, exist_ok=True)
    with stage_scene(context.scene, "judge-closeups") as scene:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        measured = measured_frame(depsgraph, triangle_cap)
        points = world_points(depsgraph)
        configure_scene(scene, resolution, samples, outlines=False)
        device = use_device(scene, chosen["backend"], found)
        rig = Rig(scene, measured["min"], measured["max"], measured["origin"])
        render_time = stopwatch()
        images = render_shots(rig, points, folder)
        for image in images:
            if not os.path.isfile(image["path"]) or os.path.getsize(image["path"]) == 0:
                raise JudgeError("render_failed", f"the {image['name']} close-up did not render")
        render_seconds = render_time()
    sheet_time = stopwatch()
    size = measured["size"]
    title = options["closeup-title"] or os.path.basename(context.asset)
    header = [
        (title, TEXT),
        (f"{measured['triangles']} TRIS   {size[0]:.3f} X {size[1]:.3f} X {size[2]:.3f} M   {measured['objects']} OBJECTS", MUTED),
        (f"CLOSE-UPS {resolution} PX   {samples} SAMPLES   DENOISED   {device_text(device)}", MARKER),
    ]
    sheet = os.path.join(folder, CLOSEUP_SHEET)
    width, height = compose_closeups(images, resolution, header, sheet)
    return {
        "images": images,
        "sheet": sheet,
        "sheetSize": [width, height],
        "device": device,
        "probes": found["probes"],
        "timings": {"device": found["probeSeconds"], "render": render_seconds, "sheet": sheet_time()},
    }
