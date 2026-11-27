import math

import numpy
from mathutils import Matrix

from .errors import bad_args
from .kit_limits import MAX_INSTANCES
from .meshdata import MeshData
from .tree_axes import heights_from_tips
from .tree_frames import first_normal, reflect

EPSILON = 1e-12


class Leaf:
    def __init__(self, position, tangent, outward, height, chain, index, tip):
        self.position = position
        self.tangent = tangent
        self.outward = outward
        self.height = height
        self.chain = chain
        self.index = index
        self.tip = tip


def shoot_chains(skeleton):
    found, _, heights = heights_from_tips(skeleton)
    picked = []
    for index, (chain, branched) in enumerate(found):
        if skeleton.kinds[chain[-1]] == 0 and len(chain) >= 2:
            picked.append((index, chain, branched, int(heights[index])))
    return picked


def transport(normal, tangent, next_tangent, step):
    square = float(step @ step)
    if square < EPSILON:
        return normal
    reflected = reflect(normal, step, square)
    turned = reflect(tangent, step, square)
    second = next_tangent - turned
    square_two = float(second @ second)
    moved = reflected if square_two < EPSILON else reflect(reflected, second, square_two)
    moved = moved - next_tangent * float(moved @ next_tangent)
    return moved / max(float(numpy.linalg.norm(moved)), EPSILON)


def along_path(normal, previous, position, points, directions, segment):
    start, first = previous
    path = [start] + [points[index] for index in range(first + 1, segment + 1)] + [position]
    tangents = [directions[first]] + [directions[index] for index in range(first + 1, segment + 1)] + [directions[segment]]
    for index in range(len(path) - 1):
        normal = transport(normal, tangents[index], tangents[index + 1], path[index + 1] - path[index])
    return normal


def side_leaf_count(total, density):
    """Exact: leaves sit at (index + 0.5) / density while that is below total; the kept indices are a prefix."""
    if density <= 0.0:
        return 0
    most = int(math.floor(total * density + 0.5))
    count = max(0, min(most, math.ceil(total * density - 0.5)))
    while count > 0 and (count - 0.5) / density >= total:
        count -= 1
    while count < most and (count + 0.5) / density < total:
        count += 1
    return count


def chain_length(skeleton, chain):
    lengths = numpy.linalg.norm(numpy.diff(skeleton.positions[chain].astype(float), axis=0), axis=1)
    return float(numpy.cumsum(lengths)[-1]) if (lengths > EPSILON).any() else None


def chain_leaves(skeleton, chain, height, density, tip_leaves, divergence, phase, chain_index):
    points = skeleton.positions[chain].astype(float)
    radii = skeleton.radii[chain].astype(float)
    steps = numpy.diff(points, axis=0)
    lengths = numpy.linalg.norm(steps, axis=1)
    keep = lengths > EPSILON
    if not keep.any():
        return []
    directions = steps / numpy.maximum(lengths, EPSILON)[:, None]
    along = numpy.concatenate([[0.0], numpy.cumsum(lengths)])
    total = float(along[-1])
    count = side_leaf_count(total, density)
    places = [(index + 0.5) / density for index in range(count)]
    places += [total] * tip_leaves
    leaves = []
    normal = None
    previous = None
    for number, distance in enumerate(places):
        segment = int(min(numpy.searchsorted(along, distance, side="right") - 1, len(steps) - 1))
        share = (distance - along[segment]) / max(lengths[segment], EPSILON)
        position = points[segment] + share * steps[segment]
        tangent = directions[segment]
        if normal is None:
            normal = first_normal(tangent)
        else:
            normal = along_path(normal, previous, position, points, directions, segment)
        previous = (position, segment)
        turn = math.radians(phase + number * divergence)
        binormal = numpy.cross(tangent, normal)
        outward = math.cos(turn) * normal + math.sin(turn) * binormal
        radius = radii[segment] + share * (radii[segment + 1] - radii[segment])
        leaves.append(Leaf(position + radius * outward, tangent, outward, height, chain_index, number, distance >= total - EPSILON and number >= count))
    return leaves


