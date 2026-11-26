import math

import numpy

from .tree_leaves import EPSILON, shoot_chains
from .tree_sprays import frame_of, turned
from .tree_frames import first_normal

OUTER_START = 0.45
ATTRIBUTES = ("leaf_hue", "leaf_saturation", "leaf_value", "leaf_age", "leaf_damage", "leaf_shape", "leaf_seed")
DAMAGED_SHARE = 0.18
SHARED_SHARE = 0.5


class Spray:
    def __init__(self, position, direction, height, tip, chain):
        self.position = position
        self.direction = direction
        self.height = height
        self.tip = tip
        self.chain = chain
        self.outer = 0.0
        self.up = None
        self.scale = 1.0


def chain_frames(skeleton, chain):
    points = skeleton.positions[chain].astype(float)
    radii = skeleton.radii[chain].astype(float)
    steps = numpy.diff(points, axis=0)
    lengths = numpy.linalg.norm(steps, axis=1)
    directions = steps / numpy.maximum(lengths, EPSILON)[:, None]
    along = numpy.concatenate([[0.0], numpy.cumsum(lengths)])
    return points, radii, steps, lengths, directions, along


def sprays_on_chain(skeleton, chain, height, cluster, tip_count, rng, chain_index, bearing=0.0, leafy=True):
    points, radii, steps, lengths, directions, along = chain_frames(skeleton, chain)
    total = float(along[-1])
    if total <= EPSILON:
        return []
    found = []
    spacing = cluster["spacing"]
    insertion = math.radians(cluster["angle"])
    if spacing > 0.0 and (leafy or bearing > 0.0):
        reach = cluster["reach"]
        distance = (max(0.0, total - reach) if reach > 0.0 else 0.0) + spacing * rng.uniform(0.2, 1.0)
        azimuth = rng.uniform(0.0, 2.0 * math.pi)
        normal = first_normal(directions[0])
        while distance < total - 0.25 * spacing:
            segment = int(min(numpy.searchsorted(along, distance, side="right") - 1, len(steps) - 1))
            share = (distance - along[segment]) / max(lengths[segment], EPSILON)
            tangent = directions[segment]
            across = normal - tangent * float(normal @ tangent)
            across /= max(numpy.linalg.norm(across), EPSILON)
            outward = turned(across, tangent, azimuth)
            radius = radii[segment] + share * (radii[segment + 1] - radii[segment])
            position = points[segment] + share * steps[segment] + radius * outward
            direction = math.cos(insertion) * tangent + math.sin(insertion) * outward
            if leafy or radius <= bearing:
                found.append(Spray(position, direction, height, False, chain_index))
            azimuth += math.radians(cluster["divergence"]) + rng.uniform(-0.3, 0.3)
            distance += spacing * (1.0 + cluster["spacing_variation"] * rng.uniform(-1.0, 1.0))
    tip = points[-1]
    tangent = directions[-1]
    normal = first_normal(tangent)
    for index in range(tip_count):
        spread = 0.0 if index == 0 else math.radians(cluster["tip_spread"]) * rng.uniform(0.5, 1.0)
        side = turned(normal, tangent, 2.0 * math.pi * (index + rng.uniform(-0.3, 0.3)) / max(tip_count, 1))
        direction = turned(tangent, numpy.cross(tangent, side), spread)
        found.append(Spray(tip.copy(), direction, max(height, 1), True, chain_index))
    return found


def outerness(positions):
    centre = positions.mean(axis=0)
    reach = numpy.percentile(numpy.abs(positions - centre), 95.0, axis=0)
    reach = numpy.maximum(reach, 1e-6)
    distance = numpy.linalg.norm((positions - centre) / reach, axis=1) / math.sqrt(3.0)
    raw = numpy.clip((distance - OUTER_START * distance.max()) / max((1.0 - OUTER_START) * distance.max(), 1e-9), 0.0, 1.0)
    return raw * raw * (3.0 - 2.0 * raw)


def droop(direction, amount):
    if amount <= 0.0:
        return direction
    down = numpy.array([0.0, 0.0, -1.0])
    axis = numpy.cross(direction, down)
    if numpy.linalg.norm(axis) < 1e-9:
        return direction
    between = math.acos(max(-1.0, min(1.0, float(direction @ down))))
    return turned(direction, axis, amount * between)


