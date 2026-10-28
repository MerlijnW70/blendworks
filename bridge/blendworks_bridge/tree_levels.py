import math

import numpy

from .errors import bad_args
from .tree_colonize import SHOOT
from .tree_shapes import shape_ratio

SPACING_TOLERANCE = 1e-9
MIDDLE_SHARE = 0.6


def per_level(values, index):
    return values[min(index, len(values) - 1)]


def rotated(vector, axis, angle):
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return vector * cosine + numpy.cross(axis, vector) * sine + axis * numpy.dot(axis, vector) * (1.0 - cosine)


def normalised(vector):
    return vector / numpy.linalg.norm(vector)


class LevelPlan:
    def __init__(self, args):
        self.levels = args["levels"]
        self.branches = args["branches"]
        self.down_angle = args["down_angle"]
        self.rotate = args["rotate"]
        self.length_ratio = args["length_ratio"]
        self.curve = args["curve"]
        self.curve_back = args["curve_back"]
        self.curve_variation = args["curve_variation"]
        self.rng = numpy.random.default_rng([args["seed"], 2])
        self.segments = args["segments"]
        self.length = args["height"]
        self.trunk_height = args["trunk_height"]
        self.shape = args["envelope"]
        if self.trunk_height >= self.length:
            raise bad_args("trunk_height must be below height, the trunk length, for levels")

    def bend(self, level, length, start, end):
        curve = math.radians(per_level(self.curve, level))
        back = math.radians(per_level(self.curve_back, level))
        if back == 0.0:
            angle = curve * (end - start) / length
        else:
            middle = 0.5 * length
            angle = (2.0 * curve * max(0.0, min(end, middle) - start) + 2.0 * back * max(0.0, end - max(start, middle))) / length
        variation = math.radians(per_level(self.curve_variation, level))
        if variation > 0.0:
            angle += variation * float(self.rng.uniform(-1.0, 1.0)) * (end - start) / length
        return angle

    def child_setting(self, values, child_level):
        return per_level(values, child_level - 1)

    def most_children(self, level):
        return 0 if level >= self.levels - 1 else int(self.child_setting(self.branches, level + 1))

    def node_bound(self):
        total = 1
        stems = 1
        for level in range(self.levels):
            children = self.most_children(level)
            total += stems * (int(per_level(self.segments, level)) + 2 * children)
            stems *= children
        return total

    def child_length(self, child_level, parent_length, offset):
        ratio = self.child_setting(self.length_ratio, child_level)
        if child_level == 1:
            return parent_length * ratio * float(shape_ratio(self.shape, (parent_length - offset) / (parent_length - self.trunk_height)))
        return ratio * (parent_length - MIDDLE_SHARE * offset)

    def child_count(self, child_level, length, parent_length):
        if child_level >= self.levels - 1:
            return 0
        relative = (length / parent_length) / self.child_setting(self.length_ratio, child_level)
        return int(round(self.child_setting(self.branches, child_level + 1) * (0.2 + 0.8 * relative)))


class Stem:
    def __init__(self, level, length, base, count):
        self.level = level
        self.length = length
        self.base = base
        self.count = count
        self.nodes = []
        self.arcs = []
        self.attachments = []


def arc_lengths(length, offsets, segments):
    grid = [length * step / segments for step in range(1, segments + 1)]
    marks = sorted(set(grid) | set(offsets))
    values = []
    for value in marks:
        if values and value - values[-1] <= SPACING_TOLERANCE * length:
            if value in offsets:
                values[-1] = value
            continue
        values.append(value)
    with_slots = []
    for index, value in enumerate(values):
        with_slots.append(value)
        if value in offsets and index + 1 < len(values):
            with_slots.append(0.5 * (value + values[index + 1]))
    return with_slots


class LevelGrowth:
    def __init__(self, plan, nodes, base_height):
        self.plan = plan
        self.nodes = nodes
        self.base_height = base_height
        self.stems = []
        self.stem_of = {0: 0}
        self.fraction = {0: 0.0}
        self.levels_of = {0: 0}
        self.truncated = 0

    def grow(self):
        tangent = numpy.array([0.0, 0.0, 1.0])
        normal = numpy.array([1.0, 0.0, 0.0])
        self.build(0, self.plan.length, 0, tangent, normal, self.plan.most_children(0))
        return self

    def offsets(self, stem):
        if stem.count <= 0:
            return []
        start = self.plan.trunk_height if stem.level == 0 else 0.0
        return [start + (stem.length - start) * (index + 0.5) / stem.count for index in range(stem.count)]

    def build(self, level, length, base, tangent, normal, count):
        stem = Stem(level, length, base, count)
        stem_index = len(self.stems)
        self.stems.append(stem)
        offsets = self.offsets(stem)
        arcs = arc_lengths(length, offsets, int(per_level(self.plan.segments, level)))
        position = self.nodes.positions[base].copy()
        previous = 0.0
        frames = {}
        for arc in arcs:
            if self.nodes.room <= 0:
                raise bad_args("the levels tree needs more nodes than max_nodes")
            step = arc - previous
            axis = numpy.cross(tangent, normal)
            angle = self.plan.bend(level, length, previous, arc)
            tangent = normalised(rotated(tangent, axis, angle))
            normal = normalised(rotated(normal, axis, angle))
            position = position + tangent * step
            if position[2] <= self.base_height:
                self.truncated += 1
                break
            parent = stem.nodes[-1] if stem.nodes else base
            node = self.nodes.add(position, parent, SHOOT)
            stem.nodes.append(node)
            stem.arcs.append(arc)
            self.stem_of[node] = stem_index
            self.fraction[node] = arc / length
            self.levels_of[node] = level
            frames[arc] = (node, tangent.copy(), normal.copy())
            previous = arc
        for index, offset in enumerate(offsets):
            if offset in frames:
                self.attach(stem, index, offset, *frames[offset])
        return stem

    def attach(self, stem, index, offset, node, tangent, normal):
        child_level = stem.level + 1
        length = self.plan.child_length(child_level, stem.length, offset)
        if length <= 0.0:
            return
        binormal = numpy.cross(tangent, normal)
        azimuth = math.radians(self.plan.child_setting(self.plan.rotate, child_level)) * index
        down = math.radians(self.plan.child_setting(self.plan.down_angle, child_level))
        side = math.cos(azimuth) * normal + math.sin(azimuth) * binormal
        direction = normalised(math.cos(down) * tangent + math.sin(down) * side)
        towards = tangent - numpy.dot(tangent, direction) * direction
        child_normal = normalised(towards) if numpy.linalg.norm(towards) > 1e-9 else normal
        stem.attachments.append({"node": node, "offset": offset, "index": index, "azimuth": azimuth, "length": length})
        self.build(child_level, length, node, direction, child_normal, self.plan.child_count(child_level, length, stem.length))

    def stem_tables(self, count):
        stem_of = numpy.full(count, -1, dtype=numpy.int64)
        fraction = numpy.zeros(count)
        order = numpy.full(count, -1, dtype=numpy.int64)
        for node, stem in self.stem_of.items():
            stem_of[node] = stem
            fraction[node] = self.fraction[node]
            order[node] = self.levels_of[node]
        lengths = numpy.array([stem.length for stem in self.stems])
        return stem_of, fraction, order, lengths
