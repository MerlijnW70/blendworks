"""Twig sprays: style, frames and points."""

import math

import numpy

from .errors import bad_args
from .limits import MAX_MESH_VERTICES

LEAF_ROWS = (0.0, 0.45, 1.0)
FLAT_ROWS = (0.0, 1.0)
TWIG_SIDES = 3
TWIG_RINGS = (0.0, 0.5, 1.0)
TWIG_TIP_SHARE = 0.4
ARRANGEMENTS = ("alternate", "opposite", "terminal", "needles", "brush")
NEEDLE_START = 0.15
FORK_RADIUS = 0.7
FORK_SCALE = 0.95
NEEDLE_VERTICES = 3
NEEDLE_TIP_LIFT = 0.18
SHAPE_LENGTH = (0.85, 1.0, 1.25)
BRUSH_ROLL = math.pi / 3.0


class SprayStyle:
    def __init__(self, args):
        cluster = args["clusters"]
        self.arrangement = cluster["arrangement"]
        self.leaf_range = (int(cluster["leaves"][0]), int(max(cluster["leaves"])))
        self.twig_length = float(cluster["twig_length"])
        self.twig_radius = float(cluster["twig_radius"])
        self.twig_bend = float(cluster["twig_bend"])
        self.insertion = math.radians(cluster["leaf_angle"])
        self.size = float(args["size"])
        self.width = float(args["card"]["width"])
        self.petiole = float(cluster["petiole"])
        variation = args["variation"]
        self.size_variation = float(variation["size"])
        self.curl = math.radians(variation["curl"])
        self.fold = math.radians(args["card"]["fold"])
        self.fold_variation = math.radians(variation["fold"])
        self.tilt = math.radians(variation["tilt"])
        self.shapes = int(args["shapes"])
        self.low = args["detail"] == "low"
        self.needles = self.arrangement == "needles"
        self.brush = self.arrangement == "brush"
        self.flat = self.low or self.needles or self.brush
        self.shape_length = tuple(float(value) for value in args["shape_length"])
        self.forks = (int(cluster["forks"][0]), int(max(cluster["forks"])))
        self.fork_angle = math.radians(cluster["fork_angle"])
        self.fork_length = float(cluster["fork_length"])


def frame_of(direction, up):
    x_axis = direction / numpy.linalg.norm(direction)
    z_axis = up - x_axis * float(up @ x_axis)
    size = numpy.linalg.norm(z_axis)
    if size < 1e-9:
        z_axis = numpy.cross(x_axis, [0.0, 1.0, 0.0])
        size = numpy.linalg.norm(z_axis)
    z_axis = z_axis / size
    return x_axis, numpy.cross(z_axis, x_axis), z_axis


def turned(vector, axis, angle):
    axis = axis / numpy.linalg.norm(axis)
    return vector * math.cos(angle) + numpy.cross(axis, vector) * math.sin(angle) + axis * float(axis @ vector) * (1.0 - math.cos(angle))


def unit_rows(vectors):
    return vectors / numpy.maximum(numpy.linalg.norm(vectors, axis=-1, keepdims=True), 1e-12)


def twig_frames(bend, share):
    tangent = unit_rows(numpy.stack([numpy.ones_like(share), numpy.zeros_like(share), 2.0 * bend * share], axis=-1))
    normal = numpy.stack([-tangent[..., 2], numpy.zeros_like(share), tangent[..., 0]], axis=-1)
    side = numpy.zeros_like(tangent)
    side[..., 1] = 1.0
    return tangent, side, normal


def twig_points(bend, share, length):
    return numpy.stack([share * length, numpy.zeros_like(share), bend * length * share * share], axis=-1)


def orthonormal(x_axis, up):
    z_axis = unit_rows(up - x_axis * numpy.einsum("ij,ij->i", up, x_axis)[:, None])
    return numpy.stack([x_axis, numpy.cross(z_axis, x_axis), z_axis], axis=-1)


