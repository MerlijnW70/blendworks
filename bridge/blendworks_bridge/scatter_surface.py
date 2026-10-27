import bpy
import numpy

from .errors import bad_args, not_found

DEGENERATE_AREA = 1e-14


class Surface:
    def __init__(self, corners, polygon, normals, smooth, vertex_ids, loop_ids):
        centres = corners.mean(axis=1)
        order = numpy.lexsort((centres[:, 2], centres[:, 1], centres[:, 0]))
        self.order = order
        self.corners = corners[order]
        self.polygon = polygon[order]
        self.normals = normals[order]
        self.smooth = smooth[order]
        self.vertex_ids = vertex_ids[order]
        self.loop_ids = loop_ids[order]
        cross = numpy.cross(self.corners[:, 1] - self.corners[:, 0], self.corners[:, 2] - self.corners[:, 0])
        self.areas = 0.5 * numpy.linalg.norm(cross, axis=1)
        self.cumulative = numpy.cumsum(numpy.where(self.areas > DEGENERATE_AREA, self.areas, 0.0))
        self.smooth_normals = corner_normals(self.normals, self.areas, self.vertex_ids)
        self.attribute = None
        self.weights = None

    @property
    def area(self):
        return float(self.cumulative[-1]) if len(self.cumulative) else 0.0

    def pick(self, triangle_draw, first, second):
        triangle = numpy.minimum(numpy.searchsorted(self.cumulative, triangle_draw * self.area, side="right"), len(self.areas) - 1)
        root = numpy.sqrt(first)
        weights = numpy.column_stack([1.0 - root, root * (1.0 - second), root * second])
        return triangle, weights

    def positions(self, triangle, weights):
        return numpy.einsum("ij,ijk->ik", weights, self.corners[triangle])

    def interpolate(self, values, triangle, weights):
        return numpy.einsum("ij,ij->i", weights, values[triangle])

    def surface_normals(self, triangle, weights):
        blended = numpy.einsum("ij,ijk->ik", weights, self.smooth_normals[triangle])
        length = numpy.linalg.norm(blended, axis=1)
        blended = numpy.divide(blended, length[:, None], out=self.normals[triangle].copy(), where=length[:, None] > 1e-12)
        return numpy.where(self.smooth[triangle][:, None], blended, self.normals[triangle])


def corner_normals(normals, areas, vertex_ids):
    totals = numpy.zeros((int(vertex_ids.max()) + 1, 3))
    for corner in range(3):
        numpy.add.at(totals, vertex_ids[:, corner], normals * areas[:, None])
    return unit_rows(totals)[vertex_ids]


def unit_rows(rows):
    length = numpy.linalg.norm(rows, axis=1)
    return numpy.divide(rows, length[:, None], out=numpy.zeros_like(rows), where=length[:, None] > 0)


def vertex_group_weights(obj, mesh, name):
    group = obj.vertex_groups.get(name)
    if group is None:
        raise not_found(f"{obj.name} has no vertex group named {name}")
    values = numpy.zeros(len(mesh.vertices))
    for vertex in mesh.vertices:
        for assignment in vertex.groups:
            if assignment.group == group.index:
                values[vertex.index] = assignment.weight
    return values


def attribute_corners(mesh, name, triangles):
    attribute = mesh.attributes.get(name)
    if attribute is None:
        raise not_found(f"the target has no attribute named {name}")
    if attribute.data_type not in ("FLOAT", "INT", "FLOAT_COLOR", "BYTE_COLOR", "BOOLEAN"):
        raise bad_args(f"attribute {name} is {attribute.data_type}; scatter reads float attributes")
    if attribute.data_type in ("FLOAT_COLOR", "BYTE_COLOR"):
        raise bad_args(f"attribute {name} is a colour; scatter reads float attributes")
    values = numpy.empty(len(attribute.data), dtype=numpy.float64)
    attribute.data.foreach_get("value", values)
    if attribute.domain == "POINT":
        return values[triangles["vertices"]]
    if attribute.domain == "FACE":
        return numpy.repeat(values[triangles["polygon"]][:, None], 3, axis=1)
    if attribute.domain == "CORNER":
        return values[triangles["loops"]]
    raise bad_args(f"attribute {name} is on the {attribute.domain.lower()} domain; scatter reads point, face or corner attributes")


def read_surface(obj, depsgraph, attribute=None, group=None):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        mesh.calc_loop_triangles()
        count = len(mesh.loop_triangles)
        if count == 0:
            raise bad_args(f"{obj.name} has no faces to scatter on")
        vertex_count = len(mesh.vertices)
        local = numpy.empty(vertex_count * 3)
        mesh.vertices.foreach_get("co", local)
        matrix = numpy.array(obj.matrix_world)
        linear = matrix[:3, :3]
        world = local.reshape(-1, 3) @ linear.T + matrix[:3, 3]
        inverse = numpy.linalg.inv(linear)
        triangles = {}
        for key, width in (("vertices", 3), ("loops", 3)):
            buffer = numpy.empty(count * width, dtype=numpy.int64)
            mesh.loop_triangles.foreach_get(key, buffer)
            triangles[key] = buffer.reshape(count, width)
        polygon = numpy.empty(count, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("polygon_index", polygon)
        triangles["polygon"] = polygon
        polygon_normals = numpy.empty(len(mesh.polygons) * 3)
        mesh.polygons.foreach_get("normal", polygon_normals)
        world_polygon_normals = unit_rows(polygon_normals.reshape(-1, 3) @ inverse)
        smooth = numpy.empty(len(mesh.polygons), dtype=bool)
        mesh.polygons.foreach_get("use_smooth", smooth)
        surface = Surface(
            world[triangles["vertices"]],
            polygon,
            world_polygon_normals[polygon],
            smooth[polygon],
            triangles["vertices"],
            triangles["loops"],
        )
        if attribute is not None:
            surface.attribute = attribute_corners(mesh, attribute, triangles)[surface.order]
        if group is not None:
            surface.weights = vertex_group_weights(obj, mesh, group)[surface.vertex_ids]
        return surface
    finally:
        bpy.data.meshes.remove(mesh)
