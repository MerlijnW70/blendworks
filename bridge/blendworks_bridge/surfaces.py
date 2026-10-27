import bisect
import math

import bmesh
from mathutils import Vector

from .analytic_paths import plane_basis
from .errors import bad_args
from .paths import clean_path, object_curve, segment_lengths
from .selection import select_faces

PLANAR_DEGREES = 2.0
MIN_EDGE = 1e-5


def default_up(normal):
    return Vector((0.0, 1.0, 0.0)) if abs(normal.z) > 0.99 else Vector((0.0, 0.0, 1.0))


def plane_frame(normal, up):
    normal = Vector(normal)
    if normal.length == 0:
        raise bad_args("the plane normal must not be zero")
    normal.normalize()
    up = Vector(up) if up is not None else default_up(normal)
    up = up - normal * up.dot(normal)
    if up.length < 1e-9:
        raise bad_args("up must not be parallel to the surface normal")
    up.normalize()
    return normal, up.cross(normal), up


class PlaneSurface:
    kind = "plane"

    def __init__(self, origin, normal, up):
        self.origin = Vector(origin)
        self.normal, self.across, self.up = plane_frame(normal, up)

    def limit(self, tolerance):
        return math.inf

    def point(self, x, y):
        return self.origin + self.across * x + self.up * y, self.normal

    def distance(self, first, second):
        return math.inf


class FaceRegion(PlaneSurface):
    kind = "faces"

    def __init__(self, obj, selection, up):
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            bm.normal_update()
            faces = select_faces(bm, obj, selection)
            matrix = obj.matrix_world
            normal_matrix = matrix.to_3x3().inverted_safe().transposed()
            total, centre, corners = Vector(), Vector(), []
            weights = 0.0
            for face in faces:
                weight = face.calc_area()
                total += (normal_matrix @ face.normal).normalized() * weight
                centre += (matrix @ face.calc_center_median()) * weight
                weights += weight
                corners.extend(matrix @ vert.co for vert in face.verts)
            normals = [(normal_matrix @ face.normal).normalized() for face in faces]
        finally:
            bm.free()
        mean = total.normalized()
        limit = math.cos(math.radians(PLANAR_DEGREES))
        if any(normal.dot(mean) < limit for normal in normals):
            raise bad_args(f"the selected faces are not one flat region; they bend more than {PLANAR_DEGREES} degrees")
        super().__init__(centre / weights, mean, up)
        offsets = [((corner - self.origin).dot(self.across), (corner - self.origin).dot(self.up)) for corner in corners]
        self.region = (min(x for x, _ in offsets), min(y for _, y in offsets), max(x for x, _ in offsets), max(y for _, y in offsets))
        middle = Vector(((self.region[0] + self.region[2]) / 2.0, (self.region[1] + self.region[3]) / 2.0, 0.0))
        self.origin = self.origin + self.across * middle.x + self.up * middle.y
        self.region = (self.region[0] - middle.x, self.region[1] - middle.y, self.region[2] - middle.x, self.region[3] - middle.y)


class CylinderSurface:
    kind = "cylinder"

    def __init__(self, spec):
        self.axis = Vector(spec["axis"])
        if self.axis.length == 0:
            raise bad_args("axis must not be zero")
        self.axis.normalize()
        self.first, self.second = plane_basis(self.axis, spec.get("reference"))
        self.centre = Vector(spec["centre"])
        self.radius = spec["radius"]
        self.sign = 1.0 if spec["side"] == "outer" else -1.0
        self.start = math.radians(spec["angle"])

    def limit(self, tolerance):
        return math.sqrt(8.0 * self.radius * tolerance)

    def distance(self, first, second):
        return abs(second[0] - first[0])

    def point(self, x, y):
        angle = self.start + self.sign * x / self.radius
        radial = self.first * math.cos(angle) + self.second * math.sin(angle)
        return self.centre + self.axis * y + radial * self.radius, radial * self.sign


class PathSurface:
    kind = "curve"

    def __init__(self, points, closed, hint):
        self.points = points
        self.closed = closed
        lengths = segment_lengths(points, closed)
        self.directions = [(points[(index + 1) % len(points)] - points[index]) / lengths[index] for index in range(len(lengths))]
        self.starts = [0.0]
        for length in lengths:
            self.starts.append(self.starts[-1] + length)
        self.total = self.starts[-1]
        self.hint = Vector(hint)
        if self.hint.length == 0:
            raise bad_args("normal must not be zero")
        self.hint.normalize()
        for direction in self.directions:
            if abs(direction.dot(self.hint)) > 0.999:
                raise bad_args("normal must not run along the path")
        turns = [math.acos(max(-1.0, min(1.0, a.dot(b)))) for a, b in zip(self.directions, self.directions[1:] + ([self.directions[0]] if closed else []))]
        self.curvature = max((turn / max(lengths[index], MIN_EDGE) for index, turn in enumerate(turns)), default=0.0)

    def limit(self, tolerance):
        return math.inf if self.curvature < 1e-9 else math.sqrt(8.0 * tolerance / self.curvature)

    def distance(self, first, second):
        return math.hypot(second[0] - first[0], second[1] - first[1])

    def point(self, x, y):
        if self.closed:
            x %= self.total
        elif x < -1e-9 or x > self.total + 1e-9:
            raise bad_args(f"the text runs {abs(x if x < 0 else x - self.total):.4f} m past the end of the path; shorten it, make it smaller or move the offset")
        index = min(max(bisect.bisect_right(self.starts, x) - 1, 0), len(self.directions) - 1)
        direction = self.directions[index]
        position = self.points[index] + direction * (x - self.starts[index])
        normal = (self.hint - direction * self.hint.dot(direction)).normalized()
        return position + normal.cross(direction) * y, normal


def curve_surface(spec):
    if ("object" in spec) == ("waypoints" in spec):
        raise bad_args("give the curve as exactly one of object or waypoints")
    if "object" in spec:
        points, cyclic = object_curve(spec["object"])
        closed = spec.get("closed", cyclic)
        points = clean_path(points, closed, f"curve {spec['object']}")
    else:
        closed = spec.get("closed", False)
        points = clean_path(spec["waypoints"], closed)
    return PathSurface(points, closed, spec["normal"])


def build_surface(obj, args):
    given = [kind for kind in ("plane", "faces", "cylinder", "curve") if kind in args]
    if len(given) != 1:
        raise bad_args("give the surface as exactly one of plane, faces, cylinder or curve")
    kind = given[0]
    spec = args[kind]
    if kind == "plane":
        return PlaneSurface(spec["origin"], spec["normal"], spec.get("up"))
    if kind == "faces":
        selection = {key: value for key, value in spec.items() if key != "up"}
        return FaceRegion(obj, selection, spec.get("up"))
    if kind == "cylinder":
        return CylinderSurface(spec)
    return curve_surface(spec)

