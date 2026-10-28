import math

import bmesh
import bpy
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from tree_helpers import plain
from blendworks_bridge.tree_skeleton import PROPERTY

RAYS = 16
RADIUS_TOLERANCE = 0.10
COLLAR_REACH = 1.5
BURIED_REACH = 0.5
SPLIT_COSINE = math.cos(math.radians(75.0))

SMALL = dict(height=6.0, trunk_height=1.5, crown_radius=2.0, points=700, influence=0.9, kill=0.2, step=0.12, seed=4)
SMALL_ROOTS = dict(points=300, depth=0.8, radius=1.4, influence=0.6, kill=0.18, step=0.1)
LEVELS = dict(method="levels", envelope="conical", height=7.0, trunk_height=1.0, branches=[24, 6], levels=3, segments=[24, 6, 3], down_angle=[70.0, 50.0], curve=[0.0, 20.0, 10.0], tip_radius=0.006, seed=2)


class Skeleton:
    def __init__(self, obj):
        data = plain(obj[PROPERTY])
        self.positions = numpy.array(data["position"], dtype=float).reshape(-1, 3)
        self.parents = numpy.array(data["parent"], dtype=numpy.int64)
        self.radii = numpy.array(data["radius"], dtype=float)
        self.orders = numpy.array(data["order"], dtype=numpy.int64)
        self.kinds = numpy.array(data["kind"], dtype=numpy.int64)
        self.children = [[] for _ in self.parents]
        for node in range(1, len(self.parents)):
            self.children[self.parents[node]].append(node)

    def main_child(self, node):
        same = [child for child in self.children[node] if self.orders[child] == self.orders[node] and self.kinds[child] == self.kinds[node]]
        return same[0] if same else None

    def tangent(self, node):
        following = self.main_child(node)
        start = self.positions[self.parents[node]] if node > 0 else self.positions[node]
        end = self.positions[following] if following is not None else self.positions[node]
        direction = end - start
        return direction / max(numpy.linalg.norm(direction), 1e-12)

    def axis_start(self, node):
        while node > 0 and self.orders[self.parents[node]] == self.orders[node] and self.kinds[self.parents[node]] == self.kinds[node] and self.main_child(self.parents[node]) == node:
            node = self.parents[node]
        return node

    def axis_nodes(self, node):
        first = self.axis_start(node)
        nodes = [self.parents[first]] if first > 0 else []
        nodes.append(first)
        while self.main_child(nodes[-1]) is not None:
            nodes.append(self.main_child(nodes[-1]))
        return nodes

    def along_from_base(self, node):
        total = 0.0
        while node > 0:
            total += float(numpy.linalg.norm(self.positions[node] - self.positions[self.parents[node]]))
            node = self.parents[node]
        return total


def segment_distances(points, starts, ends):
    span = ends - starts
    square = numpy.maximum(numpy.einsum("ij,ij->i", span, span), 1e-24)
    out = numpy.empty((len(points), len(starts)))
    for row, point in enumerate(points):
        share = numpy.clip(numpy.einsum("ij,ij->i", point - starts, span) / square, 0.0, 1.0)
        out[row] = numpy.linalg.norm(starts + share[:, None] * span - point, axis=1)
    return out


def turned(tree, node):
    following = tree.main_child(node)
    if following is None:
        return False
    incoming = tree.positions[node] - tree.positions[tree.parents[node]]
    outgoing = tree.positions[following] - tree.positions[node]
    return float(incoming @ outgoing) < SPLIT_COSINE * numpy.linalg.norm(incoming) * numpy.linalg.norm(outgoing)


def excluded_nodes(tree, flare_height, root_length, cut):
    count = len(tree.parents)
    skip = numpy.zeros(count, dtype=bool)
    skip[0] = True
    skip |= tree.radii < cut
    for node in range(1, count):
        if tree.radii[tree.parents[node]] < cut:
            skip[node] = True
        start = tree.axis_start(node)
        if tree.kinds[node] == 0 and tree.orders[node] == 0 and tree.along_from_base(node) < flare_height:
            skip[node] = True
        if tree.kinds[node] == 1 and tree.along_from_base(node) < root_length:
            skip[node] = True
        if turned(tree, node):
            skip[node] = True
        junction = tree.parents[start]
        if start > 0 and junction >= 0:
            line = tree.positions[tree.axis_nodes(junction)]
            distance = segment_distances(tree.positions[node][None, :], line[:-1], line[1:]).min() if len(line) > 1 else numpy.linalg.norm(tree.positions[node] - line[0])
            if distance < tree.radii[junction] + COLLAR_REACH * tree.radii[node]:
                skip[node] = True
    nodes = numpy.arange(1, count)
    starts = tree.positions[tree.parents[nodes]]
    ends = tree.positions[nodes]
    segment_radii = tree.radii[nodes]
    for first in range(0, count, 256):
        rows = numpy.arange(first, min(count, first + 256))
        gaps = segment_distances(tree.positions[rows], starts, ends)
        for local, node in enumerate(rows.tolist()):
            own = (nodes == node) | (tree.parents[nodes] == node)
            inside = (gaps[local] < segment_radii + BURIED_REACH * tree.radii[node]) & ~own & (segment_radii >= tree.radii[node])
            if inside.any():
                skip[node] = True
    return skip


