import numpy

EDGE_VERTS = ".edge_verts"
CORNER_EDGE = ".corner_edge"
LAYOUTS = {
    "BOOLEAN": ("value", numpy.bool_, 1),
    "INT8": ("value", numpy.int32, 1),
    "INT": ("value", numpy.int32, 1),
    "FLOAT": ("value", numpy.float32, 1),
    "INT16_2D": ("value", numpy.int32, 2),
    "INT32_2D": ("value", numpy.int32, 2),
    "FLOAT2": ("vector", numpy.float32, 2),
    "FLOAT_VECTOR": ("vector", numpy.float32, 3),
    "FLOAT_COLOR": ("color", numpy.float32, 4),
    "BYTE_COLOR": ("color", numpy.float32, 4),
    "QUATERNION": ("value", numpy.float32, 4),
    "FLOAT4X4": ("value", numpy.float32, 16),
}


def read(attribute, count):
    if attribute.data_type == "STRING":
        return [item.value for item in attribute.data]
    field, kind, width = LAYOUTS[attribute.data_type]
    values = numpy.empty(count * width, dtype=kind)
    attribute.data.foreach_get(field, values)
    return values.reshape(count, width) if width > 1 else values


def write(attribute, values):
    if attribute.data_type == "STRING":
        for item, value in zip(attribute.data, values):
            item.value = value
        return
    field = LAYOUTS[attribute.data_type][0]
    attribute.data.foreach_set(field, numpy.ascontiguousarray(values).ravel())


def edge_keys(mesh):
    count = len(mesh.edges)
    pairs = numpy.empty(count * 2, dtype=numpy.int64)
    mesh.edges.foreach_get("vertices", pairs)
    pairs = pairs.reshape(count, 2)
    return pairs.min(axis=1), pairs.max(axis=1)


def canonical_order(mesh):
    low, high = edge_keys(mesh)
    return numpy.lexsort((high, low))


def canonical_edges(mesh):
    """Blender's edge calculation hashes edges into one table per thread, so the edge order of a mesh it builds
    depends on the thread count; sort the edges by their lower then higher vertex index, carrying every edge
    attribute and remapping the corners, so the mesh is the same at any thread count. Returns whether it moved any."""
    count = len(mesh.edges)
    if count < 2:
        return False
    order = canonical_order(mesh)
    if numpy.array_equal(order, numpy.arange(count)):
        return False
    edge_attributes = [attribute for attribute in mesh.attributes if attribute.domain == "EDGE" and attribute.name != CORNER_EDGE]
    moved = {attribute.name: read(attribute, count) for attribute in edge_attributes}
    for attribute in edge_attributes:
        values = moved[attribute.name]
        write(attribute, [values[index] for index in order] if isinstance(values, list) else values[order])
    if len(mesh.loops):
        corners = numpy.empty(len(mesh.loops), dtype=numpy.int64)
        mesh.loops.foreach_get("edge_index", corners)
        position = numpy.empty(count, dtype=numpy.int64)
        position[order] = numpy.arange(count)
        mesh.loops.foreach_set("edge_index", position[corners].astype(numpy.int32))
    mesh.update()
    return True
