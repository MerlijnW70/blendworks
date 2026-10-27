from dataclasses import dataclass

import bmesh
import numpy
from mathutils.geometry import barycentric_transform
from mathutils.kdtree import KDTree

from .flatfill import area_vector, fill_polygons, merge_flat

SLIVER_AREA = 1e-12
SLIVER_ASPECT = 1000.0
CAP_COSINE = -0.5
MAX_PASSES = 40
FLAT_ANGLE = 0.001
UV_JOIN = 1e-6
TILT_COSINE = 0.99985


@dataclass
class Limits:
    reach: float
    floor: float
    aspect: float
    height: float = 0.0


def loop_triangles(bm):
    triangles = bm.calc_loop_triangles()
    bm.verts.index_update()
    table = numpy.array([[loop.vert.index for loop in triangle] for triangle in triangles], dtype=numpy.int64).reshape(-1, 3)
    return triangles, table


def triangle_shapes(bm, table):
    if len(table) == 0:
        return numpy.empty(0), numpy.empty(0), numpy.empty(0)
    coordinates = numpy.array([vert.co[:] for vert in bm.verts], dtype=numpy.float64)
    a, b, c = coordinates[table[:, 0]], coordinates[table[:, 1]], coordinates[table[:, 2]]
    area = numpy.linalg.norm(numpy.cross(b - a, c - a), axis=1) / 2.0
    longest = numpy.maximum.reduce([numpy.linalg.norm(b - a, axis=1), numpy.linalg.norm(c - b, axis=1), numpy.linalg.norm(a - c, axis=1)])
    aspect = numpy.where(area > 0, longest ** 2 / numpy.maximum(2.0 * area, 1e-300), numpy.inf)
    return area, aspect, longest


def uv_aspects(bm, triangles):
    layer = bm.loops.layers.uv.active
    if layer is None or not triangles:
        return numpy.zeros(len(triangles))
    corners = numpy.array([[loop[layer].uv[:] for loop in triangle] for triangle in triangles], dtype=numpy.float64)
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    doubled = numpy.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    longest = numpy.maximum.reduce([numpy.linalg.norm(b - a, axis=1), numpy.linalg.norm(c - b, axis=1), numpy.linalg.norm(a - c, axis=1)])
    return numpy.where(doubled > 0, longest ** 2 / numpy.maximum(doubled, 1e-300), numpy.inf)


def quality(bm, floor, ceiling, height=0.0):
    triangles, table = loop_triangles(bm)
    area, aspect, longest = triangle_shapes(bm, table)
    low = 2.0 * area <= height * longest
    flat_uv = uv_aspects(bm, triangles) >= ceiling
    shaped = (area <= floor) | (aspect >= ceiling)
    bad = shaped | low | flat_uv
    sound = area > floor
    return [(triangles[int(index)], bool(shaped[index] or low[index])) for index in numpy.nonzero(bad)[0]], {
        "triangles": len(table),
        "zero_area": int((~sound).sum()),
        "slivers": int(shaped.sum()),
        "worst_aspect": round(float(aspect[sound].max()), 3) if sound.any() else 0.0,
        "thin": int((low & ~shaped).sum()),
        "flat_uv": int(flat_uv.sum()),
    }


def neighbours(vert):
    return {edge.other_vert(vert) for edge in vert.link_edges}


def link_condition(keep, gone, edge):
    sides = set(edge.link_faces)
    if len(sides) != 2 or any(gone in face.verts for face in keep.link_faces if face not in sides):
        return False
    allowed = {next(vert for vert in face.verts if vert not in (keep, gone)) for face in sides if len(face.verts) == 3}
    return neighbours(keep) & neighbours(gone) <= allowed


def stays_sound(face, moved, position, limits):
    before = area_vector([vert.co for vert in face.verts])
    if before.length <= 2.0 * limits.floor:
        return True
    after = area_vector([position if vert in moved else vert.co for vert in face.verts])
    if after.length > 0 and after.dot(before) <= 0:
        return False
    corners = [vert.co for vert in face.verts]
    if after.length > 0 and len(corners) == 3 and aspect_of(*corners) < limits.aspect and after.normalized().dot(before.normalized()) < TILT_COSINE:
        return False
    unit = before.normalized()
    return all(abs((position - vert.co).dot(unit)) <= limits.reach for vert in face.verts if vert in moved)


def moves_safely(moved, position, limits, skip=()):
    before_worst = after_worst = 0.0
    for face in {face for vert in moved for face in vert.link_faces}:
        if len(face.verts) == 3:
            before_worst = max(before_worst, aspect_of(*(vert.co for vert in face.verts)))
        if face in skip or sum(1 for vert in face.verts if vert in moved) > 1:
            continue
        if not stays_sound(face, moved, position, limits):
            return False
        if len(face.verts) == 3:
            after_worst = max(after_worst, aspect_of(*(position if vert in moved else vert.co for vert in face.verts)))
    return after_worst < limits.aspect or after_worst < before_worst


