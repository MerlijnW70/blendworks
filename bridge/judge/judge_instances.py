import math
import re

import numpy as np
from mathutils import Matrix

SCALE_TOLERANCE = 0.01
YAW_TOLERANCE_DEGREES = 5.0
SHAPE_TOLERANCE = 1e-3
AXIS_GAP = 1e-2
WELD_DISTANCE = 1e-6
MAX_PIECES = 200000
SIZE_DIGITS = 7
DIGITS = 4


def name_pattern(text):
    pattern = text or "*"
    expression = "".join(".*" if char == "*" else "." if char == "?" else re.escape(char) for char in pattern)
    return pattern, re.compile(f"^{expression}$", re.DOTALL)


def vertex_labels(corners, vertex_count):
    labels = np.arange(vertex_count, dtype=np.int64)
    first = np.concatenate([corners[:, 0], corners[:, 1]])
    second = np.concatenate([corners[:, 1], corners[:, 2]])
    while True:
        lowest = np.minimum(labels[first], labels[second])
        merged = labels.copy()
        np.minimum.at(merged, first, lowest)
        np.minimum.at(merged, second, lowest)
        while True:
            jumped = merged[merged]
            if np.array_equal(jumped, merged):
                break
            merged = jumped
        if np.array_equal(merged, labels):
            return labels
        labels = merged


def welded(points):
    keys = np.round(points / WELD_DISTANCE).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first, kind="stable")
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order))
    return first[order], rank[inverse.reshape(-1)]


def mesh_parts(local, corners):
    representatives, mapping = welded(local)
    corners = mapping[corners]
    labels = vertex_labels(corners, len(representatives))
    used = np.unique(corners)
    triangle_labels = labels[corners[:, 0]]
    triangle_order = np.argsort(triangle_labels, kind="stable")
    sorted_labels = triangle_labels[triangle_order]
    used_labels = labels[used]
    vertex_order = np.argsort(used_labels, kind="stable")
    parts = []
    for label in np.unique(used_labels).tolist():
        vertices = used[vertex_order[np.searchsorted(used_labels[vertex_order], label, "left") : np.searchsorted(used_labels[vertex_order], label, "right")]]
        triangles = np.searchsorted(sorted_labels, label, "right") - np.searchsorted(sorted_labels, label, "left")
        parts.append((representatives[vertices], (len(vertices), int(triangles))))
    return parts


PROPER_SIGNS = (np.array([1.0, 1.0, 1.0]), np.array([1.0, -1.0, -1.0]), np.array([-1.0, 1.0, -1.0]), np.array([-1.0, -1.0, 1.0]))


def yaw_degrees(rotation):
    quaternion = Matrix(rotation.tolist()).to_quaternion()
    angle = math.degrees(2.0 * math.atan2(quaternion.z, quaternion.w))
    return (angle + 180.0) % 360.0 - 180.0


class Frame:
    def __init__(self, points):
        centred = points - points.mean(axis=0)
        self.size = float(np.sqrt((centred * centred).sum(axis=1).mean()))
        unit = centred / max(self.size, 1e-12)
        spread, axes = np.linalg.eigh(unit.T @ unit / len(unit))
        if np.linalg.det(axes) < 0:
            axes[:, 0] = -axes[:, 0]
        self.axes = axes
        self.distinct = bool(min(spread[1] - spread[0], spread[2] - spread[1]) >= AXIS_GAP * max(spread[2], 1e-12))
        self.radii = np.sort(np.linalg.norm(unit, axis=1))
        self.canonical = unit @ axes
        self.sorted = None if not self.distinct else [np.sort(self.canonical[:, axis]) for axis in range(3)]

    def rotations_to(self, other):
        if not (self.distinct and other.distinct):
            return [np.eye(3)]
        found = []
        for signs in PROPER_SIGNS:
            if all(np.abs(np.sort(other.canonical[:, axis] * signs[axis]) - self.sorted[axis]).max() <= SHAPE_TOLERANCE for axis in range(3)):
                found.append(other.axes @ np.diag(signs) @ self.axes.T)
        return found


