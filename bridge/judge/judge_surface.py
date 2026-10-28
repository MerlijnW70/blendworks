from array import array
from math import sqrt

from mathutils.bvhtree import BVHTree

from judge_rays import fixed_directions, generator_for, stratified_sample

MAX_TESTED_TRIANGLES = 300_000
TRIANGLE_POINTS = ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6))
EPSILON_RATIO = 2.0**-21
MINIMUM_EPSILON = 1e-9
LAYER_RATIO = 1e-5
OWN_FACE_RETRIES = 8
ORDER_CELLS = 8
FIRST_STEP_DIVISOR = 16
STEP_GROWTH = 4


def triangle_area(a, b, c):
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    x = ab[1] * ac[2] - ab[2] * ac[1]
    y = ab[2] * ac[0] - ab[0] * ac[2]
    z = ab[0] * ac[1] - ab[1] * ac[0]
    return sqrt(x * x + y * y + z * z) / 2


def triangle_normal(a, b, c):
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    x = ab[1] * ac[2] - ab[2] * ac[1]
    y = ab[2] * ac[0] - ab[0] * ac[2]
    z = ab[0] * ac[1] - ab[1] * ac[0]
    length = sqrt(x * x + y * y + z * z)
    return (x / length, y / length, z / length)


def blend(corners, weights):
    a, b, c = corners
    first, second, third = weights
    return (a[0] * first + b[0] * second + c[0] * third, a[1] * first + b[1] * second + c[1] * third, a[2] * first + b[2] * second + c[2] * third)


def along(point, direction, distance):
    return (point[0] + direction[0] * distance, point[1] + direction[1] * distance, point[2] + direction[2] * distance)


def dot(first, second):
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


class Surface:
    def __init__(self, degenerate_area, weld_distance, seed=""):
        self.degenerate_area = degenerate_area
        self.weld_distance = weld_distance
        self.seed = seed
        self.vertices = []
        self.triangles = []
        self.triangle_faces = []
        self.triangle_areas = []
        self.faces = []
        self.keys = set()
        self.degenerate = 0
        self.duplicate = 0
        self.low = [float("inf")] * 3
        self.high = [float("-inf")] * 3
        self.magnitude = 0.0

    def add(self, mesh, world, triangle_areas, opaque_faces=None):
        offset = len(self.vertices)
        self.vertices.extend(world)
        loop_vertices = array("i", [0]) * len(mesh.loops)
        mesh.loops.foreach_get("vertex_index", loop_vertices)
        triangle_vertices = array("i", [0]) * (len(mesh.loop_triangles) * 3)
        mesh.loop_triangles.foreach_get("vertices", triangle_vertices)
        triangle_faces = array("i", [0]) * len(mesh.loop_triangles)
        mesh.loop_triangles.foreach_get("polygon_index", triangle_faces)
        starts = array("i", [0]) * len(mesh.polygons)
        mesh.polygons.foreach_get("loop_start", starts)
        totals = array("i", [0]) * len(mesh.polygons)
        mesh.polygons.foreach_get("loop_total", totals)
        by_face = {}
        for index, face in enumerate(triangle_faces):
            by_face.setdefault(face, []).append(index)
        for face_index, (start, total) in enumerate(zip(starts, totals)):
            corners = loop_vertices[start : start + total]
            owned = by_face.get(face_index, [])
            area = sum(triangle_areas[index] for index in owned)
            if area <= self.degenerate_area:
                self.degenerate += 1
                continue
            key = tuple(sorted(self.quantized(world[vertex]) for vertex in corners))
            if key in self.keys:
                self.duplicate += 1
            self.keys.add(key)
            kept = [index for index in owned if triangle_areas[index] > self.degenerate_area]
            self.faces.append({"count": len(kept), "area": area, "opaque": opaque_faces is None or bool(opaque_faces[face_index])})
            for index in kept:
                self.triangles.append(tuple(offset + vertex for vertex in triangle_vertices[index * 3 : index * 3 + 3]))
                self.triangle_faces.append(len(self.faces) - 1)
                self.triangle_areas.append(triangle_areas[index])
            self.include([world[vertex] for vertex in corners])

    def include(self, points):
        for point in points:
            for axis in range(3):
                value = point[axis]
                if value < self.low[axis]:
                    self.low[axis] = value
                if value > self.high[axis]:
                    self.high[axis] = value
                if abs(value) > self.magnitude:
                    self.magnitude = abs(value)

    def quantized(self, point):
        step = self.weld_distance
        return (round(point[0] / step), round(point[1] / step), round(point[2] / step))

    def corners(self, triangle):
        return [self.vertices[vertex] for vertex in self.triangles[triangle]]

    def epsilon(self):
        return max(MINIMUM_EPSILON, EPSILON_RATIO * self.magnitude)

    def layer_tolerance(self):
        extent = max(self.high[axis] - self.low[axis] for axis in range(3))
        return max(self.epsilon(), LAYER_RATIO * extent)

    def visibility(self):
        if not self.faces:
            return {"tested": 0, "sampled": False, "hiddenRatio": 0.0, "hiddenFaces": 0, "visibleTriangles": 0}
        generator = generator_for(self.seed)
        directions = fixed_directions()
        testable = [triangle for triangle, face in enumerate(self.triangle_faces) if self.faces[face]["opaque"]]
        centroids = [blend(self.corners(triangle), TRIANGLE_POINTS[0]) for triangle in testable]
        sample = stratified_sample(centroids, self.low, self.high, MAX_TESTED_TRIANGLES, generator)
        tree = BVHTree.FromPolygons(self.vertices, [self.triangles[triangle] for triangle in testable], all_triangles=True)
        caster = RayCaster(tree, [self.triangle_faces[triangle] for triangle in testable], directions, self.epsilon(), self.layer_tolerance())
        return self.estimate(testable, sample, len(sample) < len(testable), caster)

    def estimate(self, testable, sample, sampled, caster):
        total_area = 0.0
        hidden_area = 0.0
        hidden_faces = 0.0
        visible_triangles = 0.0
        tested_faces = set()
        seen_visible = set()
        for face_index, face in enumerate(self.faces):
            if not face["opaque"]:
                total_area += face["area"]
                hidden_area += face["area"]
                hidden_faces += 1
                tested_faces.add(face_index)
        for position, weight in sample:
            triangle = testable[position]
            face_index = self.triangle_faces[triangle]
            area = self.triangle_areas[triangle]
            tested_faces.add(face_index)
            total_area += weight * area
            if caster.visible(self.corners(triangle), face_index):
                visible_triangles += weight
                seen_visible.add(face_index)
                continue
            hidden_area += weight * area
            if sampled:
                hidden_faces += weight / self.faces[face_index]["count"]
        if not sampled:
            hidden_faces += sum(1 for face_index, face in enumerate(self.faces) if face["opaque"] and face_index not in seen_visible)
        return {
            "tested": len(tested_faces),
            "sampled": sampled,
            "hiddenRatio": hidden_area / total_area if total_area > 0 else 0.0,
            "hiddenFaces": round(hidden_faces),
            "visibleTriangles": round(visible_triangles),
        }


