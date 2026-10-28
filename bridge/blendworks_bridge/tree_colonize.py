import numpy

from .errors import bad_args
from .tree_shapes import canonical_order

SHOOT = 0
ROOT = 1
MAX_ITERATIONS = 4000
DUPLICATE_SHARE = 0.01
MEASURE_CELLS = 2_000_000


class Nodes:
    def __init__(self, capacity):
        self.capacity = capacity
        self.positions = numpy.zeros((capacity, 3))
        self.parents = numpy.full(capacity, -1, dtype=numpy.int64)
        self.kinds = numpy.zeros(capacity, dtype=numpy.int64)
        self.count = 0
        self.children = []

    def add(self, position, parent, kind):
        index = self.count
        self.positions[index] = position
        self.parents[index] = parent
        self.kinds[index] = kind
        self.children.append([])
        if parent >= 0:
            self.children[parent].append(index)
        self.count += 1
        return index

    @property
    def room(self):
        return self.capacity - self.count

    def view(self):
        return self.positions[: self.count], self.parents[: self.count], self.kinds[: self.count]


class Group:
    def __init__(self, kind, points, envelope, influence, kill, step, tropism):
        self.kind = kind
        self.points = canonical_order(points)
        self.envelope = envelope
        self.influence = float(influence)
        self.kill = float(kill)
        self.step = float(step)
        self.tropism = numpy.asarray(tropism, dtype=float)


def unit(vectors):
    length = numpy.linalg.norm(vectors, axis=-1, keepdims=True)
    return numpy.divide(vectors, length, out=numpy.zeros_like(vectors), where=length > 1e-12), length[..., 0]


class Colonization:
    def __init__(self, nodes, groups, base_height):
        self.nodes = nodes
        self.groups = groups
        self.base_height = float(base_height)
        self.points = numpy.vstack([group.points for group in groups])
        self.owner = numpy.concatenate([numpy.full(len(group.points), index, dtype=numpy.int64) for index, group in enumerate(groups)])
        self.influence = numpy.array([group.influence for group in groups])[self.owner]
        self.kill = numpy.array([group.kill for group in groups])[self.owner]
        self.point_kinds = numpy.array([group.kind for group in groups], dtype=numpy.int64)[self.owner]
        self.alive = numpy.ones(len(self.points), dtype=bool)
        self.nearest = numpy.full(len(self.points), -1, dtype=numpy.int64)
        self.distance = numpy.full(len(self.points), numpy.inf)
        self.iterations = 0
        self.stopped = "converged"
        self.measure(0)
        self.cull()

    def measure(self, first):
        positions = self.nodes.positions[first : self.nodes.count]
        if not len(positions):
            return
        live = numpy.flatnonzero(self.alive)
        if not len(live):
            return
        block_size = max(1, MEASURE_CELLS // len(live))
        for start in range(0, len(positions), block_size):
            block = positions[start : start + block_size]
            gaps = numpy.sqrt(((self.points[live, None, :] - block[None, :, :]) ** 2).sum(axis=2))
            best = gaps.argmin(axis=1)
            closest = gaps[numpy.arange(len(live)), best]
            better = closest < self.distance[live]
            self.distance[live[better]] = closest[better]
            self.nearest[live[better]] = first + start + best[better]

    def cull(self):
        self.alive &= self.distance >= self.kill

    def influenced(self):
        live = numpy.flatnonzero(self.alive & (self.distance < self.influence))
        if not len(live):
            return live
        nearest = self.nearest[live]
        kinds = self.point_kinds[live]
        grows = (self.nodes.kinds[nearest] == kinds) | ((kinds == ROOT) & (nearest == 0))
        return live[grows]

    def candidates(self, live):
        keys = self.nearest[live] * len(self.groups) + self.owner[live]
        directions, _ = unit(self.points[live] - self.nodes.positions[self.nearest[live]])
        order = numpy.argsort(keys, kind="stable")
        keys = keys[order]
        directions = directions[order]
        unique, starts = numpy.unique(keys, return_index=True)
        sums = numpy.add.reduceat(directions, starts, axis=0)
        found = []
        for key, total in zip(unique.tolist(), sums):
            node, group_index = divmod(key, len(self.groups))
            group = self.groups[group_index]
            heading, length = unit(total)
            if length < 1e-9:
                continue
            biased, length = unit(heading + group.tropism)
            if length < 1e-9:
                continue
            found.append((node, group_index, self.nodes.positions[node] + group.step * biased))
        return found

    def allowed(self, node, group, position):
        if group.kind == SHOOT and position[2] <= self.base_height:
            return False
        if group.kind == ROOT and position[2] >= self.base_height:
            return False
        if group.envelope.outside_distance(position[None, :])[0] > group.step:
            return False
        siblings = self.nodes.children[node]
        if siblings:
            gaps = numpy.linalg.norm(self.nodes.positions[siblings] - position, axis=1)
            if gaps.min() < DUPLICATE_SHARE * group.step:
                return False
        return True

    def step(self):
        live = self.influenced()
        if not len(live):
            return False
        accepted = [(node, group_index, position) for node, group_index, position in self.candidates(live) if self.allowed(node, self.groups[group_index], position)]
        if not accepted:
            return False
        if len(accepted) > self.nodes.room:
            accepted = accepted[: self.nodes.room]
            self.stopped = "max_nodes"
        first = self.nodes.count
        for node, group_index, position in accepted:
            self.nodes.add(position, node, self.groups[group_index].kind)
        self.measure(first)
        self.cull()
        return self.stopped != "max_nodes"

    def run(self):
        while self.iterations < MAX_ITERATIONS:
            if not self.alive.any():
                self.stopped = "no_points"
                return self
            self.iterations += 1
            if not self.step():
                return self
        self.stopped = "iterations"
        return self

    def remaining(self, group_index):
        return self.points[self.alive & (self.owner == group_index)]

    def report(self):
        return {
            "iterations": self.iterations,
            "stopped": self.stopped,
            "points": [int(len(group.points)) for group in self.groups],
            "remaining_points": [int((self.alive & (self.owner == index)).sum()) for index in range(len(self.groups))],
        }


def reaches_crown(group, position):
    if group.envelope.outside_distance(position[None, :])[0] > 0.0:
        return False
    return bool(len(group.points)) and float(numpy.linalg.norm(group.points - position, axis=1).min()) < group.influence


def grow_lead(nodes, group, direction, limit):
    direction, _ = unit(numpy.asarray(direction, dtype=float))
    top = nodes.count - 1
    while not reaches_crown(group, nodes.positions[top]):
        if nodes.positions[top][2] > limit:
            raise bad_args("the trunk passes the crown envelope without entering it; lower the sideways part of the tropism or move the envelope over the base")
        if nodes.room <= 0:
            raise bad_args("the trunk needs more nodes than max_nodes before it reaches the crown")
        top = nodes.add(nodes.positions[top] + group.step * direction, top, SHOOT)