class Shapes:
    def __init__(self):
        self.references = {}
        self.labels = []

    def match(self, key, points, label):
        frame = Frame(points)
        for mesh, reference in self.references.get(key, []):
            if np.abs(reference.radii - frame.radii).max() > SHAPE_TOLERANCE:
                continue
            rotations = reference.rotations_to(frame)
            if rotations:
                yaw = min((yaw_degrees(rotation) for rotation in rotations), key=abs)
                return mesh, frame.size / reference.size, yaw
        mesh = len(self.labels)
        self.labels.append(label)
        self.references.setdefault(key, []).append((mesh, frame))
        return mesh, 1.0, 0.0


def sphere_diameter(points):
    centre = (points.min(axis=0) + points.max(axis=0)) / 2.0
    return 2.0 * float(np.sqrt(((points - centre) ** 2).sum(axis=1).max()))


class PieceCollector:
    def __init__(self, instances_pattern, sizes_pattern):
        self.instances = None if instances_pattern is None else name_pattern(instances_pattern)
        self.sizes = None if sizes_pattern is None else name_pattern(sizes_pattern)
        self.parts = {}
        self.shapes = Shapes()
        self.records = []
        self.diameters = []
        self.overflow = False

    def add(self, owner, local, world, corners, data_key):
        counted = self.instances is not None and self.instances[1].match(owner)
        sized = self.sizes is not None and self.sizes[1].match(owner)
        if not counted and not sized:
            return
        if data_key not in self.parts:
            self.parts[data_key] = mesh_parts(local, corners)
        for vertices, key in self.parts[data_key]:
            if len(self.records) + len(self.diameters) >= 2 * MAX_PIECES:
                self.overflow = True
                return
            points = world[vertices]
            if counted:
                mesh, scale, yaw = self.shapes.match(key, points, owner)
                self.records.append((mesh, scale, yaw))
            if sized:
                self.diameters.append(sphere_diameter(points))

    def repetition(self):
        result = {"objects": self.instances[0], "scaleTolerance": SCALE_TOLERANCE, "yawToleranceDegrees": YAW_TOLERANCE_DEGREES, "pieces": len(self.records), "meshes": len(self.shapes.labels)}
        if self.overflow:
            return {**result, "share": None, "largestGroup": 0, "group": None, "failure": f"more than {MAX_PIECES} pieces"}
        if not self.records:
            return {**result, "share": None, "largestGroup": 0, "group": None, "failure": "no placed piece matches the objects pattern"}
        largest, group = largest_group(self.records)
        mesh, scale, yaw = group
        return {
            **result,
            "share": round(largest / len(self.records), DIGITS),
            "largestGroup": largest,
            "group": {"mesh": self.shapes.labels[mesh][:120], "scale": round(scale, DIGITS), "yaw": round(yaw, 2)},
            "failure": None,
        }

    def sphere_sizes(self):
        if self.overflow:
            return {"by": "sphere", "objects": self.sizes[0], "sizes": [], "unmeasured": 0, "failure": f"more than {MAX_PIECES} pieces"}
        return {"by": "sphere", "objects": self.sizes[0], "sizes": [float(f"{value:.{SIZE_DIGITS}g}") for value in self.diameters], "unmeasured": 0, "failure": None}


def largest_group(records):
    best = (0, records[0])
    meshes = np.array([record[0] for record in records])
    scales = np.array([record[1] for record in records])
    yaws = np.array([record[2] for record in records])
    for mesh in np.unique(meshes).tolist():
        members = np.flatnonzero(meshes == mesh)
        order = members[np.argsort(scales[members], kind="stable")]
        ordered = scales[order]
        for position, index in enumerate(order.tolist()):
            low = np.searchsorted(ordered, scales[index] * (1.0 - SCALE_TOLERANCE), "left")
            high = np.searchsorted(ordered, scales[index] * (1.0 + SCALE_TOLERANCE), "right")
            window = order[low:high]
            turn = np.abs((yaws[window] - yaws[index] + 180.0) % 360.0 - 180.0)
            count = int((turn <= YAW_TOLERANCE_DEGREES + 1e-9).sum())
            if count > best[0]:
                best = (count, records[index])
    return best
