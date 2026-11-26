import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy
import numpy as np
from mathutils import Vector

from blendworks_bridge import exr_read

FAST = {"denoise": False, "noise_threshold": 0.0, "time_limit": 600.0, "preview": False, "device": "cpu"}
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])


def render(bridge, name, size, samples=4, camera=None, height=None, alpha=False):
    args = dict(FAST)
    if camera is not None:
        args["camera"] = camera
    bridge.ok("render_final", path=name + ".exr", width=size, height=height or size, samples=samples, transparent=alpha, **args)
    pixels = exr_read.read_exr(os.path.join(bridge.workspace, name + ".exr")).stack("", "RGBA" if alpha else "RGB")
    return np.asarray(pixels, dtype=np.float64)


def luminance(pixels):
    return pixels @ LUMINANCE


def fisheye_up(bridge, name="Up", fov=180.0):
    """An equidistant fisheye at the origin looking straight up: the zenith angle grows linearly from the centre."""
    bridge.ok("add_camera", name=name, location=[0.0, 0.0, 1.0], rotation=[180.0, 0.0, 0.0])
    data = bpy.data.objects[name].data
    data.type = "PANO"
    data.panorama_type = "FISHEYE_EQUIDISTANT"
    data.fisheye_fov = math.radians(fov)
    data.clip_end = 1_000_000.0
    return name


def fisheye_directions(size, fov=180.0):
    """World direction of each pixel of fisheye_up, rows from the top of the image, and the zenith angle."""
    centres = (np.arange(size) + 0.5) / size * 2.0 - 1.0
    x, y = np.meshgrid(centres, -centres)
    radius = np.hypot(x, y)
    zenith = radius * math.radians(fov) / 2.0
    azimuth = np.arctan2(y, x)
    direction = np.stack([np.sin(zenith) * np.cos(azimuth), -np.sin(zenith) * np.sin(azimuth), np.cos(zenith)], axis=-1)
    return direction, zenith, radius <= 1.0


def ortho_down(bridge, name, width, height=400.0, centre=(0.0, 0.0)):
    bridge.ok("add_camera", name=name, location=[centre[0], centre[1], height], rotation=[0.0, 0.0, 0.0], orthographic_scale=width)
    bpy.data.objects[name].data.clip_end = 100_000.0
    return name


def angle_between(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def lamp_direction(name="Sun"):
    obj = bpy.data.objects[name]
    return list(obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0)))


def ground(bridge, size=9000.0, albedo=0.3):
    bridge.ok("add_primitive", type="plane", name="Ground", size=size)
    bridge.ok("add_material", name="Grey", base_color=[albedo, albedo, albedo], roughness=1.0)
    bridge.ok("assign_material", name="Ground", material="Grey")
