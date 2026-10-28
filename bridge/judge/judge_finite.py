from math import isfinite

import bpy
import numpy as np

from judge_common import JudgeError, quoted


def all_finite(collection, attribute, width):
    values = np.empty(len(collection) * width, dtype=np.float32)
    if values.size == 0:
        return True
    collection.foreach_get(attribute, values)
    return bool(np.isfinite(values).all())


def matrix_finite(matrix):
    return all(isfinite(value) for row in matrix for value in row)


def refuse(kind, owner):
    raise JudgeError("non_finite", f"the asset has a non-finite {kind} (NaN or infinity) in {quoted(owner)}; the judge refuses it before measuring")


def check_objects(scene):
    for obj in scene.objects:
        for name in ("matrix_world", "matrix_basis", "matrix_parent_inverse"):
            if not matrix_finite(getattr(obj, name)):
                refuse("object matrix", obj.name)
        transforms = (*obj.delta_location, *obj.delta_scale, *obj.delta_rotation_euler, *obj.delta_rotation_quaternion)
        if not all(isfinite(value) for value in transforms):
            refuse("object matrix", obj.name)


def check_meshes():
    for mesh in bpy.data.meshes:
        if not all_finite(mesh.vertices, "co", 3):
            refuse("vertex", mesh.name)
        for layer in mesh.uv_layers:
            if not all_finite(layer.uv, "vector", 2):
                refuse("UV", f"{mesh.name}/{layer.name}")
        if mesh.shape_keys is not None:
            for block in mesh.shape_keys.key_blocks:
                if not all_finite(block.data, "co", 3):
                    refuse("shape key vertex", f"{mesh.name}/{block.name}")


def check_curves():
    for curve in bpy.data.curves:
        for spline in getattr(curve, "splines", []):
            if not all_finite(spline.points, "co", 4):
                refuse("curve point", curve.name)
            for attribute in ("co", "handle_left", "handle_right"):
                if not all_finite(spline.bezier_points, attribute, 3):
                    refuse("curve point", curve.name)
    for meta in bpy.data.metaballs:
        if not all_finite(meta.elements, "co", 3) or not all_finite(meta.elements, "radius", 1):
            refuse("metaball element", meta.name)


def check_finite(scene):
    check_objects(scene)
    check_meshes()
    check_curves()


def check_world(world, matrix, label):
    if not matrix_finite(matrix):
        refuse("object matrix", label)
    for point in world:
        if not (isfinite(point[0]) and isfinite(point[1]) and isfinite(point[2])):
            refuse("vertex", label)
