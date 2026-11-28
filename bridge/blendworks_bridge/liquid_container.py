"""Container walls for liquid fills: tilt, wall offsets and boundary loops."""

import math

import numpy
from mathutils import Matrix, Vector
from mathutils.geometry import delaunay_2d_cdt

from .errors import bad_args
from .liquid_mesh import boundary_edges, mesh_volume

RINGS = (0.03, 0.1, 0.2, 0.35, 0.55, 0.8, 1.1, 1.5, 2.0, 2.7, 3.6)
GRID_SHARE = 1.0 / 28.0


def tilt_matrix(tilt):
    if not tilt or tilt.get("angle", 0.0) == 0.0:
        return Matrix.Identity(3)
    heading = math.radians(tilt.get("direction", 0.0))
    axis = Vector((math.cos(heading), -math.sin(heading), 0.0))
    return Matrix.Rotation(-math.radians(tilt["angle"]), 3, axis)


def vertex_offsets(points, faces, gap):
    """Offset of each vertex that keeps it at least gap from the plane of every face around it: angle-weighted normals, lengthened at corners."""
    a, b, c = points[faces[:, 0]], points[faces[:, 1]], points[faces[:, 2]]
    face_normals = numpy.cross(b - a, c - a)
    face_normals /= numpy.maximum(numpy.linalg.norm(face_normals, axis=1), 1e-30)[:, None]
    normals = numpy.zeros_like(points)
    corners = ((a, b, c), (b, c, a), (c, a, b))
    for column, (here, next_point, previous) in enumerate(corners):
        u, v = next_point - here, previous - here
        cosine = (u * v).sum(axis=1) / numpy.maximum(numpy.linalg.norm(u, axis=1) * numpy.linalg.norm(v, axis=1), 1e-30)
        numpy.add.at(normals, faces[:, column], face_normals * numpy.arccos(numpy.clip(cosine, -1.0, 1.0))[:, None])
    normals /= numpy.maximum(numpy.linalg.norm(normals, axis=1), 1e-30)[:, None]
    lowest = numpy.ones(len(points))
    for column in range(3):
        numpy.minimum.at(lowest, faces[:, column], (normals[faces[:, column]] * face_normals).sum(axis=1))
    return normals * (gap / numpy.clip(lowest, 0.35, 1.0))[:, None]


class Walls:
    """The inner wall of a container, offset into the cavity by the gap, in a frame whose z is the liquid surface's normal."""

    def __init__(self, points, faces, gap, rotation, pivot):
        used = numpy.unique(faces)
        remap = numpy.full(len(points), -1)
        remap[used] = numpy.arange(len(used))
        self.faces = remap[faces]
        moved = points[used] + vertex_offsets(points, faces, gap)[used]
        self.rotation = numpy.array(rotation)
        self.pivot = numpy.asarray(pivot, dtype=float)
        self.points = (moved - self.pivot) @ self.rotation.T
        self.bottom = float(self.points[:, 2].min())
        self.top = float(self.points[:, 2].max())
        edges = boundary_edges(self.faces)
        self.rim_low = float(self.points[edges.ravel(), 2].min()) if len(edges) else self.top

    def to_world(self, points):
        return points @ self.rotation + self.pivot


def clip(walls, height):
    """The walls below a plane, the new vertices on the plane shared by edge, and the cut segments."""
    points = [tuple(row) for row in walls.points.tolist()]
    below = walls.points[:, 2] <= height
    lookup = {}
    triangles, segments = [], []

    def cut(a, b):
        key = (min(a, b), max(a, b))
        index = lookup.get(key)
        if index is None:
            pa, pb = walls.points[a], walls.points[b]
            t = (height - pa[2]) / (pb[2] - pa[2])
            point = pa + t * (pb - pa)
            points.append((point[0], point[1], height))
            index = len(points) - 1
            lookup[key] = index
        return index

    for face in walls.faces.tolist():
        flags = [bool(below[index]) for index in face]
        count = sum(flags)
        if count == 3:
            triangles.append(tuple(face))
            continue
        if count == 0:
            continue
        polygon, crossing = [], []
        for position in range(3):
            current, following = face[position], face[(position + 1) % 3]
            if flags[position]:
                polygon.append(current)
            if flags[position] != flags[(position + 1) % 3]:
                index = cut(current, following)
                polygon.append(index)
                crossing.append(index)
        for position in range(1, len(polygon) - 1):
            triangles.append((polygon[0], polygon[position], polygon[position + 1]))
        if len(crossing) == 2:
            segments.append(tuple(crossing))
    return numpy.array(points, dtype=float), numpy.array(triangles, dtype=int).reshape(-1, 3), segments


