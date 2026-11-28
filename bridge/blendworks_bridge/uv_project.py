"""UV projection onto nearest faces."""

import math

import numpy

AREA_IGNORE = 1e-12
BASIS_EPSILON = 1.1920928955078125e-07


def read(collection, name, count, dtype):
    values = numpy.empty(count, dtype=dtype)
    collection.foreach_get(name, values)
    return values


def single(value):
    return float(numpy.float32(value))


def dot(vectors, direction):
    return vectors[:, 0] * direction[0] + vectors[:, 1] * direction[1] + vectors[:, 2] * direction[2]


class Faces:
    def __init__(self, mesh):
        faces, loops = len(mesh.polygons), len(mesh.loops)
        self.points = read(mesh.vertices, "co", len(mesh.vertices) * 3, numpy.float32).astype(numpy.float64).reshape(-1, 3)
        self.starts = read(mesh.polygons, "loop_start", faces, numpy.int64)
        totals = read(mesh.polygons, "loop_total", faces, numpy.int64)
        self.loop_vertex = read(mesh.loops, "vertex_index", loops, numpy.int64)
        self.face_of_loop = numpy.repeat(numpy.arange(faces), totals)
        self.normals, self.areas = self.vector_areas(totals)

    def vector_areas(self, totals):
        loops = numpy.arange(len(self.loop_vertex))
        firsts = self.starts[self.face_of_loop]
        following = numpy.where(loops == firsts + totals[self.face_of_loop] - 1, firsts, loops + 1)
        origin = self.points[self.loop_vertex[firsts]]
        a = self.points[self.loop_vertex] - origin
        b = self.points[self.loop_vertex[following]] - origin
        cross = numpy.stack([a[:, 1] * b[:, 2] - a[:, 2] * b[:, 1], a[:, 2] * b[:, 0] - a[:, 0] * b[:, 2], a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]], axis=1)
        vectors = numpy.add.reduceat(cross, self.starts, axis=0) if len(self.starts) else numpy.zeros((0, 3))
        length = numpy.sqrt(vectors[:, 0] * vectors[:, 0] + vectors[:, 1] * vectors[:, 1] + vectors[:, 2] * vectors[:, 2])
        normals = numpy.divide(vectors, length[:, None], out=numpy.zeros_like(vectors), where=length[:, None] > 0)
        return normals, 0.5 * length


def projection_normals(normals, limit):
    half_cos, limit_cos = single(math.cos(limit / 2)), single(math.cos(limit))
    count = len(normals)
    tagged = numpy.zeros(count, dtype=bool)
    closest = numpy.full(count, -1.0)
    projections = []
    seed, group = normals[0], numpy.zeros(0, dtype=numpy.int64)
    while True:
        near = numpy.nonzero(~tagged & (dot(normals, seed) > half_cos))[0]
        tagged[near] = True
        members = numpy.concatenate([group, near])
        total = numpy.zeros(3)
        for member in members.tolist():
            total = total + normals[member]
        length = math.sqrt(float(total[0] * total[0] + total[1] * total[1] + total[2] * total[2]))
        if length != 0.0:
            projection = total / length
            projections.append(projection)
            closest = numpy.maximum(closest, dot(normals, projection))
        open_faces = numpy.nonzero(~tagged)[0]
        if len(open_faces) == 0:
            break
        best = float(closest[open_faces].min())
        if not best < limit_cos:
            break
        chosen = int(open_faces[closest[open_faces] == best].max())
        seed, group = normals[chosen], numpy.array([chosen], dtype=numpy.int64)
        tagged[chosen] = True
    return projections


def nearest_projection(normals, projections):
    best = dot(normals, projections[0])
    index = numpy.zeros(len(normals), dtype=numpy.int64)
    for number, projection in enumerate(projections[1:], start=1):
        value = dot(normals, projection)
        better = value > best
        best = numpy.where(better, value, best)
        index = numpy.where(better, number, index)
    return index


def plane_basis(normal):
    x, y, z = (float(value) for value in normal)
    flat = x * x + y * y
    if flat > BASIS_EPSILON:
        scale = 1.0 / math.sqrt(flat)
        first = (y * scale, -x * scale, 0.0)
        return first, (-z * first[1], z * first[0], x * first[1] - y * first[0])
    return (-1.0 if z < 0.0 else 1.0, 0.0, 0.0), (0.0, 1.0, 0.0)


def project_by_angle(obj, angle_limit):
    mesh = obj.data
    faces = Faces(mesh)
    kept = numpy.nonzero(faces.areas > AREA_IGNORE)[0]
    order = kept[numpy.argsort(-faces.areas[kept], kind="stable")]
    uv = numpy.zeros((len(mesh.loops), 2))
    if len(order):
        projections = projection_normals(faces.normals[order], angle_limit)
        chosen = numpy.full(len(mesh.polygons), -1, dtype=numpy.int64)
        chosen[order] = nearest_projection(faces.normals[order], projections)
        bases = numpy.array([plane_basis(projection) for projection in projections])
        loop_projection = chosen[faces.face_of_loop]
        projected = numpy.nonzero(loop_projection >= 0)[0]
        points = faces.points[faces.loop_vertex[projected]]
        for axis in range(2):
            uv[projected, axis] = dot(points, bases[loop_projection[projected], axis].T)
    mesh.uv_layers.active.uv.foreach_set("vector", uv.astype(numpy.float32).reshape(-1))
    mesh.update()
    return len(order)
