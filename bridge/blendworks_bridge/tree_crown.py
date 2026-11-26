import os
import tempfile
import bpy
import numpy
from mathutils import Vector

VIEWS = {"front": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0), "left": (-1.0, 0.0, 0.0), "right": (1.0, 0.0, 0.0)}
RESOLUTION = 256
SAMPLES = 16
CELLS_ACROSS = 32
OCCUPIED = 0.05
CROWN_WIDTH_SHARE = 0.25
FRAME_MARGIN = 1.08
FILL_BAND = (0.41, 0.73)
FOLIAGE_BAND = (0.317, 0.655)


def measured_objects(names):
    found = []
    pending = [bpy.data.objects[name] for name in names]
    while pending:
        obj = pending.pop()
        if obj in found:
            continue
        if obj.type in ("MESH", "CURVE") and not obj.hide_render:
            found.append(obj)
        pending.extend(obj.children)
    return found


def world_bounds(objects):
    corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    points = numpy.array([list(corner) for corner in corners])
    return points.min(axis=0), points.max(axis=0)


def spans(occupied):
    filled = numpy.zeros_like(occupied)
    for row in range(occupied.shape[0]):
        columns = numpy.flatnonzero(occupied[row])
        if len(columns):
            filled[row, columns[0] : columns[-1] + 1] = True
    return filled


def silhouette_region(occupied):
    return spans(occupied) & spans(occupied.T).T


def crown_rows(region):
    widths = region.sum(axis=1)
    widest = int(numpy.argmax(widths))
    limit = CROWN_WIDTH_SHARE * widths[widest]
    top = widest
    while top > 0 and widths[top - 1] >= limit:
        top -= 1
    bottom = widest
    while bottom + 1 < len(widths) and widths[bottom + 1] >= limit:
        bottom += 1
    return top, bottom


def cell_size(mask):
    columns_used = numpy.flatnonzero(mask.any(axis=0))
    return max(2, int(round((columns_used[-1] - columns_used[0] + 1) / CELLS_ACROSS)))


def coverage_cells(alpha, mask, cell):
    rows_used = numpy.flatnonzero(mask.any(axis=1))
    columns_used = numpy.flatnonzero(mask.any(axis=0))
    top, left = rows_used[0], columns_used[0]
    height = (rows_used[-1] - top) // cell + 1
    width = (columns_used[-1] - left) // cell + 1
    padded = numpy.zeros((height * cell, width * cell))
    window = alpha[top : top + height * cell, left : left + width * cell]
    padded[: window.shape[0], : window.shape[1]] = window
    return padded.reshape(height, cell, width, cell).mean(axis=(1, 3))


def silhouette_fill(alpha, foliage=None):
    mask = alpha >= OCCUPIED
    if not mask.any():
        return {"fill": 0.0, "cells": 0, "holes": 0, "foliage_fill": 0.0}
    cell = cell_size(mask)
    coverage = coverage_cells(alpha, mask, cell)
    occupied = coverage >= OCCUPIED
    region = silhouette_region(occupied)
    first, last = crown_rows(region)
    crown = numpy.zeros_like(region)
    crown[first : last + 1] = region[first : last + 1]
    holes = int((crown & ~occupied).sum())
    found = {"fill": round(float(coverage[crown].mean()), 4), "cells": int(crown.sum()), "holes": holes}
    only = coverage_cells(foliage, mask, cell) if foliage is not None else coverage
    found["foliage_fill"] = round(float(only[crown].mean()), 4)
    return found


def setup_scene(objects, resolution, samples):
    scene = bpy.data.scenes.new("blendworks-crown")
    for obj in objects:
        scene.collection.objects.link(obj)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    scene.cycles.seed = 0
    scene.cycles.max_bounces = 0
    scene.cycles.transparent_max_bounces = 64
    scene.render.film_transparent = True
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    return scene