def loops(segments):
    """Chain the cut segments into closed loops; open chains (a wall with a hole) are refused."""
    following = {}
    for a, b in segments:
        following.setdefault(a, []).append(b)
        following.setdefault(b, []).append(a)
    seen, result = set(), []
    for start in following:
        if start in seen:
            continue
        loop, previous, current = [start], None, start
        seen.add(start)
        while True:
            options = [node for node in following[current] if node != previous]
            if not options:
                raise bad_args("the inner wall is open at the liquid level, so it cannot hold liquid there")
            step = options[0]
            if step == start:
                break
            if step in seen:
                break
            loop.append(step)
            seen.add(step)
            previous, current = current, step
        if len(loop) >= 3:
            result.append(loop)
    if not result:
        raise bad_args("the liquid level does not cross the inner wall")
    return result


def signed_area(points2d):
    x, y = points2d[:, 0], points2d[:, 1]
    return 0.5 * float(numpy.dot(x, numpy.roll(y, -1)) - numpy.dot(y, numpy.roll(x, -1)))


def boundary_distance(queries, segments_a, segments_b):
    if len(queries) == 0:
        return numpy.zeros(0)
    ab = segments_b - segments_a
    length2 = numpy.maximum((ab * ab).sum(axis=1), 1e-30)
    best = numpy.full(len(queries), numpy.inf)
    for start in range(0, len(queries), 2048):
        chunk = queries[start:start + 2048]
        ap = chunk[:, None, :] - segments_a[None, :, :]
        t = numpy.clip((ap * ab[None]).sum(axis=2) / length2[None], 0.0, 1.0)
        nearest = segments_a[None] + t[..., None] * ab[None]
        best[start:start + 2048] = numpy.sqrt(((chunk[:, None, :] - nearest) ** 2).sum(axis=2)).min(axis=1)
    return best


def inside_polygon(queries, polygons):
    inside = numpy.zeros(len(queries), dtype=bool)
    for polygon in polygons:
        x0, y0 = polygon[:, 0], polygon[:, 1]
        x1, y1 = numpy.roll(x0, -1), numpy.roll(y0, -1)
        for qx, qy, row in zip(queries[:, 0], queries[:, 1], range(len(queries))):
            crosses = ((y0 > qy) != (y1 > qy)) & (qx < (x1 - x0) * (qy - y0) / numpy.where(y1 == y0, 1e-30, y1 - y0) + x0)
            if crosses.sum() % 2 == 1:
                inside[row] = not inside[row]
    return inside


def interior_points(polygons, capillary):
    a = numpy.concatenate([polygon for polygon in polygons])
    b = numpy.concatenate([numpy.roll(polygon, -1, axis=0) for polygon in polygons])
    low, high = a.min(axis=0), a.max(axis=0)
    extent = float((high - low).max())
    step = max(extent * GRID_SHARE, 1e-5)
    xs = numpy.arange(low[0] + step / 2, high[0], step)
    ys = numpy.arange(low[1] + step / 2, high[1], step)
    gx, gy = numpy.meshgrid(xs, ys)
    candidates = [numpy.column_stack([gx.ravel(), gy.ravel()])]
    for polygon in polygons:
        tangent = numpy.roll(polygon, -1, axis=0) - numpy.roll(polygon, 1, axis=0)
        inward = numpy.column_stack([-tangent[:, 1], tangent[:, 0]]) * (1.0 if signed_area(polygon) > 0 else -1.0)
        inward /= numpy.maximum(numpy.linalg.norm(inward, axis=1), 1e-30)[:, None]
        edge = numpy.linalg.norm(numpy.roll(polygon, -1, axis=0) - polygon, axis=1).mean()
        for share in RINGS:
            distance = share * capillary
            if distance > step * 1.5:
                break
            stride = max(int(distance / max(edge, 1e-12) * 0.7), 1)
            candidates.append(polygon[::stride] + inward[::stride] * distance)
    points = numpy.concatenate(candidates)
    inside = inside_polygon(points, polygons)
    points = points[inside]
    gaps = boundary_distance(points, a, b)
    return points[gaps > max(RINGS[0] * capillary * 0.5, step * 0.05)]


