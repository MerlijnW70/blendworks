import bmesh
import numpy

from .noise_stack import stack_field

MAX_VOLUME_LOSS = 0.10
STEP = 0.6
EDGE_DIVISOR = 32
MAX_REFINED_VERTICES = 400_000
REFINE_ROUNDS = 12
WEAR_SPREAD = 0.5
WEAR_OCTAVES = 2
CURVATURE_PERCENTILE = 99.0
IDLE_MOVE = 1e-9
CONVEXITY_EVERY = 3


def mesh_triangles(mesh):
    mesh.calc_loop_triangles()
    count = len(mesh.vertices)
    flat = numpy.empty(count * 3)
    mesh.vertices.foreach_get("co", flat)
    triangles = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", triangles)
    loops = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("loops", loops)
    owners = numpy.empty(len(mesh.loop_triangles), dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("polygon_index", owners)
    layer = mesh.uv_layers.active
    uvs = None
    if layer is not None:
        pairs = numpy.empty(len(mesh.loops) * 2)
        layer.uv.foreach_get("vector", pairs)
        uvs = pairs.reshape(-1, 2)[loops].reshape(-1, 3, 2)
    materials = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("material_index", materials)
    smooth = numpy.empty(len(mesh.polygons), dtype=bool)
    mesh.polygons.foreach_get("use_smooth", smooth)
    return flat.reshape(count, 3), triangles.reshape(-1, 3), uvs, materials[owners], smooth[owners]


def edge_table(triangles):
    pairs = numpy.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    return numpy.unique(numpy.sort(pairs, axis=1), axis=0)


def refine(points, triangles, uvs, materials, smooth, target):
    points = [point for point in points]
    faces = [tuple(face) for face in triangles]
    corner_uvs = [tuple(map(tuple, uv)) for uv in uvs] if uvs is not None else [None] * len(faces)
    materials, smooth = list(materials), list(smooth)
    for _ in range(REFINE_ROUNDS):
        cloud = numpy.array(points)
        table = edge_table(numpy.array(faces))
        long = table[numpy.linalg.norm(cloud[table[:, 0]] - cloud[table[:, 1]], axis=1) > target]
        if len(long) == 0 or len(points) + len(long) > MAX_REFINED_VERTICES:
            break
        middles = {}
        for a, b in long.tolist():
            middles[(a, b)] = len(points)
            points.append((points[a] + points[b]) / 2.0)
        faces, corner_uvs, materials, smooth = split_faces(faces, corner_uvs, materials, smooth, middles, points)
    return numpy.array(points), numpy.array(faces), corner_uvs, materials, smooth


def split_faces(faces, corner_uvs, materials, smooth, middles, points):
    out_faces, out_uvs, out_materials, out_smooth = [], [], [], []
    for face, uv, material, flag in zip(faces, corner_uvs, materials, smooth):
        marked = [middles.get((min(face[i], face[(i + 1) % 3]), max(face[i], face[(i + 1) % 3]))) for i in range(3)]
        count = sum(m is not None for m in marked)
        if count == 0:
            pieces = [(face, uv)]
        else:
            pieces = split_pattern(face, uv, marked, points)
        for ids, ids_uv in pieces:
            out_faces.append(ids)
            out_uvs.append(ids_uv)
            out_materials.append(material)
            out_smooth.append(flag)
    return out_faces, out_uvs, out_materials, out_smooth


def midpoint_uv(uv, i):
    if uv is None:
        return None
    first, second = uv[i], uv[(i + 1) % 3]
    return ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)


def split_pattern(face, uv, marked, points):
    count = sum(m is not None for m in marked)
    corner = {index: (face[index], uv[index] if uv is not None else None) for index in range(3)}
    if count == 3:
        m = [(marked[i], midpoint_uv(uv, i)) for i in range(3)]
        v = [corner[i] for i in range(3)]
        return [pattern(v[0], m[0], m[2]), pattern(m[0], v[1], m[1]), pattern(m[2], m[1], v[2]), pattern(m[0], m[1], m[2])]
    if count == 1:
        i = marked.index(next(m for m in marked if m is not None))
        a, b, c = corner[i], corner[(i + 1) % 3], corner[(i + 2) % 3]
        mid = (marked[i], midpoint_uv(uv, i))
        return [pattern(a, mid, c), pattern(mid, b, c)]
    free = marked.index(None)
    a, b, c = corner[(free + 1) % 3], corner[(free + 2) % 3], corner[free]
    first = (marked[(free + 1) % 3], midpoint_uv(uv, (free + 1) % 3))
    second = (marked[(free + 2) % 3], midpoint_uv(uv, (free + 2) % 3))
    pieces = [pattern(first, b, second)]
    short_first = numpy.linalg.norm(points[first[0]] - points[c[0]]) <= numpy.linalg.norm(points[a[0]] - points[second[0]])
    if short_first:
        pieces += [pattern(a, first, c), pattern(first, second, c)]
    else:
        pieces += [pattern(a, first, second), pattern(a, second, c)]
    return pieces