class RayCaster:
    def __init__(self, tree, faces, directions, epsilon, tolerance):
        self.tree = tree
        self.faces = faces
        self.directions = directions
        self.epsilon = epsilon
        self.tolerance = tolerance
        self.orders = {}

    def order(self, normal):
        key = (round(normal[0] * ORDER_CELLS), round(normal[1] * ORDER_CELLS), round(normal[2] * ORDER_CELLS))
        found = self.orders.get(key)
        if found is None:
            found = sorted(range(len(self.directions)), key=lambda index: (-dot(self.directions[index], key), index))
            self.orders[key] = found
        return found

    def own(self, hit, face):
        return hit[2] is not None and self.faces[hit[2]] == face

    def escapes(self, point, direction, side, face):
        offset = self.epsilon
        origin = along(point, side, offset)
        for _ in range(OWN_FACE_RETRIES):
            hit = self.tree.ray_cast(origin, direction)
            if hit[0] is None:
                return True
            if not self.own(hit, face):
                return False
            if hit[3] <= 4 * offset:
                offset *= 4
                origin = along(point, side, offset)
            else:
                origin = along(tuple(hit[0]), direction, self.epsilon)
        return False

    def layered(self, point, normal, face):
        origin = along(point, normal, -self.epsilon)
        remaining = self.tolerance + self.epsilon
        step = self.epsilon / FIRST_STEP_DIVISOR
        for _ in range(OWN_FACE_RETRIES):
            hit = self.tree.ray_cast(origin, normal, remaining)
            if hit[0] is None:
                return False
            if not self.own(hit, face):
                return True
            remaining -= hit[3] + step
            if remaining <= 0:
                return False
            origin = along(tuple(hit[0]), normal, step)
            step *= STEP_GROWTH
        return False

    def visible(self, corners, face):
        normal = triangle_normal(*corners)
        backward = (-normal[0], -normal[1], -normal[2])
        points = [blend(corners, weights) for weights in TRIANGLE_POINTS]
        layered = [None] * len(points)
        for index in self.order(normal):
            direction = self.directions[index]
            side = normal if dot(direction, normal) >= 0 else backward
            for position, point in enumerate(points):
                if layered[position] or not self.escapes(point, direction, side, face):
                    continue
                if layered[position] is None:
                    layered[position] = self.layered(point, normal, face)
                if not layered[position]:
                    return True
        return False