def rotate_about(vectors, axes, angles):
    cosine = numpy.cos(angles)[:, None]
    sine = numpy.sin(angles)[:, None]
    return vectors * cosine + numpy.cross(axes, vectors) * sine + axes * numpy.einsum("ij,ij->i", axes, vectors)[:, None] * (1.0 - cosine)


class Units:
    def __init__(self, spray, origin, rotation, length, radius, scale):
        self.spray = spray
        self.origin = origin
        self.rotation = rotation
        self.length = length
        self.radius = radius
        self.scale = scale


def make_units(style, rng, sprays):
    main_length = style.twig_length * rng.uniform(0.8, 1.2, sprays)
    forks = rng.integers(style.forks[0], style.forks[1] + 1, sprays)
    owner = numpy.repeat(numpy.arange(sprays), forks)
    count = len(owner)
    rank = numpy.arange(count) - numpy.repeat(numpy.cumsum(forks) - forks, forks)
    total = numpy.maximum(forks[owner], 1)
    share = 0.2 + 0.6 * (rank + 0.5 + rng.uniform(-0.3, 0.3, count)) / total
    tangent, side, normal = twig_frames(numpy.full(count, style.twig_bend), share)
    sign = numpy.where((rank + rng.integers(0, 2, count)) % 2 == 0, 1.0, -1.0)
    azimuth = sign * (0.5 * math.pi + rng.uniform(-0.5, 0.5, count))
    across = numpy.sin(azimuth)[:, None] * side + numpy.cos(azimuth)[:, None] * normal
    angle = style.fork_angle * rng.uniform(0.75, 1.2, count)
    direction = numpy.cos(angle)[:, None] * tangent + numpy.sin(angle)[:, None] * across
    fork_rotation = orthonormal(unit_rows(direction), normal)
    fork_origin = twig_points(numpy.full(count, style.twig_bend), share, main_length[owner])
    fork_length = main_length[owner] * style.fork_length * rng.uniform(0.7, 1.0, count) * (1.1 - 0.4 * share)
    identity = numpy.broadcast_to(numpy.identity(3), (sprays, 3, 3))
    return Units(
        numpy.concatenate([numpy.arange(sprays), owner]),
        numpy.concatenate([numpy.zeros((sprays, 3)), fork_origin]),
        numpy.concatenate([identity, fork_rotation]),
        numpy.concatenate([main_length, fork_length]),
        numpy.concatenate([numpy.full(sprays, style.twig_radius), numpy.full(count, style.twig_radius * FORK_RADIUS)]),
        numpy.concatenate([numpy.ones(sprays), numpy.full(count, FORK_SCALE)]),
    )


