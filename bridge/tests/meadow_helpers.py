"""Helpers for the meadow tests: grid meshes, field attributes, instances and paths."""
import json

import bpy
import numpy

from cover_helpers import attribute_of

FIELD_NAMES = ("moisture", "soil", "disturbance", "shade", "grazing")


def grid_mesh(bridge, name, size, count, height, offset=(0.0, 0.0)):
    """A square grid mesh of count x count vertices over size metres, z = height(x, y)."""
    xs = numpy.linspace(-0.5 * size, 0.5 * size, count)
    x, y = numpy.meshgrid(xs, xs)
    z = height(x, y)
    vertices = numpy.column_stack([x.ravel() + offset[0], y.ravel() + offset[1], z.ravel()]).round(5).tolist()
    faces = []
    for row in range(count - 1):
        for column in range(count - 1):
            first = row * count + column
            faces.append([first, first + 1, first + count + 1, first + count])
    bridge.ok("mesh_from_data", name=name, vertices=vertices, faces=faces)
    return numpy.array(vertices)


def uv_grid_mesh(bridge, name, size, count, height, offset=(0.0, 0.0)):
    """grid_mesh with a UV map that spans the square once."""
    vertices = grid_mesh(bridge, name, size, count, height, offset)
    mesh = bpy.data.objects[name].data
    layer = mesh.uv_layers.new(name="UVMap")
    uvs = (vertices[:, :2] - numpy.array(offset) + 0.5 * size) / size
    layer.uv.foreach_set("vector", uvs[[loop.vertex_index for loop in mesh.loops]].ravel())
    return vertices


def fields_of(name):
    return {field: attribute_of(name, "meadow_" + field).astype(float) for field in FIELD_NAMES}


def vertices_of(name):
    obj = bpy.data.objects[name]
    values = numpy.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", values)
    matrix = numpy.array(obj.matrix_world)
    return values.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]


def paths_of(name):
    return [numpy.array(line) for line in json.loads(bpy.data.objects[name].data["meadow_paths"])]


def instance_matrices(name):
    mesh = bpy.data.objects[name].data
    values = numpy.empty(len(mesh.vertices) * 16, dtype=numpy.float32)
    mesh.attributes["gc_transform"].data.foreach_get("value", values)
    return values.reshape(-1, 4, 4).transpose(0, 2, 1)


def instance_positions(name):
    mesh = bpy.data.objects[name].data
    values = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", values)
    return values.reshape(-1, 3)


def nearest_vertex_values(points, vertices, values):
    """values of the vertex nearest each point, on a regular grid mesh."""
    from mathutils import kdtree

    tree = kdtree.KDTree(len(vertices))
    for index, vertex in enumerate(vertices.tolist()):
        tree.insert((vertex[0], vertex[1], 0.0), index)
    tree.balance()
    return numpy.array([values[tree.find((point[0], point[1], 0.0))[1]] for point in points.tolist()])


def slope_along(points, height_gradient):
    """Mean slope (rise over run) of the ground under a polyline."""
    middle = 0.5 * (points[1:] + points[:-1])
    steps = numpy.diff(points[:, :2], axis=0)
    lengths = numpy.linalg.norm(steps, axis=1)
    keep = lengths > 1e-9
    gx, gy = height_gradient(middle[:, 0], middle[:, 1])
    rise = numpy.abs(gx[keep] * steps[keep, 0] + gy[keep] * steps[keep, 1])
    return float(rise.sum() / lengths[keep].sum())