def pattern(*corners):
    ids = tuple(corner[0] for corner in corners)
    uvs = tuple(corner[1] for corner in corners)
    return ids, (uvs if uvs[0] is not None else None)


def volume_of(points, triangles):
    first, second, third = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    return float(numpy.einsum("ij,ij->i", first, numpy.cross(second, third)).sum() / 6.0)


def hull_volume(points):
    scratch = bmesh.new()
    try:
        for point in points:
            scratch.verts.new(point)
        hull = bmesh.ops.convex_hull(scratch, input=scratch.verts[:])
        volume = 0.0
        for face in hull["geom"]:
            if isinstance(face, bmesh.types.BMFace):
                corners = [vert.co for vert in face.verts]
                for k in range(1, len(corners) - 1):
                    volume += corners[0].dot(corners[k].cross(corners[k + 1])) / 6.0
        return volume
    finally:
        scratch.free()


def convexity_of(points, triangles):
    hull = hull_volume(points)
    return min(volume_of(points, triangles) / hull, 1.0) if hull > 0.0 else 1.0


def vertex_normals(points, triangles):
    corners = points[triangles]
    doubled = numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    face_normals = doubled / numpy.maximum(numpy.linalg.norm(doubled, axis=1), 1e-300)[:, None]
    normals = numpy.zeros_like(points)
    for corner in range(3):
        first = corners[:, (corner + 1) % 3] - corners[:, corner]
        second = corners[:, (corner + 2) % 3] - corners[:, corner]
        cosine = numpy.einsum("ij,ij->i", first, second) / numpy.maximum(numpy.linalg.norm(first, axis=1) * numpy.linalg.norm(second, axis=1), 1e-300)
        numpy.add.at(normals, triangles[:, corner], face_normals * numpy.arccos(numpy.clip(cosine, -1.0, 1.0))[:, None])
    length = numpy.linalg.norm(normals, axis=1)
    return normals / numpy.where(length > 0.0, length, 1.0)[:, None]


def wear_factor(points, seed, extent):
    params = {"seed": seed, "basis": "perlin", "scale": max(extent / 2.5, 1e-6), "octaves": WEAR_OCTAVES, "lacunarity": 2.0, "hurst": 0.7, "mode": "fbm", "ridge_offset": 1.0, "warp": 0.0, "warp_octaves": 1}
    return 1.0 + WEAR_SPREAD * stack_field(points, params)


def flow_step(points, triangles, edges, degree, modulation):
    normals = vertex_normals(points, triangles)
    total = numpy.zeros_like(points)
    numpy.add.at(total, edges[:, 0], points[edges[:, 1]])
    numpy.add.at(total, edges[:, 1], points[edges[:, 0]])
    pull = numpy.einsum("ij,ij->i", total / degree[:, None] - points, normals)
    size = numpy.abs(pull)
    reference = numpy.percentile(size, CURVATURE_PERCENTILE)
    if reference <= IDLE_MOVE:
        return points, 0.0
    moves = (STEP * numpy.minimum(size / reference, 1.0) * modulation * pull)[:, None] * normals
    return points + moves, float(numpy.abs(moves).max())


def abrade_points(points, triangles, edges, amount, target_convexity, iterations, seed, extent):
    degree = numpy.maximum(numpy.bincount(edges.ravel(), minlength=len(points)).astype(numpy.float64), 1.0)
    modulation = wear_factor(points, seed, extent)
    start = volume_of(points, triangles)
    current, loss, stopped, done = points, 0.0, "iterations", 0
    while done < iterations:
        proposed, biggest = flow_step(current, triangles, edges, degree, modulation)
        if biggest == 0.0:
            stopped = "settled"
            break
        after = 1.0 - volume_of(proposed, triangles) / start
        if after > MAX_VOLUME_LOSS:
            stopped = "volume_limit"
            break
        current, loss, done = proposed, after, done + 1
        if amount is not None and loss >= amount * MAX_VOLUME_LOSS:
            stopped = "amount"
            break
        if target_convexity is not None and done % CONVEXITY_EVERY == 0 and convexity_of(current, triangles) >= target_convexity:
            stopped = "convexity"
            break
    return current, done, loss, stopped
