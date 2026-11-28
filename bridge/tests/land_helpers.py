import json
import math

import bpy
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

DOWN = Vector((0.0, 0.0, -1.0))
REGION = 300.0


def region(bridge, name="land", size=REGION, resolution=61, height=14.0, seed=3, scale=120.0, location=None):
    bridge.ok("heightfield", name=name, size=[size, size], resolution=resolution, height=height, seed=seed, scale=scale, octaves=4, hurst=0.7, form="none")
    where = location if location is not None else [-size / 2.0, -size / 2.0, 0.0]
    bridge.ok("transform", name=name, location=where)
    return name


def surface(name):
    obj = bpy.data.objects[name]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        matrix = evaluated.matrix_world
        points = [matrix @ vertex.co for vertex in mesh.vertices]
        mesh.calc_loop_triangles()
        faces = [tuple(tri.vertices) for tri in mesh.loop_triangles]
        values = {}
        for attribute in mesh.attributes:
            if attribute.domain == "POINT" and attribute.data_type == "FLOAT" and attribute.name.startswith("dl_"):
                data = numpy.empty(len(mesh.vertices), dtype=numpy.float32)
                attribute.data.foreach_get("value", data)
                values[attribute.name] = data
    finally:
        evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(points, faces), faces, values


def heights(tree, xy, top=10_000.0):
    result = numpy.full(len(xy), numpy.nan)
    for index, (x, y) in enumerate(numpy.asarray(xy, dtype=float).tolist()):
        hit = tree.ray_cast(Vector((x, y, top)), DOWN)
        if hit[0] is not None:
            result[index] = hit[0].z
    return result


def attribute_at(tree, faces, values, xy, top=10_000.0):
    result = numpy.full(len(xy), numpy.nan)
    for index, (x, y) in enumerate(numpy.asarray(xy, dtype=float).tolist()):
        hit = tree.ray_cast(Vector((x, y, top)), DOWN)
        if hit[0] is not None:
            result[index] = float(numpy.mean(values[list(faces[hit[2]])]))
    return result


def grid(centre, size, cells):
    spacing = size / cells
    xs = centre[0] + (numpy.arange(cells) + 0.5) * spacing - size / 2.0
    ys = centre[1] + (numpy.arange(cells) + 0.5) * spacing - size / 2.0
    grid_x, grid_y = numpy.meshgrid(xs, ys)
    return numpy.column_stack([grid_x.ravel(), grid_y.ravel()]), spacing


def vertices(name):
    obj = bpy.data.objects[name]
    local = numpy.empty(len(obj.data.vertices) * 3, dtype=numpy.float32)
    obj.data.vertices.foreach_get("co", local)
    return local.reshape(-1, 3).astype(numpy.float64) + numpy.array(obj.matrix_world.translation)


def settings(name):
    return json.loads(bpy.data.objects[name]["blendworks_distant_land"])


def boundary_edges(name):
    mesh = bpy.data.objects[name].data
    counts = {}
    for polygon in mesh.polygons:
        ids = list(polygon.vertices)
        for a, b in zip(ids, ids[1:] + ids[:1]):
            key = (min(a, b), max(a, b))
            counts[key] = counts.get(key, 0) + 1
    return counts


def drop(radius, reach):
    return radius - math.sqrt(radius * radius - reach * reach)
