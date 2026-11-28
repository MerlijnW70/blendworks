"""Render helpers for rock tests: orthographic cameras, Cycles passes and AOVs, and petrographic measures of colour."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy
import numpy

from blendworks_bridge import exr_read

LUMINANCE = numpy.array([0.2126, 0.7152, 0.0722])
DARK_SHARE = 0.35
LIGHT_SHARE = 1.25


def ortho_camera(name, location, rotation, scale, resolution):
    scene = bpy.context.scene
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = scale
    data.clip_end = 100.0
    camera = bpy.data.objects.new(name, data)
    scene.collection.objects.link(camera)
    camera.location = location
    camera.rotation_euler = [numpy.radians(value) for value in rotation]
    scene.camera = camera
    scene.render.resolution_x = scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    return camera


def render_passes(folder, name, aovs=(), diffuse_color=False, samples=4):
    """Render the scene's camera with Cycles on the CPU into a multilayer EXR and return its channels by name; aovs are
    float AOVs the materials write."""
    scene = bpy.context.scene
    layer = bpy.context.view_layer
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.seed = 0
    scene.cycles.filter_width = 0.01
    layer.use_pass_diffuse_color = diffuse_color
    for aov in aovs:
        if aov not in layer.aovs:
            entry = layer.aovs.add()
            entry.name = aov
            entry.type = "VALUE"
    settings = scene.render.image_settings
    settings.media_type = "MULTI_LAYER_IMAGE"
    settings.file_format = "OPEN_EXR_MULTILAYER"
    settings.color_depth = "32"
    path = os.path.join(folder, f"{name}.exr")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    image = exr_read.read_exr(path)
    prefix = layer.name + "."
    return {key[len(prefix):]: value for key, value in image.channels.items() if key.startswith(prefix)}


def mineral_statistics(albedo, millimetres_per_pixel):
    """Petrographic measures of a rock colour image (linear RGB): each pixel is a light, middle or dark mineral by its
    luminance against the median (dark under DARK_SHARE of it, light above LIGHT_SHARE of it); the colour index is the share
    of dark minerals; the grain size is 1.5 times the mean lineal intercept along the rows, the length between changes of
    mineral (Fullman 1953, for grains of random shape); the contrast is the 90th over the 5th percentile of luminance."""
    luminance = albedo[..., :3] @ LUMINANCE
    median = float(numpy.median(luminance))
    classes = numpy.digitize(luminance, [DARK_SHARE * median, LIGHT_SHARE * median])
    changes = int((classes[:, 1:] != classes[:, :-1]).sum())
    intercept = classes.size / max(changes, 1) * millimetres_per_pixel
    return {"colour_index": float((classes == 0).mean()), "grain_mm": 1.5 * intercept,
            "contrast": float(numpy.percentile(luminance, 90) / max(numpy.percentile(luminance, 5), 1e-6)), "luminance": float(luminance.mean())}