def leaf_layout(style, rng, counts):
    owner = numpy.repeat(numpy.arange(len(counts)), counts)
    total = len(owner)
    rank = numpy.arange(total) - numpy.repeat(numpy.cumsum(counts) - counts, counts)
    many = counts[owner]
    jitter = rng.uniform(-1.0, 1.0, (total, 3))
    size = 0.9 + 0.2 * rng.uniform(0.0, 1.0, total)
    planar = numpy.ones(total, dtype=bool)
    if style.arrangement == "needles":
        share = NEEDLE_START + (1.0 - NEEDLE_START) * numpy.sqrt((rank + 0.5 + 0.5 * jitter[:, 0]) / many)
        azimuth = math.pi * jitter[:, 1]
        angle = style.insertion * (0.95 + 0.25 * jitter[:, 2])
        planar[:] = False
        return owner, share, azimuth, angle, numpy.ones(total), planar
    if style.arrangement == "brush":
        share = NEEDLE_START + (1.0 - NEEDLE_START) * (rank + 0.5 + 0.3 * jitter[:, 0]) / (many + 0.5)
        azimuth = BRUSH_ROLL * rank + 0.35 * jitter[:, 1]
        angle = style.insertion * (0.6 + 0.4 * numpy.abs(jitter[:, 2]))
        planar[:] = False
        return owner, share, azimuth, angle, size, planar
    if style.arrangement == "opposite":
        rows = (many + 1) // 2
        row = rank // 2
        share = 0.2 + 0.8 * (row + 0.5 + 0.15 * jitter[:, 0]) / rows
        azimuth = numpy.where(rank % 2 == 0, 0.5, -0.5) * math.pi + 0.3 * jitter[:, 1]
        angle = style.insertion * (0.97 + 0.22 * jitter[:, 2])
        return owner, share, azimuth, angle, size, planar
    along = many - numpy.maximum(3, numpy.round(0.7 * many)).astype(int) if style.arrangement == "terminal" else many - 1
    along = numpy.maximum(along, 0)
    on_side = rank < along
    share = numpy.where(on_side, 0.2 + 0.8 * (rank + 0.5 + 0.25 * jitter[:, 0]) / numpy.maximum(along, 1), 1.0)
    if style.arrangement == "terminal":
        share = numpy.where(on_side, 0.35 + 0.4 * (rank + 0.5) / numpy.maximum(along, 1), 1.0)
    rosette = numpy.maximum(many - along, 1)
    spoke = 2.0 * math.pi * (rank - along + 0.3 * jitter[:, 1]) / rosette
    side_azimuth = numpy.where(rank % 2 == 0, 0.5, -0.5) * math.pi + 0.3 * jitter[:, 1]
    if style.arrangement == "terminal":
        azimuth = numpy.where(on_side, side_azimuth, spoke)
        angle = style.insertion * numpy.where(on_side, 0.97 + 0.22 * jitter[:, 2], 0.85 + 0.25 * jitter[:, 2])
        size = numpy.where(on_side, size, 0.85 + 0.3 * rng.uniform(0.0, 1.0, total))
    else:
        azimuth = numpy.where(on_side, side_azimuth, 0.2 * jitter[:, 1])
        angle = numpy.where(on_side, style.insertion * (0.97 + 0.22 * jitter[:, 2]), 0.2 * numpy.abs(jitter[:, 2]))
    return owner, share, azimuth, angle, size, planar


class Leaves:
    def __init__(self, count):
        self.count = count