def moved_uvs(gone, keep, layer):
    moved = []
    for face in gone.link_faces:
        if keep in face.verts:
            continue
        loop = next(item for item in face.loops if item.vert is gone)
        corners = [loop, loop.link_loop_next, loop.link_loop_prev]
        points = [item.vert.co for item in corners]
        normal = (points[1] - points[0]).cross(points[2] - points[0])
        if normal.length == 0:
            continue
        target = keep.co - normal.normalized() * (keep.co - points[0]).dot(normal.normalized())
        moved.append((face, barycentric_transform(target, *points, *(item[layer].uv.to_3d() for item in corners)).to_2d()))
    return moved


def collapse(bm, keep, gone, limits):
    edge = bm.edges.get((keep, gone))
    if edge is None:
        if not (keep.is_boundary and gone.is_boundary):
            return False
    else:
        if not link_condition(keep, gone, edge) or (keep.is_boundary and gone.is_boundary and not edge.is_boundary):
            return False
    if not moves_safely({keep, gone}, keep.co.copy(), limits):
        return False
    layer = bm.loops.layers.uv.active
    moved = moved_uvs(gone, keep, layer) if layer is not None else []
    bmesh.ops.pointmerge(bm, verts=[keep, gone], merge_co=keep.co.copy())
    for face, uv in moved:
        if face.is_valid:
            for loop in face.loops:
                if loop.vert is keep:
                    loop[layer].uv = uv
    for face in keep.link_faces:
        face.normal_update()
    return True


def merge_close(bm, distance, limits):
    if distance <= 0 or not bm.verts:
        return 0
    verts = list(bm.verts)
    tree = KDTree(len(verts))
    for index, vert in enumerate(verts):
        tree.insert(vert.co, index)
    tree.balance()
    merged = 0
    for vert in verts:
        if not vert.is_valid:
            continue
        for _, index, _ in sorted(tree.find_range(vert.co, distance), key=lambda found: (found[2], found[1])):
            other = verts[index]
            if other is vert or not other.is_valid or not vert.is_valid:
                continue
            if collapse(bm, vert, other, limits):
                merged += 1
    return merged


def ordered_edges(face):
    return sorted(face.edges, key=lambda edge: edge.calc_length())


def split_outcome(face, edge, apex, target, onto_edge, limits):
    start, end = edge.verts
    others = [item for item in edge.link_faces if item is not face]
    if len(others) != 1 or len(others[0].verts) != 3:
        return None
    opposite = next(vert for vert in others[0].verts if vert not in (start, end))
    point = target if onto_edge else apex.co
    involved = [face, others[0]] + [item for item in apex.link_faces if item is not face]
    if any(len(item.verts) != 3 for item in involved):
        return None
    before = max(aspect_of(*(vert.co for vert in item.verts)) for item in involved)
    plane = area_vector([vert.co for vert in others[0].verts])
    halves = [area_vector([start.co, point, opposite.co]), area_vector([point, end.co, opposite.co])]
    if plane.length <= limits.floor or any(half.dot(plane) <= 0 or half.length <= limits.floor for half in halves):
        return None
    if abs((point - start.co).dot(plane.normalized())) > limits.reach:
        return None
    after = [aspect_of(start.co, point, opposite.co), aspect_of(point, end.co, opposite.co)]
    if onto_edge:
        for item in involved[2:]:
            if not stays_sound(item, {apex}, target, limits):
                return None
            after.append(aspect_of(*(target if vert is apex else vert.co for vert in item.verts)))
    worst = max(after)
    return worst if worst < before else None


def split_towards(bm, face, edge, apex, limits):
    start, end = edge.verts
    span = end.co - start.co
    if span.length_squared == 0:
        return False
    share = (apex.co - start.co).dot(span) / span.length_squared
    if not 0.0 < share < 1.0:
        return False
    target = start.co + span * share
    choices = [(split_outcome(face, edge, apex, target, onto, limits), onto) for onto in (True, False)]
    choices = [choice for choice in choices if choice[0] is not None]
    if not choices:
        return False
    onto_edge = min(choices, key=lambda choice: choice[0])[1]
    opposite = next(vert for item in edge.link_faces if item is not face for vert in item.verts if vert not in (start, end))
    _, middle = bmesh.utils.edge_split(edge, start, share)
    for item in list(middle.link_faces):
        corners = {vert for vert in item.verts}
        if apex in corners:
            bmesh.utils.face_split(item, middle, apex)
        elif opposite in corners:
            bmesh.utils.face_split(item, middle, opposite)
    for item in middle.link_faces:
        item.normal_update()
    if onto_edge:
        return collapse(bm, middle, apex, limits)
    return collapse(bm, apex, middle, limits)


def aspect_of(a, b, c):
    area = (b - a).cross(c - a).length / 2.0
    longest = max((b - a).length, (c - b).length, (a - c).length)
    return longest ** 2 / (2.0 * area) if area > 0 else float("inf")


