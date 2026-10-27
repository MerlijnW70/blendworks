import bmesh
import bpy
import numpy

ZERO_AREA = 1e-12
SLIVER_ASPECT = 1000.0
UV_MATCH = 1.0 / 2048.0
ON_LINE = 1e-5


def triangles_of(name):
    mesh = bpy.data.objects[name].data
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    vertices = numpy.zeros(count * 3, dtype=numpy.int64)
    loops = numpy.zeros(count * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", vertices)
    mesh.loop_triangles.foreach_get("loops", loops)
    positions = numpy.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", positions)
    return mesh, positions.reshape(-1, 3), vertices.reshape(-1, 3), loops.reshape(-1, 3)


def shape_counts(name):
    _, positions, vertices, _ = triangles_of(name)
    a, b, c = (positions[vertices[:, index]] for index in range(3))
    area = numpy.linalg.norm(numpy.cross(b - a, c - a), axis=1) / 2.0
    longest = numpy.maximum.reduce([numpy.linalg.norm(b - a, axis=1), numpy.linalg.norm(c - b, axis=1), numpy.linalg.norm(a - c, axis=1)])
    aspect = numpy.where(area > 0, longest ** 2 / numpy.maximum(2.0 * area, 1e-300), numpy.inf)
    return {"triangles": len(area), "zero_area": int((area <= ZERO_AREA).sum()), "slivers": int(((area <= ZERO_AREA) | (aspect >= SLIVER_ASPECT)).sum())}


def unmapped_triangles(name):
    mesh, _, _, loops = triangles_of(name)
    uv = numpy.zeros(len(mesh.loops) * 2)
    mesh.uv_layers.active.uv.foreach_get("vector", uv)
    uv = uv.reshape(-1, 2)
    a, b, c = (uv[loops[:, index]] for index in range(3))
    doubled = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    return int((numpy.abs(doubled) <= 1e-14).sum())


def broken_tangents(name):
    source = bpy.data.objects[name].data
    copy = source.copy()
    try:
        bm = bmesh.new()
        bm.from_mesh(copy)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(copy)
        bm.free()
        copy.calc_tangents(uvmap=copy.uv_layers.active.name)
        tangents = numpy.zeros(len(copy.loops) * 3)
        copy.loops.foreach_get("tangent", tangents)
        lengths = numpy.linalg.norm(tangents.reshape(-1, 3), axis=1)
        return int((~numpy.isfinite(lengths) | (lengths < 0.5)).sum())
    finally:
        bpy.data.meshes.remove(copy)


def uv_breaks(name, reference=None):
    mesh = bpy.data.objects[name].data
    model = bpy.data.objects[reference] if reference is not None else None
    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        layer = bm.loops.layers.uv.active
        found = []
        for edge in bm.edges:
            if len(edge.link_faces) != 2:
                continue
            corners = []
            for face in edge.link_faces:
                corners.append({loop.vert.index: loop[layer].uv.copy() for loop in face.loops if loop.vert in edge.verts})
            if any((corners[0][index] - corners[1][index]).length > UV_MATCH for index in corners[0]):
                inside = model is not None and all(not on_surface(model, face.calc_center_median()) for face in edge.link_faces)
                found.append((edge.verts[0].co.copy(), edge.verts[1].co.copy(), edge.smooth and not inside))
        return found
    finally:
        bm.free()


def on_surface(model, point):
    found, location, _, _ = model.closest_point_on_mesh(point)
    return found and (location - point).length <= ON_LINE


def on_segments(point, segments):
    for start, end in segments:
        span = end - start
        share = max(0.0, min(1.0, (point - start).dot(span) / span.length_squared)) if span.length_squared > 0 else 0.0
        if (point - (start + span * share)).length <= ON_LINE:
            return True
    return False


def stray_seams(name, original, reference):
    segments = [(start, end) for start, end, _ in original]
    return [item for item in uv_breaks(name, reference) if item[2] and not (on_segments(item[0], segments) and on_segments(item[1], segments))]
