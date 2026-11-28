"""Measures the sky: sun irradiance, hemisphere and luminance with a probe scene."""

import math
import os
import shutil
import tempfile

import bpy
import numpy as np
from mathutils import Vector

from . import exr_read
from .errors import failed

DISC_PIXELS = 48
DISC_FIELD = 2.0
DISC_SAMPLES = 4
PANORAMA_WIDTH = 128
PANORAMA_HEIGHT = 128
PANORAMA_SAMPLES = 4
DOME_COLUMNS = 16
DOME_AZIMUTH_START = 180.0
SKY_FIELDS = ("sky_type", "sun_size", "sun_intensity", "sun_elevation", "sun_rotation", "altitude", "air_density", "aerosol_density", "ozone_density")
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])


def copy_sky(source, target):
    for name in SKY_FIELDS:
        setattr(target, name, getattr(source, name))


class ProbeScene:
    """A private scene that renders only a sky texture, on the CPU, into small EXR files."""

    def __init__(self, sky):
        self.sky_settings = sky
        self.scene = None
        self.folder = None

    def __enter__(self):
        self.folder = tempfile.mkdtemp(prefix="blendworks-sky-")
        scene = bpy.data.scenes.new("blendworks sky probe")
        self.scene = scene
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.use_denoising = False
        scene.cycles.use_adaptive_sampling = False
        scene.cycles.seed = 0
        scene.render.film_transparent = False
        scene.render.use_compositing = False
        scene.render.use_sequencer = False
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "OPEN_EXR"
        scene.render.image_settings.color_depth = "32"
        scene.render.image_settings.color_mode = "RGB"
        scene.cycles.pixel_filter_type = "BOX"
        scene.cycles.filter_width = 1.0
        scene.view_settings.view_transform = "Standard"
        world = bpy.data.worlds.new("blendworks sky probe")
        scene.world = world
        tree = world.node_tree
        tree.nodes.clear()
        self.sky = tree.nodes.new("ShaderNodeTexSky")
        copy_sky(self.sky_settings, self.sky)
        background = tree.nodes.new("ShaderNodeBackground")
        output = tree.nodes.new("ShaderNodeOutputWorld")
        tree.links.new(self.sky.outputs["Color"], background.inputs["Color"])
        tree.links.new(background.outputs["Background"], output.inputs["Surface"])
        camera = bpy.data.cameras.new("blendworks sky probe")
        camera.sensor_width = 36.0
        camera.clip_start = 0.01
        self.camera = bpy.data.objects.new("blendworks sky probe", camera)
        scene.collection.objects.link(self.camera)
        scene.camera = self.camera
        return self

    def __exit__(self, kind, error, trace):
        world = self.scene.world
        camera = self.camera.data
        bpy.data.objects.remove(self.camera, do_unlink=True)
        bpy.data.cameras.remove(camera)
        bpy.data.scenes.remove(self.scene)
        bpy.data.worlds.remove(world)
        shutil.rmtree(self.folder, ignore_errors=True)
        return False

    def render(self, name, width, height, samples):
        scene = self.scene
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.cycles.samples = samples
        path = os.path.join(self.folder, name + ".exr")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True, scene=scene.name)
        if not os.path.isfile(path):
            raise failed("the sky probe render wrote no image")
        image = exr_read.read_exr(path)
        layer = next((prefix for prefix in ("", "ViewLayer.Combined.", "Combined.") if image.has(prefix + "R")), None)
        if layer is None:
            raise failed("the sky probe image has no colour channels")
        return np.asarray(image.stack(layer, "RGB"), dtype=np.float64)


def sun_irradiance(probe, sun_vector):
    """Irradiance of the sky's own sun disc at normal incidence, in the sky's units: the disc on minus the disc off."""
    data = probe.camera.data
    data.type = "PERSP"
    field = math.radians(DISC_FIELD)
    data.lens = data.sensor_width / 2.0 / math.tan(field / 2.0)
    probe.camera.rotation_mode = "QUATERNION"
    probe.camera.rotation_quaternion = Vector(sun_vector).to_track_quat("-Z", "Y")
    probe.sky.sun_disc = True
    lit = probe.render("disc", DISC_PIXELS, DISC_PIXELS, DISC_SAMPLES)
    probe.sky.sun_disc = False
    unlit = probe.render("sky", DISC_PIXELS, DISC_PIXELS, DISC_SAMPLES)
    pixel = field / DISC_PIXELS
    return np.maximum((lit - unlit).sum(axis=(0, 1)) * pixel * pixel, 0.0)


