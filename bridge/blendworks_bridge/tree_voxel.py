import math

import numpy
from mathutils.bvhtree import BVHTree

from .tree_join import AXIS, MATERIAL, RADIUS, TANGENT, UV_NAME, write_mesh

SMOOTH_ROUNDS = 4
SMOOTH_WEIGHT = 0.5
SMOOTH_RINGS = 2


class Source:
    def __init__(self, mesh):
        mesh.calc_loop_triangles()
        count = len(mesh.loop_triangles)
        self.triangles = numpy.empty(count * 3, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("vertices", self.triangles)
        self.triangles = self.triangles.reshape(-1, 3)
        self.loops = numpy.empty(count * 3, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("loops", self.loops)
        self.loops = self.loops.reshape(-1, 3)
        self.polygons = numpy.empty(count, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("polygon_index", self.polygons)
        points = numpy.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", points)
        self.points = points.reshape(-1, 3)
        uvs = numpy.empty(len(mesh.loops) * 2)
        mesh.uv_layers[UV_NAME].uv.foreach_get("vector", uvs)
        self.uvs = uvs.reshape(-1, 2)
        self.radii = numpy.empty(len(mesh.loops))
        mesh.attributes[RADIUS].data.foreach_get("value", self.radii)
        tangents = numpy.empty(len(mesh.loops) * 3)
        mesh.attributes[TANGENT].data.foreach_get("vector", tangents)
        self.tangents = tangents.reshape(-1, 3)
        self.face_axes = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
        mesh.attributes[AXIS].data.foreach_get("value", self.face_axes)
        self.face_materials = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
        mesh.attributes[MATERIAL].data.foreach_get("value", self.face_materials)
        self.triangle_axes = self.face_axes[self.polygons]
        self.tree = BVHTree.FromPolygons(self.points.tolist(), self.triangles.tolist(), all_triangles=True)
        self.axis_trees = {}

    def tree_of(self, axis):
        if axis not in self.axis_trees:
            picked = numpy.flatnonzero(self.triangle_axes == axis)
            self.axis_trees[axis] = (BVHTree.FromPolygons(self.points.tolist(), self.triangles[picked].tolist(), all_triangles=True), picked)
        return self.axis_trees[axis]

    def nearest(self, points, axis=None):
        if axis is None:
            tree, picked = self.tree, None
        else:
            tree, picked = self.tree_of(axis)
        locations = numpy.empty((len(points), 3))
        triangles = numpy.empty(len(points), dtype=numpy.int64)
        for index, point in enumerate(points.tolist()):
            found = tree.find_nearest(point)
            locations[index] = found[0]
            triangles[index] = found[2]
        if picked is not None:
            triangles = picked[triangles]
        return triangles, barycentric(self.points[self.triangles[triangles]], locations)

    def values(self, triangles, weights):
        loops = self.loops[triangles]
        return {
            "axis": self.triangle_axes[triangles],
            "uv": numpy.einsum("ij,ijk->ik", weights, self.uvs[loops]),
            "radius": numpy.einsum("ij,ij->i", weights, self.radii[loops]),
            "tangent": numpy.einsum("ij,ijk->ik", weights, self.tangents[loops]),
            "material": self.face_materials[self.polygons[triangles]],
        }


def barycentric(corners, points):
    first = corners[:, 1] - corners[:, 0]
    second = corners[:, 2] - corners[:, 0]
    offset = points - corners[:, 0]
    d00 = numpy.einsum("ij,ij->i", first, first)
    d01 = numpy.einsum("ij,ij->i", first, second)
    d11 = numpy.einsum("ij,ij->i", second, second)
    d20 = numpy.einsum("ij,ij->i", offset, first)
    d21 = numpy.einsum("ij,ij->i", offset, second)
    denominator = numpy.where(numpy.abs(d00 * d11 - d01 * d01) > 1e-30, d00 * d11 - d01 * d01, 1.0)
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    return numpy.clip(numpy.stack([1.0 - v - w, v, w], axis=1), 0.0, 1.0)


def read_topology(mesh):
    points = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    corners = numpy.empty(len(mesh.loops), dtype=numpy.int64)
    mesh.loops.foreach_get("vertex_index", corners)
    sizes = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_total", sizes)
    return points.reshape(-1, 3), corners, sizes


def unwrap_corners(uvs, radii, owners):
    period = 2.0 * math.pi * numpy.maximum(radii, 1e-9)
    low = numpy.full(owners.max() + 1, numpy.inf)
    high = numpy.full(owners.max() + 1, -numpy.inf)
    numpy.minimum.at(low, owners, uvs[:, 0])
    numpy.maximum.at(high, owners, uvs[:, 0])
    lift = ((high - low)[owners] > 0.5 * period) & (uvs[:, 0] < high[owners] - 0.5 * period)
    lifted = uvs.copy()
    lifted[lift, 0] += period[lift]
    return lifted


def majority_axes(corner_axes, sizes, starts):
    face_axis = corner_axes[starts].copy()
    mixed = numpy.zeros(len(sizes), dtype=bool)
    owners = numpy.repeat(numpy.arange(len(sizes)), sizes)
    mixed[owners[corner_axes != face_axis[owners]]] = True
    for face in numpy.flatnonzero(mixed).tolist():
        values, counts = numpy.unique(corner_axes[starts[face] : starts[face] + sizes[face]], return_counts=True)
        face_axis[face] = values[numpy.argmax(counts)]
    return face_axis, owners


def transfer(mesh, joined):
    source = Source(joined)
    points, corners, sizes = read_topology(mesh)
    starts = numpy.concatenate([[0], numpy.cumsum(sizes)[:-1]])
    triangles, weights = source.nearest(points)
    vertex = source.values(triangles, weights)
    face_axis, owners = majority_axes(vertex["axis"][corners], sizes, starts)
    uvs = vertex["uv"][corners]
    radii = vertex["radius"][corners]
    tangents = vertex["tangent"][corners]
    materials = vertex["material"][corners[starts]]
    wrong = numpy.flatnonzero(vertex["axis"][corners] != face_axis[owners])
    for axis in numpy.unique(face_axis[owners[wrong]]).tolist():
        picked = wrong[face_axis[owners[wrong]] == axis]
        found = source.values(*source.nearest(points[corners[picked]], axis))
        uvs[picked] = found["uv"]
        radii[picked] = found["radius"]
        tangents[picked] = found["tangent"]
        first = numpy.isin(picked, starts)
        materials[owners[picked[first]]] = found["material"][first]
    uvs = unwrap_corners(uvs, radii, owners)
    rebuilt = mesh.copy()
    rebuilt.clear_geometry()
    write_mesh(rebuilt, points, corners, sizes, uvs, {RADIUS: radii, TANGENT: tangents}, {AXIS: face_axis, MATERIAL: materials})
    return rebuilt, crease_mask(corners, owners, face_axis, len(points))


def crease_mask(corners, owners, face_axis, count):
    low = numpy.full(count, numpy.iinfo(numpy.int64).max)
    high = numpy.full(count, -1)
    numpy.minimum.at(low, corners, face_axis[owners])
    numpy.maximum.at(high, corners, face_axis[owners])
    return (high >= 0) & (low != high)


def smooth_junctions(mesh, crease):
    edges = numpy.empty(len(mesh.edges) * 2, dtype=numpy.int64)
    mesh.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    chosen = crease.copy()
    for _ in range(SMOOTH_RINGS):
        grown = chosen.copy()
        grown[edges[chosen[edges[:, 0]], 1]] = True
        grown[edges[chosen[edges[:, 1]], 0]] = True
        chosen = grown
    points = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    points = points.reshape(-1, 3)
    degree = numpy.bincount(edges.reshape(-1), minlength=len(points)).astype(float)
    for _ in range(SMOOTH_ROUNDS):
        summed = numpy.zeros_like(points)
        numpy.add.at(summed, edges[:, 0], points[edges[:, 1]])
        numpy.add.at(summed, edges[:, 1], points[edges[:, 0]])
        average = summed / numpy.maximum(degree, 1.0)[:, None]
        points[chosen] += SMOOTH_WEIGHT * (average[chosen] - points[chosen])
    mesh.vertices.foreach_set("co", points.astype(numpy.float32).reshape(-1))
    mesh.update()
    return int(chosen.sum())