def cap(points, polygons_index, capillary, contact, meniscus):
    """Triangulate the surface inside the cut loops with extra points near the wall, raised into a meniscus that decays over the capillary length."""
    polygons = [points[loop][:, :2] for loop in polygons_index]
    inner = interior_points(polygons, capillary)
    boundary = [index for loop in polygons_index for index in loop]
    coords = [Vector(points[index][:2]) for index in boundary] + [Vector(point) for point in inner]
    faces, offset = [], 0
    for loop in polygons_index:
        indices = list(range(offset, offset + len(loop)))
        if signed_area(points[loop][:, :2]) < 0:
            indices.reverse()
        faces.append(indices)
        offset += len(loop)
    result = delaunay_2d_cdt(coords, [], faces, 3, 1e-12)
    out_coords, _, out_faces, origins = result[0], result[1], result[2], result[3]
    mapping, extra = [], []
    first = len(points)
    for index, (coord, origin) in enumerate(zip(out_coords, origins)):
        known = [value for value in origin if value < len(boundary)]
        if known:
            mapping.append(boundary[known[0]])
        else:
            mapping.append(first + len(extra))
            extra.append((coord.x, coord.y))
    extra = numpy.array(extra, dtype=float).reshape(-1, 2)
    a = numpy.concatenate([polygon for polygon in polygons])
    b = numpy.concatenate([numpy.roll(polygon, -1, axis=0) for polygon in polygons])
    distance = boundary_distance(extra, a, b)
    heights = contact - meniscus + meniscus * numpy.exp(-distance / capillary)
    new_points = numpy.column_stack([extra, heights]) if len(extra) else numpy.zeros((0, 3))
    triangles = []
    for face in out_faces:
        mapped = [mapping[index] for index in face]
        for position in range(1, len(mapped) - 1):
            triangles.append((mapped[0], mapped[position], mapped[position + 1]))
    return new_points, numpy.array(triangles, dtype=int).reshape(-1, 3)


def build(walls, level, capillary, meniscus):
    """Closed liquid at a flat level: the clipped walls turned to face out of the liquid and the cap with its meniscus."""
    contact = level + meniscus
    points, triangles, segments = clip(walls, contact)
    rings = loops(segments)
    extra, cap_triangles = cap(points, rings, capillary, contact, meniscus)
    all_points = numpy.concatenate([points, extra])
    wall = triangles[:, ::-1]
    faces = numpy.concatenate([wall, cap_triangles])
    top = numpy.concatenate([numpy.zeros(len(wall), dtype=bool), numpy.ones(len(cap_triangles), dtype=bool)])
    used = numpy.unique(faces)
    remap = numpy.full(len(all_points), -1)
    remap[used] = numpy.arange(len(used))
    all_points, faces = all_points[used], remap[faces]
    volume = mesh_volume(all_points, faces)
    if volume < 0.0:
        faces = faces[:, ::-1]
        volume = -volume
    return all_points, faces, top, volume


def solve_level(walls, target, capillary, meniscus, low, high):
    """Bisection on the flat level until the closed liquid holds the target volume."""
    best = None
    for _ in range(40):
        middle = 0.5 * (low + high)
        built = build(walls, middle, capillary, meniscus)
        best = (middle, built)
        if abs(built[3] - target) <= target * 1e-4:
            break
        if built[3] < target:
            low = middle
        else:
            high = middle
    return best
