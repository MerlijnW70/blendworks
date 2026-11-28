"""Convex solid data structure with box UVs, face splits and compaction."""

import math

import numpy

PLANE_TOLERANCE = 1e-7
SMALLEST_AREA = 1e-14


class Solid:
    def __init__(self, points, faces, uvs, materials):
        self.points = numpy.asarray(points, dtype=numpy.float64).reshape(-1, 3)
        self.faces = [list(face) for face in faces]
        self.uvs = [list(uv) for uv in uvs]
        self.materials = list(materials)

    def copy(self):
        return Solid(self.points.copy(), self.faces, self.uvs, self.materials)

    def used_points(self):
        used = sorted({index for face in self.faces for index in face})
        return self.points[used]

    def volume(self):
        total = 0.0
        for face in self.faces:
            corners = self.points[face]
            for k in range(1, len(face) - 1):
                total += float(numpy.dot(corners[0], numpy.cross(corners[k], corners[k + 1]))) / 6.0
        return total

    def centroid(self):
        return self.used_points().mean(axis=0)

    def face_normal(self, face):
        corners = self.points[face]
        shifted = numpy.roll(corners, -1, axis=0)
        normal = numpy.array(
            [
                numpy.sum((corners[:, 1] - shifted[:, 1]) * (corners[:, 2] + shifted[:, 2])),
                numpy.sum((corners[:, 2] - shifted[:, 2]) * (corners[:, 0] + shifted[:, 0])),
                numpy.sum((corners[:, 0] - shifted[:, 0]) * (corners[:, 1] + shifted[:, 1])),
            ]
        )
        length = float(numpy.linalg.norm(normal))
        return normal / length if length > 0.0 else normal

    def planes(self):
        return [(self.face_normal(face), self.points[face[0]]) for face in self.faces]

    def is_convex(self, tolerance):
        used = self.used_points()
        for normal, point in self.planes():
            if float(numpy.max((used - point) @ normal)) > tolerance:
                return False
        return True

    def edges(self):
        found = {}
        for number, face in enumerate(self.faces):
            for k, a in enumerate(face):
                b = face[(k + 1) % len(face)]
                found.setdefault((min(a, b), max(a, b)), []).append(number)
        return found

    def min_width(self):
        used = self.used_points()
        normals = numpy.array([self.face_normal(face) for face in self.faces])
        projected = used @ normals.T
        return float(numpy.min(projected.max(axis=0) - projected.min(axis=0)))


def box_uv(point, normal):
    axis = int(numpy.argmax(numpy.abs(normal)))
    keep = [index for index in range(3) if index != axis]
    flip = -1.0 if normal[axis] < 0.0 else 1.0
    return (float(point[keep[0]]) * flip, float(point[keep[1]]))


def split(solid, normal, offset, fresh_material, sides=(-1, 1)):
    distance = solid.points @ normal - offset
    side = numpy.where(distance > PLANE_TOLERANCE, 1, numpy.where(distance < -PLANE_TOLERANCE, -1, 0))
    if not (side > 0).any() or not (side < 0).any():
        return {}
    points = [point for point in solid.points]
    crossings = {}

    def crossing(a, b):
        low, high = (a, b) if a < b else (b, a)
        key = (low, high)
        if key not in crossings:
            t = distance[low] / (distance[low] - distance[high])
            points.append(solid.points[low] + (solid.points[high] - solid.points[low]) * t)
            crossings[key] = len(points) - 1
        return crossings[key]

    children = {}
    for sign in sides:
        faces, uvs, materials, on_plane = [], [], [], set()
        for face, face_uvs, material in zip(solid.faces, solid.uvs, solid.materials):
            kept, kept_uvs = [], []
            for k, a in enumerate(face):
                b = face[(k + 1) % len(face)]
                sa, sb = int(side[a]) * sign, int(side[b]) * sign
                if sa <= 0:
                    kept.append(a)
                    kept_uvs.append(face_uvs[k])
                if sa * sb < 0:
                    t = distance[a] / (distance[a] - distance[b])
                    ua, ub = face_uvs[k], face_uvs[(k + 1) % len(face)]
                    kept.append(crossing(a, b))
                    kept_uvs.append((ua[0] + (ub[0] - ua[0]) * t, ua[1] + (ub[1] - ua[1]) * t))
            if len(kept) < 3 or all(side[index] == 0 for index in kept if index < len(side)):
                continue
            faces.append(kept)
            uvs.append(kept_uvs)
            materials.append(material)
            on_plane.update(index for index in kept if index >= len(side) or side[index] == 0)
        cap = cap_face(points, on_plane, normal * sign)
        if cap is None:
            continue
        faces.append(cap)
        uvs.append([box_uv(points[index], normal * sign) for index in cap])
        materials.append(fresh_material)
        children[sign] = compact(points, faces, uvs, materials)
    return children


def cap_face(points, indices, outward):
    if len(indices) < 3:
        return None
    ordered = sorted(indices)
    cloud = numpy.array([points[index] for index in ordered])
    centre = cloud.mean(axis=0)
    helper = numpy.array([1.0, 0.0, 0.0]) if abs(outward[0]) < 0.9 else numpy.array([0.0, 1.0, 0.0])
    first = numpy.cross(outward, helper)
    first /= numpy.linalg.norm(first)
    second = numpy.cross(outward, first)
    angles = [math.atan2(float((p - centre) @ second), float((p - centre) @ first)) for p in cloud]
    cap = [ordered[k] for k in numpy.argsort(angles)]
    area = 0.0
    corners = numpy.array([points[index] for index in cap])
    for k in range(1, len(cap) - 1):
        area += float(numpy.linalg.norm(numpy.cross(corners[k] - corners[0], corners[k + 1] - corners[0]))) / 2.0
    return cap if area > SMALLEST_AREA else None


def compact(points, faces, uvs, materials):
    used = sorted({index for face in faces for index in face})
    renumber = {old: new for new, old in enumerate(used)}
    return Solid([points[index] for index in used], [[renumber[index] for index in face] for face in faces], uvs, materials)


def merged_counts(points, faces, degrees=1.0):
    points = numpy.asarray(points)
    normals = []
    for face in faces:
        corners = points[list(face)]
        normal = numpy.zeros(3)
        for k in range(1, len(corners) - 1):
            normal += numpy.cross(corners[k] - corners[0], corners[k + 1] - corners[0])
        length = float(numpy.linalg.norm(normal))
        normals.append(normal / length if length > 0.0 else normal)
    parent = list(range(len(faces)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owners = {}
    for number, face in enumerate(faces):
        for k, a in enumerate(face):
            b = face[(k + 1) % len(face)]
            owners.setdefault((min(a, b), max(a, b)), []).append(number)
    limit = math.cos(math.radians(degrees))
    for pair in owners.values():
        for other in pair[1:]:
            if float(normals[pair[0]] @ normals[other]) >= limit:
                parent[find(pair[0])] = find(other)
    regions = {}
    for number, face in enumerate(faces):
        for index in face:
            regions.setdefault(index, set()).add(find(number))
    face_count = len({find(number) for number in range(len(faces))})
    vertex_count = sum(1 for around in regions.values() if len(around) >= 3)
    return face_count, vertex_count