def mesh_tree(obj):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def measured_radii(obj, tree, nodes):
    bvh = mesh_tree(obj)
    found = {}
    for node in nodes:
        tangent = tree.tangent(node)
        reference = numpy.array([0.0, 0.0, 1.0]) if abs(tangent[2]) < 0.9 else numpy.array([1.0, 0.0, 0.0])
        first = numpy.cross(tangent, reference)
        first /= numpy.linalg.norm(first)
        second = numpy.cross(tangent, first)
        hits = []
        for ray in range(RAYS):
            angle = 2.0 * math.pi * ray / RAYS
            direction = Vector(math.cos(angle) * first + math.sin(angle) * second)
            location, _, _, distance = bvh.ray_cast(Vector(tree.positions[node]), direction)
            hits.append(distance if location is not None else math.inf)
        found[node] = float(numpy.median(hits))
    return found


def radius_errors(obj, reply, cut=None):
    tree = Skeleton(obj)
    skip = excluded_nodes(tree, reply["flare"]["height"], reply["root_flare"]["length"], reply["min_radius"] if cut is None else cut)
    nodes = numpy.flatnonzero(~skip).tolist()
    measured = measured_radii(obj, tree, nodes)
    return {node: measured[node] / tree.radii[node] - 1.0 for node in nodes}, len(tree.parents)


def uv_scales(obj, materials, base_reach=0.0):
    mesh = obj.data
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    loops = numpy.empty(count * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("loops", loops)
    vertices = numpy.empty(count * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", vertices)
    polygons = numpy.empty(count, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("polygon_index", polygons)
    slots = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("material_index", slots)
    names = [material.name for material in mesh.materials]
    wanted = numpy.isin(slots[polygons], [names.index(name) for name in materials if name in names])
    points = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    points = points.reshape(-1, 3)[vertices.reshape(-1, 3)]
    uvs = numpy.empty(len(mesh.loops) * 2)
    mesh.uv_layers.active.uv.foreach_get("vector", uvs)
    uvs = uvs.reshape(-1, 2)[loops.reshape(-1, 3)]
    edges = numpy.stack([points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]], axis=2)
    spans = numpy.stack([uvs[:, 1] - uvs[:, 0], uvs[:, 2] - uvs[:, 0]], axis=2)
    determinant = spans[:, 0, 0] * spans[:, 1, 1] - spans[:, 0, 1] * spans[:, 1, 0]
    centres = points.mean(axis=1)
    base = Skeleton(obj).positions[0]
    usable = wanted & (numpy.abs(determinant) > 1e-12) & (numpy.linalg.norm(centres - base, axis=1) > base_reach)
    inverse = numpy.empty_like(spans)
    safe = numpy.where(usable, determinant, 1.0)
    inverse[:, 0, 0] = spans[:, 1, 1] / safe
    inverse[:, 0, 1] = -spans[:, 0, 1] / safe
    inverse[:, 1, 0] = -spans[:, 1, 0] / safe
    inverse[:, 1, 1] = spans[:, 0, 0] / safe
    jacobian = numpy.einsum("tij,tjk->tik", edges, inverse)
    areas = 0.5 * numpy.linalg.norm(numpy.cross(edges[:, :, 0], edges[:, :, 1]), axis=1)
    return numpy.linalg.norm(jacobian[usable, :, 0], axis=1), numpy.linalg.norm(jacobian[usable, :, 1], axis=1), areas[usable]


def weighted_share(values, weights, low, high):
    inside = (values >= low) & (values <= high)
    return float(weights[inside].sum() / weights.sum())


def scene_reset():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)


def crossing_pairs(points, triangles):
    tree = BVHTree.FromPolygons(points, triangles, all_triangles=True)
    return sum(1 for first, second in tree.overlap(tree) if first < second and not set(triangles[first]) & set(triangles[second]))


def self_intersections(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    points = [vertex.co.copy() for vertex in mesh.vertices]
    exported = crossing_pairs(points, [tuple(triangle.vertices) for triangle in mesh.loop_triangles])
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
    beauty = crossing_pairs(points, [tuple(vert.index for vert in face.verts) for face in bm.faces])
    bm.free()
    return exported + beauty


def shells(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seen = numpy.zeros(len(bm.verts), dtype=bool)
    count = 0
    for start in bm.verts:
        if seen[start.index]:
            continue
        count += 1
        stack = [start]
        seen[start.index] = True
        while stack:
            vert = stack.pop()
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if not seen[other.index]:
                    seen[other.index] = True
                    stack.append(other)
    bm.free()
    return count