def render_alpha(scene, camera, folder, view):
    scene.camera = camera
    scene.render.filepath = os.path.join(folder, f"{view}.png")
    bpy.ops.render.render(write_still=True, scene=scene.name)
    image = bpy.data.images.load(scene.render.filepath)
    try:
        width, height = image.size
        pixels = numpy.empty(width * height * 4, dtype=numpy.float32)
        image.pixels.foreach_get(pixels)
    finally:
        bpy.data.images.remove(image)
    return pixels.reshape(height, width, 4)[::-1, :, 3]


def holdout_material():
    material = bpy.data.materials.new("blendworks-crown-holdout")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    clear = nodes.new("ShaderNodeBsdfTransparent")
    material.node_tree.links.new(clear.outputs["BSDF"], output.inputs["Surface"])
    return material


def keep_foliage_only(objects, is_foliage):
    """Blank every material slot that is not foliage; returns what to put back."""
    blank = holdout_material()
    swapped = []
    hidden = []
    for obj in objects:
        slots = [slot for slot in obj.material_slots if is_foliage(slot.material)]
        if not slots:
            hidden.append((obj, obj.hide_render))
            obj.hide_render = True
            continue
        for slot in obj.material_slots:
            if slot not in slots:
                swapped.append((slot, slot.material))
                slot.material = blank
    return blank, swapped, hidden


def restore_foliage(blank, swapped, hidden):
    for slot, material in reversed(swapped):
        slot.material = material
    for obj, state in hidden:
        obj.hide_render = state
    bpy.data.materials.remove(blank)


def render_views(scene, objects, size, centre, resolution, folder, tag):
    cameras = []
    alphas = {}
    try:
        for view, direction in VIEWS.items():
            data = bpy.data.cameras.new(f"blendworks-crown-{view}")
            data.type = "ORTHO"
            data.ortho_scale = size
            data.clip_end = 4.0 * size
            camera = bpy.data.objects.new(data.name, data)
            cameras.append(camera)
            scene.collection.objects.link(camera)
            towards = Vector(direction)
            camera.location = Vector(centre.tolist()) + towards * 2.0 * size
            camera.rotation_euler = (-towards).to_track_quat("-Z", "Y").to_euler()
            alphas[view] = render_alpha(scene, camera, folder, f"{tag}-{view}")
    finally:
        for camera in cameras:
            data = camera.data
            bpy.data.objects.remove(camera)
            bpy.data.cameras.remove(data)
    return alphas


def crown_fill(names, is_foliage=None, resolution=RESOLUTION, samples=SAMPLES):
    """Render the crown from four sides; `fill` counts everything, `foliage_fill` only what is_foliage(material) accepts."""
    objects = measured_objects(names)
    if not objects:
        return {"fill": 0.0, "foliage_fill": 0.0, "views": {}}
    low, high = world_bounds(objects)
    centre = 0.5 * (low + high)
    size = float((high - low).max()) * FRAME_MARGIN
    scene = setup_scene(objects, resolution, samples)
    views = {}
    try:
        with tempfile.TemporaryDirectory() as folder:
            everything = render_views(scene, objects, size, centre, resolution, folder, "all")
            leafy = None
            if is_foliage is not None:
                kept = keep_foliage_only(objects, is_foliage)
                try:
                    leafy = render_views(scene, objects, size, centre, resolution, folder, "foliage")
                finally:
                    restore_foliage(*kept)
            for view, alpha in everything.items():
                views[view] = silhouette_fill(alpha, None if leafy is None else leafy[view])
    finally:
        bpy.data.scenes.remove(scene)
    return {
        "fill": round(float(numpy.mean([entry["fill"] for entry in views.values()])), 4),
        "foliage_fill": round(float(numpy.mean([entry["foliage_fill"] for entry in views.values()])), 4),
        "views": views,
    }


def crown_report(ctx, names, foliage_material=None):
    is_foliage = None if foliage_material is None else (lambda material: material == foliage_material)
    measured = crown_fill(names, is_foliage)
    measured["band"] = list(FILL_BAND)
    measured["within_band"] = FILL_BAND[0] <= measured["fill"] <= FILL_BAND[1]
    measured["foliage_band"] = list(FOLIAGE_BAND)
    measured["foliage_within_band"] = FOLIAGE_BAND[0] <= measured["foliage_fill"] <= FOLIAGE_BAND[1]
    return measured
