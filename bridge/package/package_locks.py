"""Vertices and edges that LOD decimation must keep: borders, material and UV seams."""

import numpy as np

UV_TOLERANCE = 1e-6


def corner_arrays(mesh):
    corners = len(mesh.loops)
    vertex = np.empty(corners, dtype=np.int64)
    edge = np.empty(corners, dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", vertex)
    mesh.loops.foreach_get("edge_index", edge)
    return vertex, edge


def face_arrays(mesh):
    count = len(mesh.polygons)
    total = np.empty(count, dtype=np.int64)
    material = np.empty(count, dtype=np.int64)
    mesh.polygons.foreach_get("loop_total", total)
    mesh.polygons.foreach_get("material_index", material)
    return total, material


def edge_ends(mesh):
    ends = np.empty(len(mesh.edges) * 2, dtype=np.int64)
    mesh.edges.foreach_get("vertices", ends)
    return ends.reshape(-1, 2)


def border_edges(edge_corners, edge_count):
    return np.bincount(edge_corners, minlength=edge_count) != 2


def material_edges(edge_corners, corner_material, edge_count):
    order = np.argsort(edge_corners, kind="stable")
    sorted_edges = edge_corners[order]
    sorted_material = corner_material[order]
    ids = np.arange(edge_count)
    first = np.searchsorted(sorted_edges, ids, side="left")
    last = np.searchsorted(sorted_edges, ids, side="right")
    flagged = np.zeros(edge_count, dtype=bool)
    paired = np.nonzero((last - first) == 2)[0]
    flagged[paired] = sorted_material[first[paired]] != sorted_material[first[paired] + 1]
    return flagged


def uv_split_vertices(mesh, corner_vertex):
    split = np.zeros(len(mesh.vertices), dtype=bool)
    if len(corner_vertex) == 0:
        return split
    order = np.argsort(corner_vertex, kind="stable")
    sorted_vertex = corner_vertex[order]
    starts = np.flatnonzero(np.r_[True, sorted_vertex[1:] != sorted_vertex[:-1]])
    present = sorted_vertex[starts]
    for layer in mesh.uv_layers:
        flat = np.empty(len(corner_vertex) * 2, dtype=np.float64)
        layer.uv.foreach_get("vector", flat)
        uv = flat.reshape(-1, 2)[order]
        spread = np.maximum.reduceat(uv, starts) - np.minimum.reduceat(uv, starts)
        split[present] |= (spread > UV_TOLERANCE).any(axis=1)
    return split


def vertex_flags(ends, flagged_edges, count):
    flags = np.zeros(count, dtype=bool)
    flags[ends[flagged_edges].ravel()] = True
    return flags


def feature_vertices(mesh):
    count = len(mesh.vertices)
    empty = np.zeros(count, dtype=bool)
    if len(mesh.polygons) == 0:
        return {"border": empty, "material": empty.copy(), "seam": empty.copy()}
    corner_vertex, corner_edge = corner_arrays(mesh)
    totals, material = face_arrays(mesh)
    corner_material = np.repeat(material, totals)
    ends = edge_ends(mesh)
    edge_count = len(mesh.edges)
    return {
        "border": vertex_flags(ends, border_edges(corner_edge, edge_count), count),
        "material": vertex_flags(ends, material_edges(corner_edge, corner_material, edge_count), count),
        "seam": uv_split_vertices(mesh, corner_vertex),
    }


def feature_counts(mesh):
    return {name: int(flags.sum()) for name, flags in feature_vertices(mesh).items()}
