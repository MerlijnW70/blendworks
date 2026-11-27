import math

import bpy
import numpy

from .edge_order import canonical_edges
from .liquid_world import LIQUID_PROPERTY, TOP_ATTRIBUTE
from .limits import MAX_MESH_VERTICES
from .errors import bad_args

SMOOTH_ANGLE = 30.0


def build_mesh(name, points, triangles, uvs=None, top=None, scalars=None, vectors=None, smooth=True):
    points = numpy.asarray(points, dtype=float).reshape(-1, 3)
    triangles = numpy.asarray(triangles, dtype=numpy.int64).reshape(-1, 3)
    if len(points) > MAX_MESH_VERTICES:
        raise bad_args(f"the liquid mesh would have {len(points)} vertices, more than {MAX_MESH_VERTICES}; give a coarser resolution or a smaller area")
    if len(triangles) == 0:
        raise bad_args("the liquid has no surface: nothing lies below the level")
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(points))
    mesh.vertices.foreach_set("co", points.astype(numpy.float32).ravel())
    mesh.loops.add(len(triangles) * 3)
    mesh.loops.foreach_set("vertex_index", triangles.astype(numpy.int32).ravel())
    mesh.polygons.add(len(triangles))
    mesh.polygons.foreach_set("loop_start", (numpy.arange(len(triangles), dtype=numpy.int32) * 3))
    mesh.polygons.foreach_set("loop_total", numpy.full(len(triangles), 3, dtype=numpy.int32))
    mesh.update(calc_edges=True)
    mesh.validate(clean_customdata=False)
    canonical_edges(mesh)
    if uvs is not None:
        layer = mesh.uv_layers.new(name="UVMap")
        corner = numpy.asarray(uvs, dtype=numpy.float32)[triangles.ravel()]
        layer.data.foreach_set("uv", corner.ravel())
    flags = numpy.ones(len(triangles), dtype=bool) if top is None else numpy.asarray(top, dtype=bool)
    attribute = mesh.attributes.new(TOP_ATTRIBUTE, "BOOLEAN", "FACE")
    attribute.data.foreach_set("value", flags)
    for key, values in (scalars or {}).items():
        layer = mesh.attributes.new(key, "FLOAT", "POINT")
        layer.data.foreach_set("value", numpy.ascontiguousarray(values, dtype=numpy.float32))
    for key, values in (vectors or {}).items():
        layer = mesh.attributes.new(key, "FLOAT_VECTOR", "POINT")
        layer.data.foreach_set("vector", numpy.ascontiguousarray(values, dtype=numpy.float32).ravel())
    mesh.polygons.foreach_set("use_smooth", numpy.full(len(triangles), smooth))
    if smooth:
        mesh.set_sharp_from_angle(angle=math.radians(SMOOTH_ANGLE))
    mesh.update()
    return mesh


def flag(obj, kind, settings=None):
    import json

    obj[LIQUID_PROPERTY] = kind
    if settings is not None:
        obj["blendworks_liquid_settings"] = json.dumps(settings, sort_keys=True)
    return obj


def mesh_volume(points, triangles):
    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    return float(numpy.einsum("ij,ij->i", a, numpy.cross(b, c)).sum() / 6.0)


def surface_area(points, triangles):
    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    return float(0.5 * numpy.linalg.norm(numpy.cross(b - a, c - a), axis=1).sum())


def object_arrays(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    points = numpy.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    points = points.reshape(-1, 3)
    matrix = numpy.array(obj.matrix_world)
    points = points @ matrix[:3, :3].T + matrix[:3, 3]
    triangles = numpy.zeros(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", triangles)
    return points, triangles.reshape(-1, 3)


def boundary_edges(triangles):
    edges = numpy.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    keys = numpy.sort(edges, axis=1)
    _, inverse, counts = numpy.unique(keys, axis=0, return_inverse=True, return_counts=True)
    return edges[counts[inverse.reshape(-1)] == 1]


def close_sheet(points, triangles, bottom):
    """A closed solid from a surface sheet: the sheet, a flat floor at bottom and walls straight down from its open edges.
    Cycles finds the volume a camera starts in by tracing closed surfaces, so a liquid volume needs a closed mesh."""
    count = len(points)
    floor = points.copy()
    floor[:, 2] = bottom
    edges = boundary_edges(triangles)
    walls = numpy.concatenate([
        numpy.column_stack([edges[:, 1], edges[:, 0], edges[:, 0] + count]),
        numpy.column_stack([edges[:, 1], edges[:, 0] + count, edges[:, 1] + count]),
    ]) if len(edges) else numpy.zeros((0, 3), dtype=int)
    faces = numpy.concatenate([triangles, triangles[:, ::-1] + count, walls])
    top = numpy.concatenate([numpy.ones(len(triangles), dtype=bool), numpy.zeros(len(faces) - len(triangles), dtype=bool)])
    return numpy.concatenate([points, floor]), faces, top