def shape_scale(style, shape):
    """Each leaf shape has its own length, so the shapes differ in geometry as well as in outline."""
    scales = numpy.array(style.shape_length)
    return scales[numpy.minimum(shape * len(scales) // max(style.shapes, 1), len(scales) - 1)]


def make_leaves(style, rng, units):
    counts = rng.integers(style.leaf_range[0], style.leaf_range[1] + 1, len(units.length))
    owner, share, azimuth, angle, size, planar = leaf_layout(style, rng, counts)
    total = len(owner)
    bend = numpy.full(total, style.twig_bend)
    tangent, side, normal = twig_frames(bend, share)
    across = numpy.sin(azimuth)[:, None] * side + numpy.cos(azimuth)[:, None] * normal
    direction = numpy.cos(angle)[:, None] * tangent + numpy.sin(angle)[:, None] * across
    up = numpy.where(planar[:, None], normal, across)
    local = orthonormal(unit_rows(direction), up)
    tilt = style.tilt * rng.uniform(-1.0, 1.0, total)
    local[:, :, 1] = rotate_about(local[:, :, 1], local[:, :, 0], tilt)
    local[:, :, 2] = rotate_about(local[:, :, 2], local[:, :, 0], tilt)
    rotation = units.rotation[owner]
    leaves = Leaves(total)
    leaves.unit = owner
    leaves.spray = units.spray[owner]
    leaves.origin = units.origin[owner] + numpy.einsum("nij,nj->ni", rotation, twig_points(bend, share, units.length[owner]))
    leaves.axes = numpy.einsum("nij,njk->nik", rotation, local)
    leaves.blade = style.size * units.scale[owner] * size * (1.0 + style.size_variation * rng.uniform(-1.0, 1.0, total))
    leaves.shape = rng.integers(0, style.shapes, total)
    leaves.length = leaves.blade / max(1.0 - style.petiole, 0.2) * shape_scale(style, leaves.shape)
    leaves.curl = style.curl * rng.uniform(-0.3, 1.0, total)
    leaves.fold = numpy.maximum(0.0, style.fold + style.fold_variation * rng.uniform(-1.0, 1.0, total))
    leaves.share = share
    return leaves


class Batch:
    def __init__(self, points, triangles, uvs, materials, leaf_of):
        self.points = points
        self.triangles = triangles
        self.uvs = uvs
        self.materials = materials
        self.leaf_of = leaf_of


def grid_triangles(rows, columns):
    triangles = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            a = row * columns + column
            triangles.extend(((a, a + 1, a + columns + 1), (a, a + columns + 1, a + columns)))
    return numpy.array(triangles, dtype=numpy.int64)


def needle_batch(style, leaves, linear, offset):
    """A bunch of needles is one triangle fanning out of the twig; the leaf preset draws the needles into it."""
    count = leaves.count
    half = 0.5 * style.width * leaves.length
    lift = NEEDLE_TIP_LIFT * leaves.length + 0.5 * leaves.length * numpy.sin(leaves.curl)
    tips = numpy.stack([leaves.length, half, lift], axis=-1)
    local = numpy.stack([numpy.zeros((count, 3)), tips * numpy.array([1.0, 1.0, 1.0]), tips * numpy.array([1.0, -1.0, 1.0])], axis=1)
    placed = leaves.origin[:, None, :] + numpy.einsum("nij,nvj->nvi", leaves.axes, local)
    points = numpy.einsum("nij,nvj->nvi", linear[leaves.spray], placed) + linear.translation[leaves.spray][:, None, :]
    triangles = offset + NEEDLE_VERTICES * numpy.arange(count)[:, None] + numpy.array([0, 1, 2])[None, :]
    uvs = numpy.tile(numpy.array([[0.5, 0.0], [1.0, 1.0], [0.0, 1.0]]), (count, 1))
    return Batch(points.reshape(-1, 3), triangles, uvs, numpy.zeros(count, dtype=numpy.int64), numpy.arange(count))


def vertex_bound(style, sprays):
    """The most vertices `sprays` clusters can have, from the largest counts the style allows."""
    twig = len(TWIG_RINGS) * (2 if style.low else TWIG_SIDES + 1)
    if style.needles:
        per_leaf = NEEDLE_VERTICES
    else:
        per_leaf = 4 if style.flat else len(LEAF_ROWS) * 3
    units = sprays * (1 + style.forks[1])
    return units * (twig + style.leaf_range[1] * per_leaf)


def check_vertex_bound(style, sprays):
    bound = vertex_bound(style, sprays)
    if bound > MAX_MESH_VERTICES:
        raise bad_args(f"{sprays} clusters of up to {style.leaf_range[1]} leaves on up to {1 + style.forks[1]} twigs could have {bound} vertices, more than the cap of {MAX_MESH_VERTICES}; raise clusters.spacing or lower clusters.leaves, forks or per_tip")


def leaf_batch(style, leaves, linear, offset):
    if style.needles:
        return needle_batch(style, leaves, linear, offset)
    rows = numpy.array(FLAT_ROWS if style.flat else LEAF_ROWS)
    columns = numpy.array((-0.5, 0.5) if style.flat else (-0.5, 0.0, 0.5))
    count = leaves.count
    bend = leaves.curl[:, None] * rows[None, :]
    curled = numpy.abs(leaves.curl) > 1e-6
    safe = numpy.where(curled, leaves.curl, 1.0)
    reach = numpy.where(curled[:, None], leaves.length[:, None] * numpy.sin(bend) / safe[:, None], rows[None, :] * leaves.length[:, None])
    drop = numpy.where(curled[:, None], -leaves.length[:, None] * (1.0 - numpy.cos(bend)) / safe[:, None], 0.0)
    across = columns[None, :] * style.width * leaves.length[:, None]
    lift = numpy.zeros_like(across) if style.flat else numpy.abs(across) * numpy.tan(leaves.fold)[:, None]
    local = numpy.zeros((count, len(rows), len(columns), 3))
    local[..., 0] = reach[:, :, None] + lift[:, None, :] * numpy.sin(bend)[:, :, None]
    local[..., 1] = across[:, None, :]
    local[..., 2] = drop[:, :, None] + lift[:, None, :] * numpy.cos(bend)[:, :, None]
    placed = leaves.origin[:, None, None, :] + numpy.einsum("nij,nrcj->nrci", leaves.axes, local)
    points = numpy.einsum("nij,nrcj->nrci", linear[leaves.spray], placed) + linear.translation[leaves.spray][:, None, None, :]
    template = grid_triangles(len(rows), len(columns))
    per = len(rows) * len(columns)
    triangles = (template[None, :, :] + offset + per * numpy.arange(count)[:, None, None]).reshape(-1, 3)
    grid_uv = numpy.stack(numpy.meshgrid(columns + 0.5, rows, indexing="xy"), axis=-1).reshape(-1, 2)
    uvs = numpy.tile(grid_uv[template].reshape(-1, 2), (count, 1))
    leaf_of = numpy.repeat(numpy.arange(count), len(template))
    return Batch(points.reshape(-1, 3), triangles, uvs, numpy.zeros(len(triangles), dtype=numpy.int64), leaf_of)


def twig_batch(style, units, linear, offset):
    count = len(units.length)
    rings = numpy.array(TWIG_RINGS)
    sides = numpy.arange(TWIG_SIDES + 1) * 2.0 * math.pi / TWIG_SIDES
    bend = numpy.full((count, len(rings)), style.twig_bend)
    share = numpy.broadcast_to(rings, (count, len(rings)))
    tangent, side, normal = twig_frames(bend, share)
    centre = twig_points(bend, share, units.length[:, None])
    radius = units.radius[:, None] * (1.0 - (1.0 - TWIG_TIP_SHARE) * rings[None, :])
    if style.low:
        sides = numpy.array([-0.5 * math.pi, 0.5 * math.pi])
    offsets = numpy.cos(sides)[None, None, :, None] * normal[:, :, None, :] + numpy.sin(sides)[None, None, :, None] * side[:, :, None, :]
    local = centre[:, :, None, :] + radius[:, :, None, None] * offsets
    placed = units.origin[:, None, None, :] + numpy.einsum("nij,nrcj->nrci", units.rotation, local)
    points = numpy.einsum("nij,nrcj->nrci", linear[units.spray], placed) + linear.translation[units.spray][:, None, None, :]
    template = grid_triangles(len(rings), len(sides))
    per = len(rings) * len(sides)
    triangles = (template[None, :, :] + offset + per * numpy.arange(count)[:, None, None]).reshape(-1, 3)
    around = (2.0 * math.pi * units.radius[:, None, None] * numpy.arange(len(sides))[None, None, :] / TWIG_SIDES) * numpy.ones((1, len(rings), 1))
    along = units.length[:, None, None] * rings[None, :, None] * numpy.ones((1, 1, len(sides)))
    uv = numpy.stack([around, along], axis=-1).reshape(count, -1, 2)
    uvs = uv[:, template.reshape(-1)].reshape(-1, 2)
    return Batch(points.reshape(-1, 3), triangles, uvs, numpy.ones(len(triangles), dtype=numpy.int64), numpy.full(len(triangles), -1))


class Linear:
    def __init__(self, matrices):
        self.matrices = numpy.asarray(matrices, dtype=float)
        self.translation = self.matrices[:, :3, 3]

    def __getitem__(self, index):
        return self.matrices[index, :3, :3]


def build_sprays(style, rng, matrices):
    check_vertex_bound(style, len(matrices))
    linear = Linear(matrices)
    units = make_units(style, rng, len(linear.matrices))
    leaves = make_leaves(style, rng, units)
    twigs = twig_batch(style, units, linear, 0)
    foliage = leaf_batch(style, leaves, linear, len(twigs.points))
    batch = Batch(
        numpy.vstack([twigs.points, foliage.points]),
        numpy.vstack([twigs.triangles, foliage.triangles]),
        numpy.vstack([twigs.uvs, foliage.uvs]),
        numpy.concatenate([twigs.materials, foliage.materials]),
        numpy.concatenate([twigs.leaf_of, foliage.leaf_of]),
    )
    return batch, leaves
