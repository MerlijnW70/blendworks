import math

import bmesh
import numpy

from .flatfill import guarded
from .slivers import SLIVER_AREA, Limits, merge_close, quality, repair
from .topology import manifold_report

MAX_REPAIR_PASSES = 12


def triangle_table(bm):
    triangles = bm.calc_loop_triangles()
    bm.verts.index_update()
    table = numpy.array([[loop.vert.index for loop in triangle] for triangle in triangles], dtype=numpy.int64).reshape(-1, 3)
    owners = [triangle[0].face for triangle in triangles]
    return table, owners


def triangle_altitudes(bm, table):
    if len(table) == 0:
        return numpy.empty(0)
    coordinates = numpy.array([vert.co[:] for vert in bm.verts], dtype=numpy.float64)
    a, b, c = coordinates[table[:, 0]], coordinates[table[:, 1]], coordinates[table[:, 2]]
    twice_area = numpy.linalg.norm(numpy.cross(b - a, c - a), axis=1)
    longest = numpy.maximum.reduce([numpy.linalg.norm(b - a, axis=1), numpy.linalg.norm(c - b, axis=1), numpy.linalg.norm(a - c, axis=1)])
    return twice_area / numpy.maximum(longest, 1e-300)


def sliver_faces(bm, tolerance):
    table, owners = triangle_table(bm)
    altitudes = triangle_altitudes(bm, table)
    bad = {}
    for index in numpy.nonzero(altitudes <= tolerance)[0]:
        face = owners[int(index)]
        bad[face] = bad.get(face, 0) + 1
    return bad, int((altitudes <= tolerance).sum())


def altitude_of(a, b, c):
    twice_area = (b - a).cross(c - a).length
    longest = max((b - a).length, (c - b).length, (a - c).length)
    return twice_area / longest if longest > 0 else 0.0


def collinear_vertices(bm, tolerance):
    found = []
    for vert in bm.verts:
        if len(vert.link_edges) != 2 or not 1 <= len(vert.link_faces) <= 2:
            continue
        first, second = vert.link_edges
        if first.seam != second.seam or first.smooth != second.smooth:
            continue
        if any(len(face.verts) < 4 for face in vert.link_faces):
            continue
        a, c = first.other_vert(vert).co, second.other_vert(vert).co
        span = c - a
        if span.length <= tolerance:
            continue
        along = (vert.co - a).dot(span) / span.length_squared
        if not 0.0 < along < 1.0:
            continue
        if (vert.co - (a + span * along)).length <= tolerance:
            found.append(vert)
    return found


def dissolve_collinear(bm, tolerance):
    removed = 0
    for _ in range(MAX_REPAIR_PASSES):
        found = collinear_vertices(bm, tolerance)
        if not found:
            break
        before = len(bm.verts)
        bmesh.ops.dissolve_verts(bm, verts=found)
        removed += before - len(bm.verts)
        if len(bm.verts) == before:
            break
    return removed


def corner_of(face, vert):
    return next(loop for loop in face.loops if loop.vert == vert)


def flip_candidates(face):
    corners = list(face.loops)
    for loop in corners:
        edge = loop.edge
        if len(edge.link_faces) != 2:
            continue
        other = next(item for item in edge.link_faces if item != face)
        yield loop, other


def faces_up(corners, reference):
    a, b, c = (vert.co for vert in corners)
    return (b - a).cross(c - a).dot(reference) > 0


def flip_into(bm, sliver, loop, other, tolerance):
    x, y = loop.vert, loop.link_loop_next.vert
    apex = loop.link_loop_prev.vert
    neighbour = next((item for item in other.loops if item.vert == y and item.link_loop_next.vert == x), None)
    if neighbour is None or len(other.verts) != 3:
        return False
    opposite = neighbour.link_loop_prev.vert
    if bm.edges.get((apex, opposite)) is not None:
        return False
    old_quality = min(altitude_of(x.co, y.co, apex.co), altitude_of(y.co, x.co, opposite.co))
    new_quality = min(altitude_of(x.co, opposite.co, apex.co), altitude_of(opposite.co, y.co, apex.co))
    if new_quality <= tolerance or new_quality <= old_quality:
        return False
    if not (faces_up((x, opposite, apex), other.normal) and faces_up((opposite, y, apex), other.normal)):
        return False
    rebuild(bm, sliver, other, x, y, apex, opposite)
    return True


LOOP_LAYER_KINDS = ("uv", "color", "float_color", "float", "int", "float_vector", "bool")


def copy_corner(bm, target, donor):
    for kind in LOOP_LAYER_KINDS:
        for layer in getattr(bm.loops.layers, kind).values():
            value = donor[layer]
            target[layer] = value.copy() if hasattr(value, "copy") else value