def place_sprays(skeleton, args):
    rng = numpy.random.default_rng([args["seed"], 11])
    cluster = args["clusters"]
    child_count = numpy.bincount(skeleton.parents[1:], minlength=skeleton.count)
    sprays = []
    for index, chain, _, height in shoot_chains(skeleton):
        leafy = height <= args["orders"]
        tips = cluster["per_tip"] if child_count[chain[-1]] == 0 else 0
        bearing = cluster["bearing_radius"]
        if not leafy and tips == 0 and bearing <= 0.0:
            continue
        sprays.extend(sprays_on_chain(skeleton, chain, min(height, args["orders"]) if leafy else 1, cluster, tips, rng, index, bearing, leafy))
    if not sprays:
        return []
    outer = outerness(numpy.array([spray.position for spray in sprays]))
    keep_inner = cluster["inner_keep"]
    kept = []
    sun = numpy.asarray(args["align"]["sun"], dtype=float)
    sun = sun / max(numpy.linalg.norm(sun), EPSILON)
    inner_factor, outer_factor = args["align"]["inner"], args["align"]["factor"]
    draws = rng.uniform(0.0, 1.0, (len(sprays), 4))
    for spray, share, (keep, roll, grow, _) in zip(sprays, outer, draws):
        if not spray.tip and keep > keep_inner + (1.0 - keep_inner) * share:
            continue
        spray.outer = float(share)
        spray.direction = droop(spray.direction / numpy.linalg.norm(spray.direction), cluster["droop"])
        factor = inner_factor + (outer_factor - inner_factor) * share
        x_axis = spray.direction
        level = numpy.array([0.0, 0.0, 1.0]) - x_axis * float(x_axis[2])
        if numpy.linalg.norm(level) < 1e-6:
            level = first_normal(x_axis)
        level /= numpy.linalg.norm(level)
        towards = sun - x_axis * float(sun @ x_axis)
        if numpy.linalg.norm(towards) > 1e-6:
            towards /= numpy.linalg.norm(towards)
            angle = math.atan2(float(numpy.cross(level, towards) @ x_axis), float(level @ towards))
        else:
            angle = 0.0
        jitter = math.radians(args["jitter"]["roll"]) * (2.0 * roll - 1.0) * (1.0 - 0.5 * factor)
        spray.up = turned(level, x_axis, factor * angle + jitter)
        spray.scale = args["size_by_order"] ** (spray.height - 1 if spray.height > 0 else 0) * (1.0 + args["jitter"]["size"] * (2.0 * grow - 1.0)) * (1.0 + cluster["shade_growth"] * (1.0 - share))
        kept.append(spray)
    return kept


def spray_matrix(spray):
    x_axis, y_axis, z_axis = frame_of(spray.direction, spray.up)
    matrix = numpy.identity(4)
    matrix[:3, 0] = x_axis * spray.scale
    matrix[:3, 1] = y_axis * spray.scale
    matrix[:3, 2] = z_axis * spray.scale
    matrix[:3, 3] = spray.position
    return matrix


def leaf_attributes(rng, outer, leaves, variation, shapes):
    count = leaves.count
    shared = rng.uniform(-1.0, 1.0, (len(outer), 3))[leaves.spray]
    own = rng.uniform(-1.0, 1.0, (count, 3))
    mixed = SHARED_SHARE * shared + (1.0 - SHARED_SHARE) * own
    age = numpy.clip(variation["age"] * (1.0 - 2.0 * leaves.share + 0.6 * rng.uniform(-1.0, 1.0, count)), -1.0, 1.0)
    damaged = rng.uniform(0.0, 1.0, count) < DAMAGED_SHARE * (0.5 + 0.5 * numpy.clip(age + 1.0, 0.0, 2.0))
    damage = numpy.where(damaged, variation["damage"] * rng.uniform(0.2, 1.0, count), 0.0)
    return {
        "leaf_hue": variation["hue"] * mixed[:, 0],
        "leaf_saturation": variation["saturation"] * mixed[:, 1],
        "leaf_value": variation["value"] * (mixed[:, 2] + 0.6 * (outer[leaves.spray] - 0.5)),
        "leaf_age": age,
        "leaf_damage": damage,
        "leaf_shape": (leaves.shape + 0.5) / max(shapes, 1),
        "leaf_seed": rng.uniform(0.0, 1.0, count),
    }
