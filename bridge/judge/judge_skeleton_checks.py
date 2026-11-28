"""Skeleton checks: edge samples and branching."""

import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

SAMPLE_SPACING = 0.01
MAX_SAMPLES = 400000
MAX_CHECKED = 4096
SURFACE_TOLERANCE = 0.002
INSIDE_SHARE = 0.5
INSIDE_RAYS = ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
INSIDE_EXITS = 4
COVER_EXTENT = 0.5
COVER_DISTANCE = 0.05
COVER_SHARE = 0.9
NEIGHBOURS = 8
MIN_BRANCHINGS = 5


class EdgeSamples:
    def __init__(self, positions, parents, extent):
        self.positions = positions
        self.parents = parents
        starts = positions[parents[1:]] if len(parents) > 1 else np.zeros((0, 3))
        ends = positions[1:]
        lengths = np.linalg.norm(ends - starts, axis=1)
        self.total_length = float(lengths.sum())
        spacing = max(SAMPLE_SPACING * extent, self.total_length / MAX_SAMPLES, 1e-9)
        counts = np.maximum(2, np.ceil(lengths / spacing).astype(np.int64) + 1)
        self.tree = KDTree(int(counts.sum()) if len(counts) else 1)
        for edge, (start, end, steps) in enumerate(zip(starts.tolist(), ends.tolist(), counts.tolist()), start=1):
            for share in np.linspace(0.0, 1.0, steps).tolist():
                self.tree.insert([start[axis] + (end[axis] - start[axis]) * share for axis in range(3)], edge)
        if not len(counts):
            self.tree.insert(positions[0].tolist(), 0)
        self.tree.balance()

    def segment_distances(self, point, edges):
        starts = self.positions[self.parents[edges]]
        axes = self.positions[edges] - starts
        lengths = (axes * axes).sum(axis=1)
        along = np.clip(((point - starts) * axes).sum(axis=1) / np.where(lengths > 0, lengths, 1.0), 0.0, 1.0)
        return np.linalg.norm(point - (starts + axes * along[:, None]), axis=1)

    def nearest_edge(self, point):
        edges = np.array(sorted({entry[1] for entry in self.tree.find_n(point.tolist(), NEIGHBOURS) if entry[1] > 0}), dtype=np.int64)
        if len(edges) == 0:
            return 0, float(np.linalg.norm(point - self.positions[0]))
        distances = self.segment_distances(point, edges)
        best = int(np.argmin(distances))
        return int(edges[best]), float(distances[best])


def evenly(count, cap=MAX_CHECKED):
    if count <= cap:
        return np.arange(count)
    return np.unique(np.round(np.linspace(0, count - 1, cap)).astype(np.int64))


def inside(bvh, point, tolerance):
    location, _, _, distance = bvh.find_nearest(Vector(point.tolist()))
    if location is not None and distance <= tolerance:
        return True
    exits = 0
    for direction in INSIDE_RAYS:
        _, normal, _, _ = bvh.ray_cast(Vector(point.tolist()), Vector(direction))
        if normal is not None and normal.dot(Vector(direction)) > 0:
            exits += 1
    return exits >= INSIDE_EXITS


def skeleton_problem(bvh, samples, positions, parents, vertices, triangles, extent):
    if extent <= 0:
        return "the object that carries the skeleton has no extent"
    span = float(np.ptp(positions, axis=0).max())
    if span < COVER_EXTENT * extent:
        return f"the skeleton spans {span:.4g} m, under {COVER_EXTENT:.0%} of the mesh's {extent:.4g} m"
    middles = (positions[1:] + positions[parents[1:]]) / 2.0
    points = np.concatenate([positions, middles])
    picked = points[evenly(len(points))]
    tolerance = SURFACE_TOLERANCE * extent
    share = float(np.mean([inside(bvh, point, tolerance) for point in picked]))
    if share < INSIDE_SHARE:
        return f"only {share:.1%} of the skeleton's nodes and edge midpoints lie inside the mesh, under {INSIDE_SHARE:.0%}"
    centres = vertices[triangles].mean(axis=1)[evenly(len(triangles))]
    near = float(np.mean([samples.nearest_edge(centre)[1] <= COVER_DISTANCE * extent for centre in centres]))
    if near < COVER_SHARE:
        return f"only {near:.1%} of the mesh surface lies within {COVER_DISTANCE:.0%} of its size of the skeleton, under {COVER_SHARE:.0%}"
    return None


def branching_inside(bvh, positions, parents, node, children, tolerance):
    points = [positions[node]] + [positions[child] for child in children] + [(positions[child] + positions[node]) / 2.0 for child in children]
    if node > 0:
        points.append((positions[node] + positions[parents[node]]) / 2.0)
    return all(inside(bvh, point, tolerance) for point in points)


def branchings_needed(samples, extent):
    return max(MIN_BRANCHINGS, int(np.ceil(samples.total_length / extent))) if extent > 0 else MIN_BRANCHINGS
