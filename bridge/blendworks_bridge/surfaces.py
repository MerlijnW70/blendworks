import bisect
import math

import bmesh
from mathutils import Vector

from .analytic_paths import angle_step, plane_basis
from .errors import bad_args
from .paths import clean_path, object_curve, segment_lengths
from .selection import select_faces

PLANAR_DEGREES = 2.0
MIN_EDGE = 1e-5
SURFACES = ("plane", "faces", "cylinder", "ring", "curve")
MIN_MITRE = 0.25


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

    def point(self, x, y):
        return self.origin + self.across * x + self.up * y, self.normal

    def folds(self, low, high, tolerance, reach):
        return ListFolds([])


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

    def folds(self, low, high, tolerance, reach):
        return even_folds(low, high, self.radius * angle_step(self.radius, min(tolerance, self.radius)))

    def x_of_angle(self, degrees):
        return self.sign * (math.radians(degrees) - self.start) * self.radius

    def point(self, x, y):
        angle = self.start + self.sign * x / self.radius
        radial = self.first * math.cos(angle) + self.second * math.sin(angle)
        return self.centre + self.axis * y + radial * self.radius, radial * self.sign


class RingSurface:
    kind = "ring"

    def __init__(self, spec):
        self.axis = Vector(spec["axis"])
        if self.axis.length == 0:
            raise bad_args("axis must not be zero")
        self.axis.normalize()
        self.first, self.second = plane_basis(self.axis, spec.get("reference"))
        self.centre = Vector(spec["centre"])
        self.radius = spec["radius"]
        self.sign = 1.0 if spec["up"] == "outward" else -1.0
        self.start = math.radians(spec["angle"])

    def folds(self, low, high, tolerance, reach):
        outer = self.radius + reach
        return even_folds(low, high, self.radius * angle_step(outer, min(tolerance, outer)))

    def x_of_angle(self, degrees):
        return self.sign * (self.start - math.radians(degrees)) * self.radius

    def point(self, x, y):
        angle = self.start - self.sign * x / self.radius
        distance = self.radius + self.sign * y
        if distance <= 0:
            raise bad_args("the text reaches the centre of the ring; make it smaller or use a larger radius")
        radial = self.first * math.cos(angle) + self.second * math.sin(angle)
        return self.centre + radial * distance, self.axis.copy()


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
        normals = [(self.hint - direction * self.hint.dot(direction)).normalized() for direction in self.directions]
        acrosses = [normal.cross(direction) for normal, direction in zip(normals, self.directions)]
        self.mitres, self.normals = [], []
        for index in range(len(points)):
            before, after = self.joining(index, len(self.directions))
            mitre = acrosses[before] + acrosses[after]
            self.mitres.append(mitre / max(1.0 + acrosses[before].dot(acrosses[after]), MIN_MITRE))
            self.normals.append((normals[before] + normals[after]).normalized())

    def joining(self, index, count):
        if self.closed:
            return (index - 1) % count, index % count
        return max(index - 1, 0), min(index, count - 1)

    def folds(self, low, high, tolerance, reach):
        if self.closed:
            return LapFolds(self.starts[:-1], self.total, low, high)
        return ListFolds([start for start in self.starts[1:-1] if low < start < high])

    def point(self, x, y):
        if self.closed:
            x %= self.total
        elif x < -1e-9 or x > self.total + 1e-9:
            raise bad_args(f"the text runs {abs(x if x < 0 else x - self.total):.4f} m past the end of the path; shorten it, make it smaller or move the offset")
        index = min(max(bisect.bisect_right(self.starts, x) - 1, 0), len(self.directions) - 1)
        following = (index + 1) % len(self.points)
        share = (x - self.starts[index]) / (self.starts[index + 1] - self.starts[index])
        start = self.points[index] + self.mitres[index] * y
        end = self.points[following] + self.mitres[following] * y
        normal = self.normals[index].lerp(self.normals[following], share).normalized()
        return start.lerp(end, share), normal


class ListFolds:
    """Fold lines given as a short sorted list."""

    def __init__(self, values):
        self.list = sorted(values)

    def count(self, low=-math.inf, high=math.inf):
        return max(0, bisect.bisect_right(self.list, high) - bisect.bisect_left(self.list, low))

    def values(self):
        return self.list


class EvenFolds:
    """Fold lines at every multiple of step strictly between low and high, counted without listing them."""

    def __init__(self, low, high, step):
        self.step = step
        self.first, self.end = math.floor(low / step) + 1, math.ceil(high / step)

    def count(self, low=-math.inf, high=math.inf):
        first = self.first if low == -math.inf else max(self.first, math.floor(low / self.step))
        last = self.end - 1 if high == math.inf else min(self.end - 1, math.ceil(high / self.step))
        return max(0, last - first + 1)

    def values(self):
        return [index * self.step for index in range(self.first, self.end)]


class LapFolds:
    """Fold lines at the corners of a closed path, lap after lap, strictly between low and high."""

    def __init__(self, starts, total, low, high):
        self.starts, self.total, self.low, self.high = starts, total, low, high
        self.laps = range(math.floor(low / total), math.floor(high / total) + 1)

    def kept(self, lap):
        return sum(1 for start in self.starts if self.low < start + self.total * lap < self.high)

    def count(self, low=-math.inf, high=math.inf):
        if low == -math.inf and high == math.inf:
            first, last = self.laps[0], self.laps[-1]
            edge = {lap for lap in (first, first + 1, last - 1, last) if first <= lap <= last}
            return sum(self.kept(lap) for lap in edge) + len(self.starts) * (len(self.laps) - len(edge))
        low, high = max(low, self.low), min(high, self.high)
        if low > high:
            return 0
        margin = 1e-9 * (abs(low) + abs(high) + self.total)
        first, last = math.floor(low / self.total), math.floor(high / self.total)
        inside = [bisect.bisect_right(self.starts, high - self.total * lap + margin) - bisect.bisect_left(self.starts, low - self.total * lap - margin) for lap in {first, last}]
        return sum(inside) + len(self.starts) * max(0, last - first - 1)

    def values(self):
        return sorted(start + self.total * lap for lap in self.laps for start in self.starts if self.low < start + self.total * lap < self.high)


def even_folds(low, high, step):
    return EvenFolds(low, high, step)


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
    given = [kind for kind in SURFACES if kind in args]
    if len(given) != 1:
        raise bad_args("give the surface as exactly one of plane, faces, cylinder, ring or curve")
    kind = given[0]
    spec = args[kind]
    if kind == "plane":
        return PlaneSurface(spec["origin"], spec["normal"], spec.get("up"))
    if kind == "faces":
        selection = {key: value for key, value in spec.items() if key != "up"}
        return FaceRegion(obj, selection, spec.get("up"))
    if kind == "cylinder":
        return CylinderSurface(spec)
    if kind == "ring":
        return RingSurface(spec)
    return curve_surface(spec)

