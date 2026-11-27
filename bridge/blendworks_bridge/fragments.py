import bmesh
import bpy
import numpy
from mathutils import Vector

from .errors import bad_args, not_found
from .meshdata import MeshData
from .polyhedron import Solid, box_uv, merged_counts
from .topology import describe_problems, manifold_report

FRESH_MATERIAL = "FreshBreak"
FRESH_FLAG = "blendworks_fresh"
CONVEX_TOLERANCE = 1e-6
UV_NAME = "UVMap"


def fresh_material():
    material = bpy.data.materials.get(FRESH_MATERIAL)
    if material is None:
        material = bpy.data.materials.new(FRESH_MATERIAL)
        material.diffuse_color = (0.62, 0.6, 0.57, 1.0)
        material[FRESH_FLAG] = True
    return material


def plan_fresh_material(args, state):
    """Plan hook: without fresh_material the call makes FreshBreak when the mesh has no fresh slot yet."""
    if "fresh_material" not in args:
        state.add("material", FRESH_MATERIAL)


def named_fresh_material(name):
    if name is None:
        return fresh_material()
    material = bpy.data.materials.get(name)
    if material is None:
        raise not_found(f"no material named {name}; create it first or leave fresh_material out")
    material[FRESH_FLAG] = True
    return material


def slot_layout(mesh, name=None):
    materials = list(mesh.materials) or [None]
    wanted = bpy.data.materials.get(name) if name is not None else None
    for index, material in enumerate(materials):
        if material is not None and (material is wanted if wanted is not None else material.get(FRESH_FLAG)):
            return materials, index
    return materials + [named_fresh_material(name)], len(materials)


def solid_from_object(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated)
    try:
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            report = manifold_report(bm)
            if not report["manifold"]:
                raise bad_args(f"{obj.name} is not a closed solid: {describe_problems(report)}")
        finally:
            bm.free()
        count = len(mesh.vertices)
        flat = numpy.empty(count * 3)
        mesh.vertices.foreach_get("co", flat)
        matrix = numpy.array(evaluated.matrix_world, dtype=numpy.float64)
        world = flat.reshape(count, 3) @ matrix[:3, :3].T + matrix[:3, 3]
        mirrored = numpy.linalg.det(matrix[:3, :3]) < 0.0
        layer = mesh.uv_layers.active
        slots = max(len(mesh.materials), 1)
        faces, uvs, materials = [], [], []
        for polygon in mesh.polygons:
            indices = list(polygon.vertices)
            corner_uvs = [tuple(layer.uv[loop].vector) for loop in polygon.loop_indices] if layer is not None else None
            if mirrored:
                indices.reverse()
                corner_uvs = corner_uvs[::-1] if corner_uvs is not None else None
            faces.append(indices)
            uvs.append(corner_uvs)
            materials.append(min(polygon.material_index, slots - 1))
        solid = Solid(world, faces, [[(0.0, 0.0)] * len(face) for face in faces], materials)
        for number, face in enumerate(faces):
            if uvs[number] is None:
                normal = solid.face_normal(face)
                solid.uvs[number] = [box_uv(world[index], normal) for index in face]
            else:
                solid.uvs[number] = uvs[number]
        return solid
    finally:
        bpy.data.meshes.remove(mesh)


def require_convex(solid, name):
    if solid.volume() <= 0.0:
        raise bad_args(f"{name} has a negative or zero volume; recalculate its normals outward first")
    extent = float(numpy.ptp(solid.points, axis=0).max())
    if not solid.is_convex(CONVEX_TOLERANCE * max(extent, 1.0)):
        raise bad_args(f"{name} is not convex: cut a convex solid, and displace or merge pieces afterwards")


def mesh_data_from(solid, origin, matrix_inverse=None):
    data = MeshData()
    local = solid.points - origin
    if matrix_inverse is not None:
        local = local @ matrix_inverse[:3, :3].T + matrix_inverse[:3, 3]
    flip = matrix_inverse is not None and numpy.linalg.det(matrix_inverse[:3, :3]) < 0.0
    data.verts = [Vector(point) for point in local]
    for face, uvs, material in zip(solid.faces, solid.uvs, solid.materials):
        indices, corner_uvs = (face[::-1], uvs[::-1]) if flip else (face, uvs)
        data.face(indices, corner_uvs, 0, material, False)
    return data


def write_solid(mesh, solid, origin, slots, matrix_inverse=None):
    data = mesh_data_from(solid, origin, matrix_inverse)
    data.to_mesh(mesh, UV_NAME)
    mesh.materials.clear()
    for material in slots:
        mesh.materials.append(material)
    mesh.polygons.foreach_set("material_index", solid.materials)
    mesh.update()
    return mesh


def solid_stats(solid):
    return merged_counts(solid.points, solid.faces)
