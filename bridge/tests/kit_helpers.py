import math

import bmesh
import bpy

from harness import snapshot


def mesh_bm(name):
    bm = bmesh.new()
    bm.from_mesh(bpy.data.objects[name].data)
    return bm


def euler(name):
    bm = mesh_bm(name)
    try:
        return len(bm.verts) - len(bm.edges) + len(bm.faces)
    finally:
        bm.free()


def volume(name):
    bm = mesh_bm(name)
    try:
        return bm.calc_volume(signed=True)
    finally:
        bm.free()


def is_closed_manifold(name):
    bm = mesh_bm(name)
    try:
        edges_ok = all(len(edge.link_faces) == 2 and edge.is_contiguous for edge in bm.edges)
        verts_ok = all(vert.is_manifold for vert in bm.verts)
        return bool(bm.faces) and edges_ok and verts_ok
    finally:
        bm.free()


def open_edge_count(name):
    bm = mesh_bm(name)
    try:
        return sum(1 for edge in bm.edges if len(edge.link_faces) != 2)
    finally:
        bm.free()


def vertices(name):
    return [vertex.co.copy() for vertex in bpy.data.objects[name].data.vertices]


def outward_normals(name):
    bm = mesh_bm(name)
    bm.verts.ensure_lookup_table()
    try:
        centre = sum((vert.co for vert in bm.verts), bm.verts[0].co * 0) / len(bm.verts)
        return sum(1 for face in bm.faces if face.normal.dot(face.calc_center_median() - centre) > 0) / len(bm.faces)
    finally:
        bm.free()


def polygon_vertex_set(name):
    return {tuple(round(c, 6) for c in vertex.co) for vertex in bpy.data.objects[name].data.vertices}


def regular_polygon_area(radius, sides):
    return sides / 2.0 * radius * radius * math.sin(math.tau / sides)


def triangle_total(name):
    return sum(len(polygon.vertices) - 2 for polygon in bpy.data.objects[name].data.polygons)


def uv_is_clean(bridge, name):
    report = bridge.ok("uv_info", name=name)
    assert report["has_uv"] and not report["outside"], report
    assert report["overlap"] == 0.0, report
    return report


def settled_snapshot():
    bpy.context.view_layer.update()
    return snapshot()


def extent(name):
    points = vertices(name)
    return [max(point[i] for point in points) - min(point[i] for point in points) for i in range(3)]
