"""Skeleton digest and radii measurement for tree assets."""

import hashlib
import math

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from judge_skeleton_checks import MIN_BRANCHINGS, SURFACE_TOLERANCE, EdgeSamples, branching_inside, branchings_needed, skeleton_problem
from judge_skeleton_read import FORMAT, PROPERTY, SkeletonError, parse_skeleton

RAYS = 32
MIN_RAYS = RAYS // 2
MAX_HITS = 64
MAX_BRANCHINGS = 512
NEAREST_SHARE = 1e-5
BREAST_HEIGHT = 1.3
SIZE_DIGITS = 7
MAX_LISTED = 64


def unit(vector):
    length = float(np.linalg.norm(vector))
    return None if length == 0.0 else vector / length


def plane_basis(tangent):
    helper = np.array([1.0, 0.0, 0.0]) if abs(tangent[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    first = unit(np.cross(tangent, helper))
    return first, np.cross(tangent, first)


def interquartile_mean(values):
    ordered = np.sort(np.array(values))
    quarter = len(ordered) // 4
    return float(ordered[quarter : len(ordered) - quarter].mean())


class NodeRadii:
    def __init__(self, skeleton, vertices, triangles):
        self.positions = skeleton["positions"]
        self.parents = skeleton["parents"]
        self.orders = skeleton["orders"]
        self.kinds = skeleton["kinds"]
        count = len(self.parents)
        self.children = [[] for _ in range(count)]
        for node in range(1, count):
            self.children[int(self.parents[node])].append(node)
        self.bvh = BVHTree.FromPolygons([tuple(point) for point in vertices.tolist()], triangles.tolist())
        self.extent = float(np.ptp(vertices, axis=0).max()) if len(vertices) else 0.0
        self.step = 1e-6 * max(self.extent, 1e-6)
        self.nearest = NEAREST_SHARE * self.extent
        self.samples = EdgeSamples(self.positions, self.parents, max(self.extent, 1e-9))
        self.problem = skeleton_problem(self.bvh, self.samples, self.positions, self.parents, vertices, triangles, self.extent)
        self.needed = branchings_needed(self.samples, self.extent)
        self.cache = {}

    def continuing(self, node):
        same = [child for child in self.children[node] if self.orders[child] == self.orders[node] and self.kinds[child] == self.kinds[node]]
        return min(same) if same else None

    def own_edges(self, node):
        edges = [node] if node > 0 else []
        following = self.continuing(node)
        return edges + ([following] if following is not None else [])

    def tangent(self, node):
        if node > 0:
            return unit(self.positions[node] - self.positions[self.parents[node]])
        following = self.continuing(node)
        if following is None:
            return np.array([0.0, 0.0, 1.0])
        return unit(self.positions[following] - self.positions[node])

    def ray_distance(self, origin, direction, own):
        start = Vector(origin.tolist())
        heading = Vector(direction.tolist())
        travelled = 0.0
        for _ in range(MAX_HITS):
            location, _, _, distance = self.bvh.ray_cast(start, heading, self.extent - travelled)
            if location is None:
                return None
            travelled += distance
            if travelled >= self.nearest and self.samples.nearest_edge(np.array(location))[0] in own:
                return travelled
            start = location + heading * self.step
            travelled += self.step
            if travelled >= self.extent:
                return None
        return None

    def measure(self, node):
        if node in self.cache:
            return self.cache[node]
        result = None
        tangent = self.tangent(node)
        own = set(self.own_edges(node))
        if tangent is not None and own:
            first, second = plane_basis(tangent)
            directions, distances = [], []
            for ray in range(RAYS):
                angle = 2.0 * math.pi * ray / RAYS
                direction = math.cos(angle) * first + math.sin(angle) * second
                distance = self.ray_distance(self.positions[node], direction, own)
                if distance is not None:
                    directions.append(direction)
                    distances.append(distance)
            if len(distances) >= MIN_RAYS:
                result = (interquartile_mean(distances), np.array(directions), np.array(distances))
        self.cache[node] = result
        return result

    def branchings(self):
        nodes = [node for node, below in enumerate(self.children) if len(below) >= 2]
        if len(nodes) <= MAX_BRANCHINGS:
            return nodes, len(nodes)
        picks = np.unique(np.round(np.linspace(0, len(nodes) - 1, MAX_BRANCHINGS)).astype(np.int64))
        return [nodes[pick] for pick in picks.tolist()], len(nodes)

    def trunk_node(self, matrix):
        heights = (self.positions @ np.array(matrix)[:3, :3].T)[:, 2]
        trunk = []
        node = self.continuing(0)
        while node is not None and self.kinds[node] == 0:
            trunk.append(node)
            node = self.continuing(node)
        if not trunk:
            return None
        rise = np.abs(heights[trunk] - heights[0] - BREAST_HEIGHT)
        return trunk[int(np.argmin(rise))]


def significant(value):
    return float(f"{value:.{SIZE_DIGITS}g}")


def world_radius(measured, linear):
    return interquartile_mean(measured[2] * np.linalg.norm(measured[1] @ linear.T, axis=1))


def skeleton_digest(skeleton):
    digest = hashlib.sha256()
    for key in ("positions", "parents", "orders", "kinds"):
        digest.update(np.ascontiguousarray(skeleton[key]).tobytes())
    return digest.hexdigest()


class SkeletonCollector:
    def __init__(self, leonardo, trunk_pattern):
        self.leonardo = leonardo
        self.trunk = trunk_pattern
        self.measurers = {}
        self.skeletons = []
        self.refused = []
        self.trunk_sizes = []
        self.trunk_unmeasured = 0

    def add(self, obj, owner, world_matrix, vertices, triangles, data_key):
        source = obj.original
        if PROPERTY not in source.keys():
            return
        try:
            skeleton = parse_skeleton(source[PROPERTY])
        except SkeletonError as error:
            self.refused.append(f"{owner[:120]}: {error}")
            return
        key = (data_key, skeleton_digest(skeleton))
        if key not in self.measurers:
            self.measurers[key] = NodeRadii(skeleton, vertices, triangles)
        radii = self.measurers[key]
        if radii.problem is not None:
            self.refused.append(f"{owner[:120]}: {radii.problem}")
            return
        if self.leonardo:
            self.add_branchings(owner, skeleton, radii)
        if self.trunk is not None and self.trunk[1].match(owner):
            node = radii.trunk_node(world_matrix)
            measured = None if node is None else radii.measure(node)
            if measured is None:
                self.trunk_unmeasured += 1
            else:
                self.trunk_sizes.append(significant(2.0 * world_radius(measured, np.array(world_matrix)[:3, :3])))

    def add_branchings(self, owner, skeleton, radii):
        nodes, total = radii.branchings()
        if total < radii.needed:
            self.refused.append(f"{owner[:120]}: the skeleton has {total} branchings, fewer than the {radii.needed} its length over the mesh's size needs")
            return
        measured = []
        unmeasured = 0
        for node in nodes:
            if not branching_inside(radii.bvh, radii.positions, radii.parents, node, radii.children[node], SURFACE_TOLERANCE * radii.extent):
                unmeasured += 1
                continue
            found = [radii.measure(node)] + [radii.measure(child) for child in radii.children[node]]
            if any(entry is None for entry in found):
                unmeasured += 1
                continue
            measured.append([significant(entry[0]) for entry in found])
        if len(measured) < MIN_BRANCHINGS:
            self.refused.append(f"{owner[:120]}: only {len(measured)} branchings lie inside the mesh and could be measured, fewer than {MIN_BRANCHINGS}")
            return
        self.skeletons.append({"object": owner[:120], "nodes": len(skeleton["parents"]), "exponent": skeleton["exponent"], "branchings": total, "sampled": len(nodes), "unmeasured": unmeasured, "radii": measured})

    def leonardo_result(self):
        failure = None
        if self.refused:
            failure = self.refused[0]
        elif not self.skeletons:
            failure = f"no object carries a {FORMAT} skeleton"
        return {"skeletons": self.skeletons[:MAX_LISTED], "refused": self.refused[:MAX_LISTED], "failure": failure}

    def trunk_sizes_result(self):
        failure = None if self.trunk_sizes or self.trunk_unmeasured else f"no object that matches the pattern carries a {FORMAT} skeleton"
        if self.refused:
            failure = self.refused[0]
        return {"by": "trunk", "objects": self.trunk[0], "sizes": self.trunk_sizes, "unmeasured": self.trunk_unmeasured, "failure": failure}
