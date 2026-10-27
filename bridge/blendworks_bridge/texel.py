import contextlib
import math

import bpy

from .errors import bad_args
from .operators import only_selected, operator_context
from .util import rounded

TINY_AREA = 1e-12


def uv_area(points):
    total = 0.0
    for index in range(1, len(points) - 1):
        a, b, c = points[0], points[index], points[index + 1]
        total += abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2.0
    return total


def world_area(points):
    total = 0.0
    for index in range(1, len(points) - 1):
        total += (points[index] - points[0]).cross(points[index + 1] - points[0]).length / 2.0
    return total


def face_areas(obj, layer):
    mesh = obj.data
    matrix = obj.matrix_world
    world = [matrix @ vertex.co for vertex in mesh.vertices]
    areas = []
    for polygon in mesh.polygons:
        uvs = [layer.data[index].uv for index in polygon.loop_indices]
        corners = [world[index] for index in polygon.vertices]
        areas.append((uv_area(uvs), world_area(corners)))
    return areas


def density(obj, layer, texture_size):
    areas = face_areas(obj, layer)
    total_uv = sum(item[0] for item in areas)
    total_world = sum(item[1] for item in areas)
    faces = [texture_size * math.sqrt(uv / area) for uv, area in areas if area > TINY_AREA]
    if total_world <= TINY_AREA or not faces:
        return {"texture_size": texture_size, "mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "texture_size": texture_size,
        "mean": rounded(texture_size * math.sqrt(total_uv / total_world), 3),
        "min": rounded(min(faces), 3),
        "max": rounded(max(faces), 3),
    }


def mean_density(obj, layer, texture_size):
    areas = face_areas(obj, layer)
    total_uv = sum(item[0] for item in areas)
    total_world = sum(item[1] for item in areas)
    if total_uv <= 0.0 or total_world <= TINY_AREA:
        raise bad_args(f"{obj.name} has no UV or surface area to measure a texel density on")
    return texture_size * math.sqrt(total_uv / total_world)


def scale_uvs(obj, layer, factor):
    for item in layer.data:
        item.uv = (item.uv[0] * factor, item.uv[1] * factor)
    obj.data.update()


def scale_to_density(obj, layer, target, texture_size):
    factor = target / mean_density(obj, layer, texture_size)
    scale_uvs(obj, layer, factor)
    return factor


@contextlib.contextmanager
def multi_edit_mode(view_layer, objects):
    active = objects[0]
    with only_selected(view_layer, active, objects):
        with bpy.context.temp_override(**operator_context(active, objects)):
            bpy.ops.object.mode_set(mode="EDIT")
            try:
                bpy.ops.mesh.reveal()
                bpy.ops.mesh.select_all(action="SELECT")
                yield
            finally:
                bpy.ops.object.mode_set(mode="OBJECT")


def average_island_scale(view_layer, objects):
    with multi_edit_mode(view_layer, objects):
        bpy.ops.uv.average_islands_scale(scale_uv=False, shear=False)


def pack(view_layer, objects, margin, rotate, scale):
    with multi_edit_mode(view_layer, objects):
        bpy.ops.uv.pack_islands(
            udim_source="CLOSEST_UDIM",
            rotate=rotate,
            rotate_method="ANY",
            scale=scale,
            margin_method="FRACTION",
            margin=margin,
            shape_method="CONCAVE",
        )
    for obj in objects:
        obj.data.update()
