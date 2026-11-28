"""Joins tree tubes into one mesh with a skin union."""

import bpy
import numpy

from .edge_order import canonical_edges
from .errors import failed

UV_NAME = "UVMap"
RADIUS = "tree_radius"
TANGENT = "tree_tangent"
AXIS = "tree_axis"
MATERIAL = "tree_material"


class Arrays:
    def __init__(self):
        self.points = []
        self.corners = []
        self.sizes = []
        self.uvs = []
        self.radii = []
        self.tangents = []
        self.materials = []
        self.axes = []
        self.count = 0

    def add(self, tube):
        points = tube.vertices()
        for block in tube.blocks:
            faces = block["faces"]
            self.corners.append((faces + self.count).reshape(-1))
            self.sizes.append(numpy.full(len(faces), faces.shape[1], dtype=numpy.int64))
            self.uvs.append(block["uvs"].reshape(-1, 2))
            self.radii.append(block["radii"].reshape(-1))
            self.tangents.append(block["tangents"].reshape(-1, 3))
            self.materials.append(block["materials"])
            self.axes.append(numpy.full(len(faces), tube.axis_index, dtype=numpy.int64))
        self.points.append(points)
        self.count += len(points)
        return self

    def to_mesh(self, name):
        mesh = bpy.data.meshes.new(name)
        write_mesh(
            mesh,
            numpy.vstack(self.points),
            numpy.concatenate(self.corners),
            numpy.concatenate(self.sizes),
            numpy.vstack(self.uvs),
            {RADIUS: numpy.concatenate(self.radii), TANGENT: numpy.vstack(self.tangents)},
            {AXIS: numpy.concatenate(self.axes), MATERIAL: numpy.concatenate(self.materials)},
        )
        return mesh


def write_mesh(mesh, points, corners, sizes, uvs, corner_values, face_values):
    mesh.vertices.add(len(points))
    mesh.vertices.foreach_set("co", numpy.asarray(points, dtype=numpy.float32).reshape(-1))
    mesh.loops.add(len(corners))
    mesh.loops.foreach_set("vertex_index", numpy.asarray(corners, dtype=numpy.int32))
    mesh.polygons.add(len(sizes))
    starts = numpy.concatenate([[0], numpy.cumsum(sizes)[:-1]]).astype(numpy.int32)
    mesh.polygons.foreach_set("loop_start", starts)
    mesh.update(calc_edges=True)
    canonical_edges(mesh)
    layer = mesh.uv_layers.new(name=UV_NAME)
    layer.uv.foreach_set("vector", numpy.asarray(uvs, dtype=numpy.float32).reshape(-1))
    for name, values in corner_values.items():
        kind = "FLOAT_VECTOR" if values.ndim == 2 else "FLOAT"
        attribute = mesh.attributes.new(name, kind, "CORNER")
        attribute.data.foreach_set("vector" if kind == "FLOAT_VECTOR" else "value", numpy.asarray(values, dtype=numpy.float32).reshape(-1))
    for name, values in face_values.items():
        attribute = mesh.attributes.new(name, "INT", "FACE")
        attribute.data.foreach_set("value", numpy.asarray(values, dtype=numpy.int32))
    mesh.polygons.foreach_set("use_smooth", numpy.ones(len(sizes), dtype=bool))
    mesh.update()
    return mesh


def temporary_object(ctx, name, mesh, collection=None):
    obj = bpy.data.objects.new(name, mesh)
    (collection or ctx.scene.collection).objects.link(obj)
    return obj


def remove_objects(objects):
    for obj in objects:
        mesh = obj.data
        bpy.data.objects.remove(obj)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def evaluated_copy(ctx, obj, name):
    ctx.view_layer.update()
    evaluated = obj.evaluated_get(ctx.depsgraph())
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=ctx.depsgraph())
    canonical_edges(mesh)
    return mesh


def skin_union(ctx, tubes, name):
    collection = bpy.data.collections.new(f"{name}_tubes")
    objects = []
    try:
        base = temporary_object(ctx, f"{name}_trunk", Arrays().add(tubes[0]).to_mesh(f"{name}_trunk"))
        objects.append(base)
        for tube in tubes[1:]:
            objects.append(temporary_object(ctx, f"{name}_tube", Arrays().add(tube).to_mesh(f"{name}_tube"), collection))
        if len(tubes) == 1:
            return evaluated_copy(ctx, base, name)
        modifier = base.modifiers.new("Union", "BOOLEAN")
        modifier.operation = "UNION"
        modifier.solver = "MANIFOLD"
        modifier.operand_type = "COLLECTION"
        modifier.collection = collection
        mesh = evaluated_copy(ctx, base, name)
        if len(mesh.polygons) == 0:
            bpy.data.meshes.remove(mesh)
            raise failed("the union of the branch tubes came out empty")
        return mesh
    finally:
        remove_objects(objects)
        bpy.data.collections.remove(collection)
        ctx.view_layer.update()


def joined_tubes(tubes, name):
    arrays = Arrays()
    for tube in tubes:
        arrays.add(tube)
    return arrays.to_mesh(name)


def voxel_remesh(ctx, mesh, voxel_size, name):
    obj = temporary_object(ctx, f"{name}_voxels", mesh)
    try:
        modifier = obj.modifiers.new("Remesh", "REMESH")
        modifier.mode = "VOXEL"
        modifier.voxel_size = voxel_size
        modifier.adaptivity = 0.0
        modifier.use_smooth_shade = True
        return evaluated_copy(ctx, obj, name)
    finally:
        obj.modifiers.clear()
        bpy.data.objects.remove(obj)
        ctx.view_layer.update()
