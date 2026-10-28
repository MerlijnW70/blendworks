import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "judge"))

import bmesh
import bpy
import numpy
from judge_natural import object_roughness, triangle_corners, world_vertices


def mesh_of(name):
    return bpy.data.objects[name]


def world_and_faces(name):
    obj = mesh_of(name)
    bpy.context.view_layer.update()
    mesh = obj.data
    matrix = numpy.array(obj.matrix_world)
    count = len(mesh.vertices)
    flat = numpy.empty(count * 3)
    mesh.vertices.foreach_get("co", flat)
    world = flat.reshape(count, 3) @ matrix[:3, :3].T + matrix[:3, 3]
    return world, [list(polygon.vertices) for polygon in mesh.polygons]


def report(name):
    bm = bmesh.new()
    bm.from_mesh(mesh_of(name).data)
    try:
        open_edges = sum(1 for edge in bm.edges if len(edge.link_faces) != 2)
        pinched = sum(1 for vert in bm.verts if vert.link_faces and not vert.is_manifold)
        return {"closed": bool(bm.faces) and open_edges == 0 and pinched == 0, "volume": bm.calc_volume(signed=True)}
    finally:
        bm.free()


def roughness_p90(name):
    obj = mesh_of(name)
    mesh = obj.data
    mesh.calc_loop_triangles()
    return object_roughness(world_vertices(mesh, obj.matrix_world), triangle_corners(mesh))["p90"]


def extents(name):
    world, _ = world_and_faces(name)
    return numpy.ptp(world, axis=0)


def convex(name, tolerance=1e-4):
    world, faces = world_and_faces(name)
    for face in faces:
        corners = world[face]
        normal = numpy.cross(corners[1] - corners[0], corners[2] - corners[0])
        length = numpy.linalg.norm(normal)
        if length == 0:
            continue
        if numpy.max((world - corners[0]) @ (normal / length)) > tolerance:
            return False
    return True
