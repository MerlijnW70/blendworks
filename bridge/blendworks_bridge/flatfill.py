"""Flat polygon fill: dissolving flat faces and constrained Delaunay filling."""

import bmesh
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

from .topology import manifold_report


def area_vector(corners):
    origin = corners[0]
    total = origin * 0.0
    for index in range(1, len(corners) - 1):
        total = total + (corners[index] - origin).cross(corners[index + 1] - origin)
    return total / 2.0


def dissolve_flat(bm, angle):
    bmesh.ops.dissolve_limit(bm, angle_limit=angle, use_dissolve_boundaries=False, verts=list(bm.verts), edges=list(bm.edges), delimit={"MATERIAL", "SEAM", "SHARP", "UV"})


def keeps_closed(bm, operation):
    trial = bm.copy()
    try:
        closed = manifold_report(trial)["manifold"]
        operation(trial)
        return not closed or manifold_report(trial)["manifold"]
    finally:
        trial.free()


def guarded(bm, operation):
    if not keeps_closed(bm, operation):
        return False
    operation(bm)
    return True


def merge_flat(bm, angle):
    faces, verts = len(bm.faces), len(bm.verts)
    guarded(bm, lambda target: dissolve_flat(target, angle))
    return faces - len(bm.faces), verts - len(bm.verts)


def inside_polygon(point, polygon):
    result = False
    for index, start in enumerate(polygon):
        end = polygon[index - 1]
        if (start.y > point.y) != (end.y > point.y) and point.x < start.x + (point.y - start.y) * (end.x - start.x) / (end.y - start.y):
            result = not result
    return result


def cdt_fill(bm, face):
    normal = area_vector([vert.co for vert in face.verts])
    if normal.length == 0:
        return False
    normal.normalize()
    across = normal.orthogonal().normalized()
    up = normal.cross(across)
    loops = list(face.loops)
    origin = loops[0].vert.co.copy()
    points = [Vector(((loop.vert.co - origin).dot(across), (loop.vert.co - origin).dot(up))) for loop in loops]
    count = len(points)
    vertices, _, faces, sources, _, _ = delaunay_2d_cdt(points, [(index, (index + 1) % count) for index in range(count)], [], 1, 0.0)
    if len(vertices) != count or any(len(source) != 1 for source in sources):
        return False
    original = [source[0] for source in sources]
    triangles = []
    for item in faces:
        a, b, c = (original[index] for index in item)
        if not inside_polygon((points[a] + points[b] + points[c]) / 3.0, points):
            continue
        if (points[b] - points[a]).cross(points[c] - points[a]) < 0:
            b, c = c, b
        triangles.append((a, b, c))
    if len(triangles) != count - 2:
        return False
    for triangle in triangles:
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            if (second - first) % count not in (1, count - 1) and bm.edges.get((loops[first].vert, loops[second].vert)) is not None:
                return False
    made = []
    for triangle in triangles:
        try:
            new = bm.faces.new([loops[index].vert for index in triangle], face)
        except ValueError:
            for item in made:
                bm.faces.remove(item)
            return False
        for loop, index in zip(new.loops, triangle):
            loop.copy_from(loops[index])
        made.append(new)
    bm.faces.remove(face)
    for item in made:
        item.normal_update()
    return True


def fill_polygons(bm, faces):
    return sum(1 for face in faces if face.is_valid and cdt_fill(bm, face))
