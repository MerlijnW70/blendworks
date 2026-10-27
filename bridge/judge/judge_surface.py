import random
from array import array
from math import cos, pi, sin, sqrt

from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree

SEED = 20261027
DIRECTIONS = 64
MAX_TESTED_FACES = 20_000
INNER_POINTS = ((0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6))
MAX_CENTROIDS = 4
OFFSET_RATIO = 1e-5
MINIMUM_OFFSET = 1e-6


def fibonacci_directions(count, generator):
    rotation = Euler((generator.uniform(0, 2 * pi), generator.uniform(0, 2 * pi), generator.uniform(0, 2 * pi))).to_matrix()
    golden = pi * (3.0 - sqrt(5.0))
    directions = []
    for index in range(count):
        z = 1.0 - 2.0 * (index + 0.5) / count
        radius = sqrt(max(0.0, 1.0 - z * z))
        angle = golden * index
        directions.append((rotation @ Vector((cos(angle) * radius, sin(angle) * radius, z))).normalized())
    return directions


def triangle_area(a, b, c):
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    x = ab[1] * ac[2] - ab[2] * ac[1]
    y = ab[2] * ac[0] - ab[0] * ac[2]
    z = ab[0] * ac[1] - ab[1] * ac[0]
    return sqrt(x * x + y * y + z * z) / 2


class Surface:
    def __init__(self, degenerate_area, weld_distance):
        self.degenerate_area = degenerate_area
        self.weld_distance = weld_distance
        self.vertices = []
        self.triangles = []
        self.faces = []
        self.keys = set()
        self.degenerate = 0
        self.duplicate = 0
        self.low = [float("inf")] * 3
        self.high = [float("-inf")] * 3

    def add(self, mesh, world, triangle_areas):
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
            triangles = [tuple(offset + vertex for vertex in triangle_vertices[index * 3 : index * 3 + 3]) for index in owned if triangle_areas[index] > self.degenerate_area]
            self.faces.append((len(self.triangles), len(triangles), area))
            self.triangles.extend(triangles)
            for vertex in corners:
                point = world[vertex]
                for axis in range(3):
                    if point[axis] < self.low[axis]:
                        self.low[axis] = point[axis]
                    if point[axis] > self.high[axis]:
                        self.high[axis] = point[axis]

    def quantized(self, point):
        step = self.weld_distance
        return (round(point[0] / step), round(point[1] / step), round(point[2] / step))

    def visibility(self):
        generator = random.Random(SEED)
        directions = fibonacci_directions(DIRECTIONS, generator)
        total_triangles = sum(count for _, count, _ in self.faces)
        if not self.faces:
            return {"tested": 0, "sampled": False, "hiddenRatio": 0.0, "hiddenFaces": 0, "visibleTriangles": 0}
        indices = list(range(len(self.faces)))
        sampled = len(indices) > MAX_TESTED_FACES
        if sampled:
            indices = sorted(generator.sample(indices, MAX_TESTED_FACES))
        tree = BVHTree.FromPolygons(self.vertices, self.triangles, all_triangles=True)
        diagonal = sqrt(sum((self.high[axis] - self.low[axis]) ** 2 for axis in range(3)))
        offset = max(MINIMUM_OFFSET, OFFSET_RATIO * diagonal)
        hidden_area = 0.0
        tested_area = 0.0
        hidden_faces = 0
        visible_triangles = 0
        tested_triangles = 0
        for index in indices:
            start, count, area = self.faces[index]
            tested_area += area
            tested_triangles += count
            if self.face_visible(tree, start, count, directions, offset):
                visible_triangles += count
            else:
                hidden_faces += 1
                hidden_area += area
        if sampled:
            visible_triangles = round(visible_triangles * total_triangles / tested_triangles) if tested_triangles else 0
            hidden_faces = round(hidden_faces * len(self.faces) / len(indices))
        return {
            "tested": len(indices),
            "sampled": sampled,
            "hiddenRatio": hidden_area / tested_area if tested_area else 0.0,
            "hiddenFaces": hidden_faces,
            "visibleTriangles": visible_triangles,
        }

    def face_visible(self, tree, start, count, directions, offset):
        corners = [[Vector(self.vertices[vertex]) for vertex in self.triangles[index]] for index in range(start, start + count)]
        largest = max(corners, key=lambda points: (points[1] - points[0]).cross(points[2] - points[0]).length)
        normal = (largest[1] - largest[0]).cross(largest[2] - largest[0]).normalized()
        points = [(points[0] + points[1] + points[2]) / 3 for points in corners[:MAX_CENTROIDS]]
        points += [largest[0] * first + largest[1] * second + largest[2] * third for first, second, third in INNER_POINTS]
        ordered = sorted(directions, key=lambda direction: -direction.dot(normal))
        for direction in ordered:
            step = direction * offset
            for point in points:
                if tree.ray_cast(point + step, direction)[0] is None:
                    return True
        return False
