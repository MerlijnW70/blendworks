import numpy

from .cover_shading import darken_ground
from .errors import BAD_ARGS, BridgeError

SMOOTHING_PASSES = 2


def triangle_coverage(surface, placed_list):
    covered = numpy.zeros(len(surface.areas))
    for placed in placed_list:
        if len(placed):
            numpy.add.at(covered, placed.triangle, placed.footprint)
    areas = numpy.maximum(surface.areas, 1e-12)
    return 1.0 - numpy.exp(-covered / areas)


def vertex_values(surface, values, vertex_count):
    totals = numpy.zeros(vertex_count)
    weights = numpy.zeros(vertex_count)
    for corner in range(3):
        numpy.add.at(totals, surface.vertex_ids[:, corner], values * surface.areas)
        numpy.add.at(weights, surface.vertex_ids[:, corner], surface.areas)
    return numpy.divide(totals, weights, out=numpy.zeros(vertex_count), where=weights > 0)


def smoothed(surface, values, vertex_count):
    for _ in range(SMOOTHING_PASSES):
        per_triangle = values[surface.vertex_ids].mean(axis=1)
        values = 0.5 * values + 0.5 * vertex_values(surface, per_triangle, vertex_count)
    return values


def write_contact(target, surface, placed_list, attribute_name, evaluated_count):
    mesh = target.data
    count = len(mesh.vertices)
    if evaluated_count != count:
        return None
    values = smoothed(surface, vertex_values(surface, triangle_coverage(surface, placed_list), count), count)
    existing = mesh.attributes.get(attribute_name)
    if existing is not None and (existing.domain != "POINT" or existing.data_type != "FLOAT"):
        mesh.attributes.remove(existing)
        existing = None
    attribute = existing if existing is not None else mesh.attributes.new(attribute_name, "FLOAT", "POINT")
    attribute.data.foreach_set("value", values.astype(numpy.float32))
    mesh.update()
    return values


def contact_shading(target, attribute_name, strength):
    changed, skipped = [], []
    for slot in target.material_slots:
        material = slot.material
        if material is None or material.node_tree is None or material.name in changed:
            continue
        try:
            darken_ground(material, attribute_name, strength)
        except BridgeError as error:
            if error.code != BAD_ARGS:
                raise
            skipped.append(material.name)
            continue
        changed.append(material.name)
    return changed, skipped
