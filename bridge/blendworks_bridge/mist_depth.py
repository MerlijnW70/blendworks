"""Valley mist in the depth method of atmosphere: when the haze is applied per pixel from the depth pass, the mist volumes
are left out of the render and their optical depth is summed along each camera ray instead, in even steps through the
part of the ray inside the mist's box and in front of the surface, from the same low-ground map the volume reads. The
mist's breakup noise is a shader noise and is left out; the colour becomes colour * T + airlight * (1 - T)."""
import json

import bpy
import numpy
from mathutils import Vector

from .valley_mist import FLAG, PROPERTY, TOP_IMAGE_SUFFIX, density

STEPS = 48
ROWS = 64


def mist_objects(scene):
    return [obj for obj in scene.objects if obj.get(FLAG) and not obj.hide_render and isinstance(obj.get(PROPERTY), str)]


def top_grid(obj):
    image = bpy.data.images.get(obj.name + TOP_IMAGE_SUFFIX)
    if image is None:
        return None
    width, height = image.size
    pixels = numpy.empty(width * height * 4, dtype=numpy.float32)
    image.pixels.foreach_get(pixels)
    return pixels.reshape(height, width, 4)[..., :2].astype(numpy.float64)


def box_of(obj):
    corners = numpy.array([list(obj.matrix_world @ Vector(corner)) for corner in obj.bound_box])
    return corners.min(axis=0), corners.max(axis=0)


def apply(rgb, origin, directions, distance, airlight, scene, box_span):
    """rgb with every visible valley mist laid over it along the rays."""
    for obj in mist_objects(scene):
        settings = json.loads(obj[PROPERTY])
        grid = top_grid(obj)
        if grid is None:
            continue
        low, high = box_of(obj)
        enter, leave = box_span(origin, directions, low, high)
        far = numpy.minimum(leave, distance)
        depth = numpy.zeros(distance.shape)
        for start in range(0, distance.shape[0], ROWS):
            rows = slice(start, start + ROWS)
            near_part, far_part = enter[rows], far[rows]
            step = numpy.maximum(far_part - near_part, 0.0) / STEPS
            for index in range(STEPS):
                reach = near_part + (index + 0.5) * step
                points = origin + directions[rows] * reach[..., None]
                flat = points.reshape(-1, 3)
                depth[rows] += density(settings, grid, flat[:, :2], flat[:, 2]).reshape(reach.shape) * step
        through = numpy.exp(-depth)[..., None].astype(numpy.float32)
        rgb = rgb * through + numpy.asarray(airlight, dtype=numpy.float32) * numpy.asarray(settings["tint"], dtype=numpy.float32) * (1.0 - through)
    return rgb
