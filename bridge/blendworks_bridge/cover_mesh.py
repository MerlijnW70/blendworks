import math

import bpy
import numpy

WIND_LAYER = "wind"
BLADE_ATTRIBUTE = "gc_blade"
DRY_ATTRIBUTE = "gc_dry"
NEVER_DRY = 2.0
BASE_BAND = 0.002
FLAT_EXTENT = 0.001


class ElementMesh:
    def __init__(self):
        self.points = []
        self.wind = []
        self.blade = []
        self.dry = []
        self.faces = []
        self.uvs = []
        self.slots = []
        self.smooth = []

    def vertex(self, co, wind=(0.0, 0.0, 0.0, 0.0), blade=0.0, dry=NEVER_DRY):
        self.points.append((float(co[0]), float(co[1]), float(co[2])))
        self.wind.append(tuple(float(value) for value in wind))
        self.blade.append(float(blade))
        self.dry.append(float(dry))
        return len(self.points) - 1

    def face(self, indices, uvs, slot=0, smooth=True):
        self.faces.append(tuple(indices))
        self.uvs.append([tuple(uv) for uv in uvs])
        self.slots.append(slot)
        self.smooth.append(smooth)

    def quad_strip(self, left, right, us, vs, slot=0):
        for index in range(len(left) - 1):
            a, b, c, d = left[index], right[index], right[index + 1], left[index + 1]
            if c == d:
                self.face((a, b, c), ((us[0], vs[index]), (us[1], vs[index]), (0.5 * (us[0] + us[1]), vs[index + 1])), slot)
            else:
                self.face((a, b, c, d), ((us[0], vs[index]), (us[1], vs[index]), (us[1], vs[index + 1]), (us[0], vs[index + 1])), slot)

    @property
    def triangles(self):
        return sum(len(face) - 2 for face in self.faces)

    def coordinates(self):
        return numpy.array(self.points, dtype=numpy.float64).reshape(-1, 3)

    def base_radius(self):
        points = self.coordinates()
        if not len(points):
            return 0.0
        lowest = points[:, 2].min()
        base = points[points[:, 2] <= lowest + BASE_BAND]
        return float(numpy.linalg.norm(base[:, :2], axis=1).max())

    def base_samples(self, most=8):
        points = self.coordinates()
        lowest = points[:, 2].min()
        base = points[points[:, 2] <= lowest + BASE_BAND]
        if len(base) <= most:
            return base
        angles = numpy.arctan2(base[:, 1], base[:, 0])
        buckets = numpy.floor((angles + math.pi) / (2.0 * math.pi) * most).astype(int).clip(0, most - 1)
        reach = numpy.linalg.norm(base[:, :2], axis=1)
        chosen = [numpy.flatnonzero(buckets == bucket)[numpy.argmax(reach[buckets == bucket])] for bucket in range(most) if numpy.any(buckets == bucket)]
        return base[chosen]

    def flat(self):
        points = self.coordinates()
        return bool(len(points)) and float(numpy.ptp(points[:, 2])) < FLAT_EXTENT

    def footprint(self):
        points = self.coordinates()
        if not len(points):
            return 0.0
        extent = numpy.ptp(points[:, :2], axis=0)
        return float(math.pi * 0.25 * extent[0] * extent[1])

    def summary(self):
        points = self.coordinates()
        low, high = points.min(axis=0), points.max(axis=0)
        return {
            "vertices": len(self.points),
            "faces": len(self.faces),
            "triangles": self.triangles,
            "size": [round(float(value), 6) for value in high - low],
            "base_radius": round(self.base_radius(), 6),
            "lowest": round(float(low[2]), 6),
        }

    def to_mesh(self, name, materials, wind):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.points, [], self.faces)
        mesh.validate(verbose=False)
        layer = mesh.uv_layers.new(name="UVMap")
        flat = [value for corners in self.uvs for uv in corners for value in uv]
        layer.uv.foreach_set("vector", flat)
        mesh.polygons.foreach_set("material_index", self.slots)
        mesh.polygons.foreach_set("use_smooth", self.smooth)
        for attribute_name, values in ((BLADE_ATTRIBUTE, self.blade), (DRY_ATTRIBUTE, self.dry)):
            attribute = mesh.attributes.new(attribute_name, "FLOAT", "POINT")
            attribute.data.foreach_set("value", values)
        if wind:
            colors = mesh.color_attributes.new(WIND_LAYER, "FLOAT_COLOR", "POINT")
            colors.data.foreach_set("color", [value for entry in self.wind for value in entry])
            mesh.color_attributes.active_color = colors
            mesh.color_attributes.render_color_index = mesh.color_attributes.active_color_index
        for material in materials:
            mesh.materials.append(material)
        mesh.update()
        return mesh


def rotate_about(vector, axis, angle):
    vector = numpy.asarray(vector, dtype=float)
    axis = numpy.asarray(axis, dtype=float)
    axis = axis / max(numpy.linalg.norm(axis), 1e-12)
    cosine, sine = math.cos(angle), math.sin(angle)
    return vector * cosine + numpy.cross(axis, vector) * sine + axis * numpy.dot(axis, vector) * (1.0 - cosine)


def unit(vector):
    vector = numpy.asarray(vector, dtype=float)
    length = numpy.linalg.norm(vector)
    return vector / length if length > 1e-12 else vector


def segments_for(budget, items, per_item, smallest=1, largest=12):
    best = None
    for segments in range(smallest, largest + 1):
        if items * per_item(segments) <= budget:
            best = segments
    return best
