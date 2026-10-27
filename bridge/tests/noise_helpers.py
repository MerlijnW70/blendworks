import bmesh
import bpy
import numpy


def grid_plane(name, extent, segments, location=(0.0, 0.0, 0.0)):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=segments, y_segments=segments, size=extent / 2.0)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    bpy.context.view_layer.update()
    return obj


def world_points(name):
    bpy.context.view_layer.update()
    obj = bpy.data.objects[name]
    matrix = numpy.array(obj.matrix_world)
    count = len(obj.data.vertices)
    local = numpy.empty(count * 3)
    obj.data.vertices.foreach_get("co", local)
    return local.reshape(count, 3) @ matrix[:3, :3].T + matrix[:3, 3]
