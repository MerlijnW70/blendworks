import numpy

ATTRIBUTES = ("slope", "height", "curvature")


def world_arrays(obj):
    mesh = obj.data
    count = len(mesh.vertices)
    local = numpy.empty(count * 3)
    mesh.vertices.foreach_get("co", local)
    matrix = numpy.array(obj.matrix_world)
    return local.reshape(count, 3) @ matrix[:3, :3].T + matrix[:3, 3], matrix[:3, :3]


def polygon_vertex_index(mesh):
    totals = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_total", totals)
    corners = numpy.empty(len(mesh.loops), dtype=numpy.int64)
    mesh.loops.foreach_get("vertex_index", corners)
    return numpy.repeat(numpy.arange(len(totals)), totals), corners


def face_normals(mesh, linear):
    normals = numpy.empty(len(mesh.polygons) * 3)
    mesh.polygons.foreach_get("normal", normals)
    areas = numpy.empty(len(mesh.polygons))
    mesh.polygons.foreach_get("area", areas)
    return normals.reshape(-1, 3) @ numpy.linalg.inv(linear), areas


def surface_corners(mesh, surface):
    faces, corners = polygon_vertex_index(mesh)
    kept = faces < surface[0]
    return faces[kept], corners[kept]


def slope_values(obj, linear, surface):
    mesh = obj.data
    normals, areas = face_normals(mesh, linear)
    length = numpy.linalg.norm(normals, axis=1)
    cosine = numpy.divide(normals[:, 2], length, out=numpy.ones(len(normals)), where=length > 0)
    slopes = numpy.degrees(numpy.arccos(numpy.clip(cosine, -1.0, 1.0)))
    faces, corners = surface_corners(mesh, surface)
    total = numpy.zeros(len(mesh.vertices))
    weight = numpy.zeros(len(mesh.vertices))
    numpy.add.at(total, corners, slopes[faces] * areas[faces])
    numpy.add.at(weight, corners, areas[faces])
    return numpy.divide(total, weight, out=numpy.zeros_like(total), where=weight > 0)


def vertex_normals(mesh, linear, surface):
    normals, areas = face_normals(mesh, linear)
    faces, corners = surface_corners(mesh, surface)
    summed = numpy.zeros((len(mesh.vertices), 3))
    numpy.add.at(summed, corners, normals[faces] / numpy.maximum(numpy.linalg.norm(normals[faces], axis=1), 1e-30)[:, None] * areas[faces][:, None])
    return summed / numpy.maximum(numpy.linalg.norm(summed, axis=1), 1e-30)[:, None]


def curvature_values(obj, points, linear, surface):
    mesh = obj.data
    count = len(points)
    edges = numpy.empty(len(mesh.edges) * 2, dtype=numpy.int64)
    mesh.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    edges = edges[(edges < surface[1]).all(axis=1)]
    normals = vertex_normals(mesh, linear, surface)
    centroid = numpy.zeros((count, 3))
    squared = numpy.zeros(count)
    degree = numpy.zeros(count)
    for first, second in ((edges[:, 0], edges[:, 1]), (edges[:, 1], edges[:, 0])):
        numpy.add.at(centroid, first, points[second])
        numpy.add.at(squared, first, numpy.sum((points[second] - points[first]) ** 2, axis=1))
        numpy.add.at(degree, first, 1.0)
    safe = numpy.maximum(degree, 1.0)
    pull = numpy.einsum("ij,ij->i", centroid / safe[:, None] - points, normals)
    mean_square = squared / safe
    return numpy.divide(-2.0 * pull, mean_square, out=numpy.zeros(count), where=mean_square > 0)


def write_float_attribute(mesh, name, values):
    existing = mesh.attributes.get(name)
    if existing is not None:
        mesh.attributes.remove(existing)
    attribute = mesh.attributes.new(name, "FLOAT", "POINT")
    attribute.data.foreach_set("value", numpy.ascontiguousarray(values, dtype=numpy.float32))


def write_attributes(obj, names, surface_faces=None, surface_vertices=None):
    mesh = obj.data
    surface = (len(mesh.polygons) if surface_faces is None else surface_faces, len(mesh.vertices) if surface_vertices is None else surface_vertices)
    mesh.update()
    points, linear = world_arrays(obj)
    written = {}
    for name in names:
        if name == "slope":
            written[name] = slope_values(obj, linear, surface)
        elif name == "height":
            written[name] = points[:, 2]
        elif name == "curvature":
            written[name] = curvature_values(obj, points, linear, surface)
        write_float_attribute(mesh, name, written[name])
    return {name: [float(values.min()), float(values.max())] for name, values in written.items() if len(values)}