def flip_better(bm, face, edge, limits):
    others = [item for item in edge.link_faces if item is not face]
    if len(others) != 1 or len(others[0].verts) != 3 or len(face.verts) != 3:
        return False
    loop = next(item for item in face.loops if item.edge is edge)
    start, end, apex = loop.vert, loop.link_loop_next.vert, loop.link_loop_prev.vert
    opposite = next(vert for vert in others[0].verts if vert not in (start, end))
    if bm.edges.get((apex, opposite)) is not None:
        return False
    plane = area_vector([start.co, end.co, apex.co])
    if plane.length <= limits.floor or abs((opposite.co - start.co).dot(plane.normalized())) > limits.reach:
        return False
    first, second = area_vector([start.co, opposite.co, apex.co]), area_vector([opposite.co, end.co, apex.co])
    if first.dot(plane) <= 0 or second.dot(plane) <= 0 or first.length <= limits.floor or second.length <= limits.floor:
        return False
    if min(first.normalized().dot(plane.normalized()), second.normalized().dot(plane.normalized())) < TILT_COSINE and aspect_of(start.co, end.co, apex.co) < limits.aspect:
        return False
    before = max(aspect_of(start.co, end.co, apex.co), aspect_of(start.co, end.co, opposite.co))
    after = max(aspect_of(start.co, opposite.co, apex.co), aspect_of(opposite.co, end.co, apex.co))
    layer = bm.loops.layers.uv.active
    if layer is not None:
        mine = {item.vert: item[layer].uv.to_3d() for item in face.loops}
        theirs = {item.vert: item[layer].uv.to_3d() for item in others[0].loops}
        if (mine[start] - theirs[start]).length > UV_JOIN or (mine[end] - theirs[end]).length > UV_JOIN:
            return False
        before = max(before, aspect_of(mine[start], mine[end], mine[apex]), aspect_of(theirs[start], theirs[end], theirs[opposite]))
        after = max(after, aspect_of(mine[start], theirs[opposite], mine[apex]), aspect_of(theirs[opposite], mine[end], mine[apex]))
    if after >= before:
        return False
    rotated = bmesh.utils.edge_rotate(edge, True)
    if rotated is None:
        return False
    for item in rotated.link_faces:
        item.normal_update()
    return True


def bisect(bm, edge):
    if any(len(face.verts) != 3 for face in edge.link_faces):
        return False
    _, middle = bmesh.utils.edge_split(edge, edge.verts[0], 0.5)
    for face in list(middle.link_faces):
        if len(face.verts) == 4:
            loop = next(item for item in face.loops if item.vert is middle)
            bmesh.utils.face_split(face, middle, loop.link_loop_next.link_loop_next.vert)
    for face in middle.link_faces:
        face.normal_update()
    return True


def fix_needle(bm, face, limits):
    first, second = ordered_edges(face)[0].verts
    return collapse(bm, first, second, limits) or collapse(bm, second, first, limits)


def is_cap(lengths):
    shortest, middle, longest = lengths
    if shortest == 0:
        return False
    return (shortest ** 2 + middle ** 2 - longest ** 2) / (2.0 * shortest * middle) < CAP_COSINE


def fix_triangle(bm, face, limits, shaped):
    edges = ordered_edges(face)
    longest = edges[-1]
    polygons = [item for edge in edges[1:] for item in edge.link_faces if len(item.verts) > 3]
    if polygons and fill_polygons(bm, sorted(set(polygons), key=lambda item: item.index)):
        return "faces_retriangulated"
    if face.calc_area() > limits.floor:
        for edge in reversed(edges):
            if flip_better(bm, face, edge, limits):
                return "edges_flipped"
    if not shaped:
        return None
    if is_cap([edge.calc_length() for edge in edges]):
        apex = next(vert for vert in face.verts if vert not in longest.verts)
        if split_towards(bm, face, longest, apex, limits):
            return "slivers_split"
    if fix_needle(bm, face, limits):
        return "edges_collapsed"
    if face.calc_area() > limits.floor and bisect(bm, longest):
        return "edges_bisected"
    return None


def repair(bm, limits):
    counts = {"faces_retriangulated": 0, "edges_flipped": 0, "slivers_split": 0, "edges_collapsed": 0, "edges_bisected": 0}
    counts["faces_merged"], counts["vertices_dissolved"] = merge_flat(bm, FLAT_ANGLE)
    for _ in range(MAX_PASSES):
        bm.normal_update()
        bad, _ = quality(bm, limits.floor, limits.aspect, limits.height)
        if not bad:
            break
        bm.faces.index_update()
        shaped = {triangle[0].face for triangle, geometric in bad if geometric}
        owners = sorted({triangle[0].face for triangle, _ in bad}, key=lambda face: face.index)
        polygons = [face for face in owners if len(face.verts) > 3]
        filled = fill_polygons(bm, polygons)
        counts["faces_retriangulated"] += filled
        if filled:
            continue
        progress = 0
        for face in owners:
            if not face.is_valid or len(face.verts) != 3:
                continue
            outcome = fix_triangle(bm, face, limits, face in shaped)
            if outcome is not None:
                counts[outcome] += 1
                progress += 1
        if progress == 0:
            break
    return counts
