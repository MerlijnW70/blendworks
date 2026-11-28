"""The cavity of a container that liquid fills, as voxels and inner faces."""

import heapq
import math

import bmesh
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .errors import bad_args

UP = Vector((0.0, 0.0, 1.0))
NEIGHBOURS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
MAX_VOXELS = 2_000_000


def container_arrays(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        matrix = obj.matrix_world
        points = numpy.array([(matrix @ vertex.co)[:] for vertex in mesh.vertices], dtype=float)
        polygons = [tuple(polygon.vertices) for polygon in mesh.polygons]
        source = bmesh.new()
        source.from_mesh(mesh)
        closed = all(edge.is_manifold for edge in source.edges) and len(source.edges) > 0
        source.free()
    finally:
        evaluated.to_mesh_clear()
    triangles = []
    for polygon in polygons:
        for index in range(1, len(polygon) - 1):
            triangles.append((polygon[0], polygon[index], polygon[index + 1]))
    if not triangles:
        raise bad_args(f"{obj.name} has no faces")
    points, triangles = welded(points, numpy.array(triangles, dtype=int))
    return points, triangles, closed


def welded(points, triangles):
    """Merge coincident vertices (seams of lathes and sweeps) so the wall is one connected surface."""
    tolerance = max(float((points.max(axis=0) - points.min(axis=0)).max()) * 1e-6, 1e-9)
    keys = numpy.round(points / tolerance).astype(numpy.int64)
    _, first, inverse = numpy.unique(keys, axis=0, return_index=True, return_inverse=True)
    merged = inverse.reshape(-1)[triangles]
    keep = (merged[:, 0] != merged[:, 1]) & (merged[:, 1] != merged[:, 2]) & (merged[:, 0] != merged[:, 2])
    return points[first], merged[keep]


class Voxels:
    """The container on a voxel grid: solid where the wall is, and for each empty voxel the level at which water there spills out."""

    def __init__(self, points, triangles, closed, resolution):
        self.points = points
        self.triangles = triangles
        self.tree = BVHTree.FromPolygons([Vector(point) for point in points], [tuple(row) for row in triangles.tolist()])
        low, high = points.min(axis=0), points.max(axis=0)
        extent = float((high - low).max())
        self.size = extent / resolution
        self.low = low - 2.0 * self.size
        counts = numpy.ceil((high + 2.0 * self.size - self.low) / self.size).astype(int) + 1
        if int(numpy.prod(counts)) > MAX_VOXELS:
            raise bad_args("the container needs too many voxels; give a lower resolution")
        self.shape = (int(counts[0]), int(counts[1]), int(counts[2]))
        self.closed = closed
        self.solid = self.solidify()
        self.spill = self.spill_levels()

    def centre(self, i, j, k):
        return self.low + (numpy.array([i, j, k], dtype=float) + 0.5) * self.size

    def z_of(self, k):
        return self.low[2] + (k + 0.5) * self.size

    def solidify(self):
        nx, ny, nz = self.shape
        solid = numpy.zeros(self.shape, dtype=bool)
        reach = self.size * 0.75
        for i in range(nx):
            for j in range(ny):
                x, y = self.low[0] + (i + 0.5) * self.size, self.low[1] + (j + 0.5) * self.size
                crossings = self.column_crossings(x, y) if self.closed else []
                for k in range(nz):
                    z = self.low[2] + (k + 0.5) * self.size
                    if self.tree.find_nearest(Vector((x, y, z)), reach)[0] is not None:
                        solid[i, j, k] = True
                    elif crossings and sum(1 for value in crossings if value < z) % 2 == 1:
                        solid[i, j, k] = True
        return solid

    def column_crossings(self, x, y):
        found = []
        origin = Vector((x, y, self.low[2] - self.size))
        for _ in range(256):
            hit = self.tree.ray_cast(origin, UP)
            if hit[0] is None:
                break
            found.append(hit[0].z)
            origin = hit[0] + UP * 1e-7
        return found

    def spill_levels(self):
        """Minimax over paths to the edge of the grid of the highest voxel on the path (a priority flood through empty voxels)."""
        nx, ny, nz = self.shape
        spill = numpy.full(self.shape, math.inf)
        heap = []
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    if (i in (0, nx - 1) or j in (0, ny - 1) or k in (0, nz - 1)) and not self.solid[i, j, k]:
                        spill[i, j, k] = self.z_of(k)
                        heap.append((spill[i, j, k], i, j, k))
        heapq.heapify(heap)
        while heap:
            level, i, j, k = heapq.heappop(heap)
            if level > spill[i, j, k]:
                continue
            for di, dj, dk in NEIGHBOURS:
                a, b, c = i + di, j + dj, k + dk
                if 0 <= a < nx and 0 <= b < ny and 0 <= c < nz and not self.solid[a, b, c]:
                    candidate = max(level, self.z_of(c))
                    if candidate < spill[a, b, c]:
                        spill[a, b, c] = candidate
                        heapq.heappush(heap, (candidate, a, b, c))
        return spill

    def held(self):
        """Empty voxels that hold water: their spill level lies above them."""
        k = numpy.arange(self.shape[2])
        z = self.low[2] + (k + 0.5) * self.size
        return (~self.solid) & (self.spill > z[None, None, :] + 0.5 * self.size)

    def index(self, point):
        cell = numpy.floor((numpy.asarray(point) - self.low) / self.size).astype(int)
        if numpy.any(cell < 0) or numpy.any(cell >= numpy.array(self.shape)):
            return None
        return tuple(int(value) for value in cell)

    def rim(self):
        held = self.held()
        if not held.any():
            raise bad_args("the container holds no liquid: no enclosed space was found (is it open at the bottom, or are its walls thinner than a voxel?)")
        values = self.spill[held]
        finite = values[numpy.isfinite(values)]
        if len(finite):
            return float(finite.min())
        k = numpy.nonzero(held.any(axis=(0, 1)))[0]
        return self.z_of(int(k.max())) + 0.5 * self.size


def inner_faces(voxels, points, triangles):
    """Faces of the container that bound its held space, each oriented with its normal into that space."""
    held = voxels.held()
    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    normals = numpy.cross(b - a, c - a)
    lengths = numpy.linalg.norm(normals, axis=1)
    usable = lengths > 1e-20
    normals[usable] /= lengths[usable][:, None]
    centres = (a + b + c) / 3.0
    chosen, flips = [], []

    def first_free(start, direction):
        for step in range(1, 41):
            cell = voxels.index(start + direction * voxels.size * 0.5 * step)
            if cell is None:
                return step, False
            if not voxels.solid[cell]:
                return step, bool(held[cell])
        return 99, None

    if voxels.closed:
        outward = 1.0 if float(numpy.einsum("ij,ij->i", a, numpy.cross(b, c)).sum()) >= 0.0 else -1.0
        for row in numpy.nonzero(usable)[0].tolist():
            if first_free(centres[row], normals[row] * outward)[1]:
                chosen.append(row)
                flips.append(outward < 0.0)
        return oriented(triangles, chosen, flips)
    for row in numpy.nonzero(usable)[0].tolist():
        ahead, forward = first_free(centres[row], normals[row])
        behind, backward = first_free(centres[row], -normals[row])
        if ahead < behind:
            inner, flip = forward, False
        elif behind < ahead:
            inner, flip = backward, True
        else:
            inner, flip = forward != backward and forward is not None and backward is not None, bool(backward)
        if inner:
            chosen.append(row)
            flips.append(flip)
    return oriented(triangles, chosen, flips)


def oriented(triangles, chosen, flips):
    """The chosen faces, turned to face into the held space."""
    if not chosen:
        raise bad_args("no inner wall faces were found around the held space")
    faces = triangles[chosen].copy()
    flip = numpy.array(flips)
    faces[flip] = faces[flip][:, ::-1]
    return faces
