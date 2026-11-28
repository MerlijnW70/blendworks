"""Linked and realized copies of objects with unique child names."""

import bpy

from .errors import bad_args, failed
from .limits import MAX_MESH_VERTICES
from .meshdata import MeshData
from .util import link_object


def child_name(name, index):
    return f"{name}_{index:03d}"


def require_free_names(name, count):
    taken = [child_name(name, index) for index in range(count) if child_name(name, index) in bpy.data.objects]
    if taken:
        raise bad_args(f"an object named {taken[0]} already exists; choose another name")


def linked_copies(ctx, name, mesh, matrices, group):
    require_free_names(name, len(matrices))
    parent = None
    if group:
        parent = link_object(ctx, name, None)
    objects = []
    for index, matrix in enumerate(matrices):
        copy = bpy.data.objects.new(child_name(name, index), mesh)
        ctx.scene.collection.objects.link(copy)
        copy.matrix_world = matrix
        if parent is not None:
            copy.parent = parent
        objects.append(copy)
    return parent, objects


def realized_copy(ctx, name, mesh, matrices):
    data = MeshData.from_mesh(mesh)
    if len(data.verts) * len(matrices) > MAX_MESH_VERTICES:
        raise failed(f"{len(matrices)} copies would exceed the cap of {MAX_MESH_VERTICES} vertices")
    total = MeshData()
    for matrix in matrices:
        total.append(data, matrix)
    result = bpy.data.meshes.new(name)
    total.to_mesh(result)
    for material in mesh.materials:
        result.materials.append(material)
    return link_object(ctx, name, result)