def leaf_matrix(leaf, angle, sun, factor, roll, scale):
    insertion = math.radians(angle)
    x_axis = math.cos(insertion) * leaf.tangent + math.sin(insertion) * leaf.outward
    x_axis /= numpy.linalg.norm(x_axis)
    y_axis = numpy.cross(leaf.tangent, leaf.outward)
    y_axis /= max(numpy.linalg.norm(y_axis), EPSILON)
    z_axis = numpy.cross(x_axis, y_axis)
    target = sun - x_axis * float(sun @ x_axis)
    if numpy.linalg.norm(target) > 1e-6:
        target /= numpy.linalg.norm(target)
        full = math.atan2(float(numpy.cross(z_axis, target) @ x_axis), float(z_axis @ target))
    else:
        full = 0.0
    spin = factor * full + roll
    y_turned = math.cos(spin) * y_axis + math.sin(spin) * z_axis
    z_turned = numpy.cross(x_axis, y_turned)
    matrix = Matrix.Identity(4)
    for row in range(3):
        matrix[row][0] = x_axis[row] * scale
        matrix[row][1] = y_turned[row] * scale
        matrix[row][2] = z_turned[row] * scale
        matrix[row][3] = leaf.position[row]
    return matrix


def check_leaf_count(skeleton, bearing):
    """Exact: every bearing chain gets side_leaf_count side leaves plus its tip leaves, as chain_leaves places them."""
    total = 0
    for _, chain, _, tips, density in bearing:
        length = chain_length(skeleton, chain)
        if length is not None:
            total += side_leaf_count(length, density) + tips
    if total > MAX_INSTANCES:
        raise bad_args(f"{total} leaves; the {MAX_INSTANCES.key} limit is {MAX_INSTANCES.plain()} ({MAX_INSTANCES.reason}) "
                       "Lower density, tip_leaves or orders.")


def place_leaves(skeleton, args):
    rng = numpy.random.default_rng(args["seed"])
    sun = numpy.asarray(args["align"]["sun"], dtype=float)
    sun = sun / max(numpy.linalg.norm(sun), EPSILON)
    leaves = []
    child_count = numpy.bincount(skeleton.parents[1:], minlength=skeleton.count)
    bearing = []
    for index, chain, _, height in shoot_chains(skeleton):
        tips = args["tip_leaves"] if child_count[chain[-1]] == 0 else 0
        density = args["density"] if height <= args["orders"] else 0.0
        if tips != 0 or density != 0.0:
            bearing.append((index, chain, height, tips, density))
    check_leaf_count(skeleton, bearing)
    for index, chain, height, tips, density in bearing:
        phase = float(rng.uniform(0.0, 360.0))
        leaves.extend(chain_leaves(skeleton, chain, min(height, args["orders"]), density, tips, args["divergence"], phase, index))
    jitter = args["jitter"]
    draws = rng.uniform(-1.0, 1.0, size=(len(leaves), 2))
    matrices = []
    sizes = []
    for leaf, (roll, grow) in zip(leaves, draws):
        size = args["size"] * args["size_by_order"] ** (leaf.height - 1) * (1.0 + jitter["size"] * grow)
        sizes.append(size)
        matrices.append(leaf_matrix(leaf, args["angle"], sun, args["align"]["factor"], math.radians(jitter["roll"]) * roll, size))
    return leaves, matrices, sizes


def leaf_card(width, fold):
    lift = 0.5 * width * math.tan(math.radians(fold))
    data = MeshData()
    base = data.vertex((0.0, 0.0, 0.0))
    tip = data.vertex((1.0, 0.0, 0.0))
    left_base = data.vertex((0.0, -0.5 * width, lift))
    left_tip = data.vertex((1.0, -0.5 * width, lift))
    right_base = data.vertex((0.0, 0.5 * width, lift))
    right_tip = data.vertex((1.0, 0.5 * width, lift))
    data.face((base, left_base, left_tip, tip), [(0.5, 0.0), (0.0, 0.0), (0.0, 1.0), (0.5, 1.0)], smooth=True)
    data.face((base, tip, right_tip, right_base), [(0.5, 0.0), (0.5, 1.0), (1.0, 1.0), (1.0, 0.0)], smooth=True)
    return data