def hemisphere(probe):
    """Horizontal irradiance, mean radiance, the horizon radiance of the sky without its sun disc, and its upper half as a
    coarse dome: rows from the zenith down to the horizon, columns from azimuth 180 degrees eastwards round (see
    dome_azimuth)."""
    data = probe.camera.data
    data.type = "PANO"
    data.panorama_type = "EQUIRECTANGULAR"
    probe.camera.rotation_mode = "XYZ"
    probe.camera.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    probe.sky.sun_disc = False
    pixels = probe.render("panorama", PANORAMA_WIDTH, PANORAMA_HEIGHT, PANORAMA_SAMPLES)
    rows = pixels.shape[0]
    latitude = math.pi / 2.0 - (np.arange(rows) + 0.5) / rows * math.pi
    upper = latitude > 0.0
    band = (math.pi / rows) * (2.0 * math.pi / pixels.shape[1])
    solid = np.cos(latitude) * band
    cosine = np.sin(np.maximum(latitude, 0.0))
    row_means = pixels.mean(axis=1)
    sums = pixels.sum(axis=1)
    irradiance = (sums * (solid * cosine)[:, None]).sum(axis=0)
    mean = (sums[upper] * solid[upper][:, None]).sum(axis=0) / (solid[upper].sum() * pixels.shape[1])
    horizon_rows = upper & (latitude < math.radians(12.0))
    horizon = row_means[horizon_rows].mean(axis=0)
    zenith = row_means[0]
    dome = pixels[upper].reshape(int(upper.sum()), DOME_COLUMNS, -1, 3).mean(axis=2)
    return irradiance, mean, horizon, zenith, dome


def measure(sky, sun_vector):
    with ProbeScene(sky) as probe:
        sun = sun_irradiance(probe, sun_vector)
        irradiance, mean, horizon, zenith, dome = hemisphere(probe)
    return {"sun_rgb": sun, "sky_irradiance": irradiance, "sky_mean": mean, "horizon": horizon, "zenith": zenith, "dome": dome.ravel()}


def dome_radiance(dome, rows, directions):
    """Sky radiance of a stored dome (flat list, rows from the zenith to the horizon) along world directions, bilinear;
    directions below the horizon read the horizon row."""
    dome = np.asarray(dome, dtype=np.float64).reshape(rows, DOME_COLUMNS, 3)
    directions = np.asarray(directions, dtype=np.float64)
    elevation = np.degrees(np.arcsin(np.clip(directions[..., 2], 0.0, 1.0)))
    azimuth = np.degrees(np.arctan2(directions[..., 0], directions[..., 1]))
    row = np.clip((90.0 - elevation) / 90.0 * rows - 0.5, 0.0, rows - 1.0)
    column = (((azimuth - DOME_AZIMUTH_START) / 360.0) % 1.0) * DOME_COLUMNS - 0.5
    r0 = np.floor(row).astype(int)
    r1 = np.minimum(r0 + 1, rows - 1)
    c0 = np.floor(column).astype(int) % DOME_COLUMNS
    c1 = (c0 + 1) % DOME_COLUMNS
    fr = (row - np.floor(row))[..., None]
    fc = (column - np.floor(column))[..., None]
    top = dome[r0, c0] * (1.0 - fc) + dome[r0, c1] * fc
    bottom = dome[r1, c0] * (1.0 - fc) + dome[r1, c1] * fc
    return top * (1.0 - fr) + bottom * fr


def luminance(rgb):
    return float(np.dot(np.asarray(rgb, dtype=np.float64), LUMINANCE))


def lamp_colour(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    peak = float(rgb.max())
    if peak <= 0.0:
        return [1.0, 1.0, 1.0], 0.0
    return [round(float(value), 6) for value in rgb / peak], peak
