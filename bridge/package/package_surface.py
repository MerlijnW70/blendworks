import numpy as np
from mathutils.bvhtree import BVHTree

SAMPLE_FLOOR = 2000
SAMPLE_CEILING = 50000
SAMPLES_PER_TRIANGLE = 2


def mesh_surface(mesh, matrix):
    mesh.calc_loop_triangles()
    count = len(mesh.vertices)
    coordinates = np.empty(count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coordinates)
    transform = np.array(matrix, dtype=np.float64)
    world = coordinates.reshape(-1, 3).astype(np.float64) @ transform[:3, :3].T + transform[:3, 3]
    corners = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("vertices", corners)
    return Surface(world, corners.reshape(-1, 3))


def triangle_soup(objects, depsgraph):
    parts = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            parts.append(mesh_surface(mesh, evaluated.matrix_world))
        finally:
            evaluated.to_mesh_clear()
    return Surface.join(parts)


class Surface:
    def __init__(self, vertices, triangles):
        self.vertices = vertices
        self.triangles = triangles
        self.cached_tree = None

    @staticmethod
    def join(parts):
        if not parts:
            return Surface(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
        offsets = np.cumsum([0] + [len(part.vertices) for part in parts[:-1]])
        return Surface(
            np.concatenate([part.vertices for part in parts]),
            np.concatenate([part.triangles + offset for part, offset in zip(parts, offsets)]),
        )

    def used_vertices(self):
        return self.vertices[np.unique(self.triangles)] if len(self.triangles) else self.vertices[:0]

    def bounds(self):
        points = self.used_vertices()
        return points.min(axis=0), points.max(axis=0)

    def diagonal(self):
        low, high = self.bounds()
        return float(np.linalg.norm(high - low))

    def corners(self, indices=None):
        chosen = self.triangles if indices is None else self.triangles[indices]
        return self.vertices[chosen]

    def areas(self):
        corners = self.corners()
        return 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)

    def tree(self):
        if self.cached_tree is None:
            self.cached_tree = BVHTree.FromPolygons(self.vertices.tolist(), self.triangles.tolist(), all_triangles=True)
        return self.cached_tree

    def sample_count(self, scale=1.0):
        return int(min(SAMPLE_CEILING, max(SAMPLE_FLOOR, SAMPLES_PER_TRIANGLE * len(self.triangles))) * scale)

    def sample(self, count, generator):
        areas = self.areas()
        total = areas.sum()
        if total <= 0 or count <= 0:
            return np.zeros((0, 3))
        chosen = generator.choice(len(areas), size=count, p=areas / total)
        corners = self.corners(chosen)
        first = np.sqrt(generator.random(count))
        second = generator.random(count)
        weights = np.stack([1.0 - first, first * (1.0 - second), first * second], axis=1)
        return np.einsum("ij,ijk->ik", weights, corners)


def nearest_distances(points, surface):
    tree = surface.tree()
    distances = np.empty(len(points), dtype=np.float64)
    for position, point in enumerate(points.tolist()):
        found = tree.find_nearest(point)
        distances[position] = np.inf if found[0] is None else found[3]
    return distances