def rebuild(bm, sliver, other, x, y, apex, opposite):
    uv_layers = list(bm.loops.layers.uv.values())
    source = {vert: corner_of(other, vert) for vert in (x, y, opposite)}
    span = y.co - x.co
    along = (apex.co - x.co).dot(span) / span.length_squared if span.length_squared > 0 else 0.0
    along = min(max(along, 0.0), 1.0)
    uv_at_apex = [source[x][layer].uv.lerp(source[y][layer].uv, along) for layer in uv_layers]
    for corners in ((x, opposite, apex), (opposite, y, apex)):
        face = bm.faces.new(corners, other)
        for loop in face.loops:
            copy_corner(bm, loop, source.get(loop.vert) or source[x])
            if loop.vert == apex:
                for layer, uv in zip(uv_layers, uv_at_apex):
                    loop[layer].uv = uv
        face.normal_update()
    bm.faces.remove(sliver)
    bm.faces.remove(other)
    for edge in list(x.link_edges):
        if edge.other_vert(x) == y and not edge.link_faces:
            bm.edges.remove(edge)


def repair_slivers(bm, tolerance):
    retriangulated = flipped = 0
    for _ in range(MAX_REPAIR_PASSES):
        bm.normal_update()
        bad, count = sliver_faces(bm, tolerance)
        if count == 0:
            break
        polygons = [face for face in bad if len(face.verts) > 3]
        if polygons:
            bmesh.ops.triangulate(bm, faces=polygons, quad_method="BEAUTY", ngon_method="BEAUTY")
            retriangulated += len(polygons)
            continue
        progress = 0
        for sliver in list(bad):
            if not sliver.is_valid:
                continue
            for loop, other in sorted(flip_candidates(sliver), key=lambda pair: -pair[0].edge.calc_length()):
                if len(other.verts) > 3:
                    bmesh.ops.triangulate(bm, faces=[other], quad_method="BEAUTY", ngon_method="BEAUTY")
                    retriangulated += 1
                    progress += 1
                    break
                if flip_into(bm, sliver, loop, other, tolerance):
                    flipped += 1
                    progress += 1
                    break
        if progress == 0:
            break
    return retriangulated, flipped


def remove_loose(bm):
    edges = [edge for edge in bm.edges if not edge.link_faces]
    vertices = len(bm.verts)
    bmesh.ops.delete(bm, geom=edges, context="EDGES")
    bmesh.ops.delete(bm, geom=[vert for vert in bm.verts if not vert.link_edges], context="VERTS")
    return len(edges), vertices - len(bm.verts)


def recalc_normals(bm):
    bm.normal_update()
    before = [face.normal.copy() for face in bm.faces]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    return sum(1 for old, face in zip(before, bm.faces) if old.dot(face.normal) < 0)


def clean_bmesh(bm, tolerance, merge_distance, area_floor=SLIVER_AREA, aspect_ceiling=None):
    start = manifold_report(bm)
    _, degenerate_before = sliver_faces(bm, tolerance)
    report = {"degenerate_triangles_before": degenerate_before}
    limits = Limits(max(merge_distance, tolerance), area_floor, aspect_ceiling or math.inf, tolerance)
    loose_edges, loose_vertices = remove_loose(bm)
    vertices = len(bm.verts)
    bm.normal_update()
    merge_close(bm, merge_distance, limits)
    report["merged_vertices"] = vertices - len(bm.verts)
    faces = len(bm.faces)
    guarded(bm, lambda target: bmesh.ops.dissolve_degenerate(target, dist=tolerance, edges=target.edges))
    report["dissolved_faces"] = faces - len(bm.faces)
    report["collinear_vertices_removed"] = dissolve_collinear(bm, tolerance)
    report["faces_retriangulated"], report["edges_flipped"] = repair_slivers(bm, tolerance)
    if aspect_ceiling is not None:
        for key, value in repair(bm, limits).items():
            report[key] = report.get(key, 0) + value
    extra_edges, extra_vertices = remove_loose(bm)
    report["loose_edges_removed"] = loose_edges + extra_edges
    report["loose_vertices_removed"] = loose_vertices + extra_vertices
    closed = manifold_report(bm)["manifold"]
    report["normals_flipped"] = recalc_normals(bm) if closed else 0
    _, report["degenerate_triangles_after"] = sliver_faces(bm, tolerance)
    if aspect_ceiling is not None:
        report["quality"] = quality(bm, area_floor, aspect_ceiling, tolerance)[1]
    return report, start["manifold"], closed
