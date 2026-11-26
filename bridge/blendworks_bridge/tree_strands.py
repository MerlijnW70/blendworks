import math

import numpy

from .tree_skeleton import chains

HANGING_SHARE = 0.5
MIN_STRANDS = 3
MIN_SIBLINGS = 3
FORK_SHARE = 0.3
IRREGULAR = {"spacing_cv": 0.3, "neighbour_length_change": 0.15}


def arc_positions(points):
    steps = numpy.linalg.norm(numpy.diff(points, axis=0), axis=1)
    return numpy.concatenate([[0.0], numpy.cumsum(steps)])


def coefficient_of_variation(values):
    values = numpy.asarray(values, dtype=float)
    if len(values) < 2 or values.mean() <= 0.0:
        return 0.0
    return float(values.std() / values.mean())


class Strand:
    def __init__(self, chain, positions, order):
        self.order = order
        self.attach = chain[0]
        self.nodes = chain[1:]
        points = positions[chain]
        self.length = float(arc_positions(points)[-1])
        self.drop = float(points[0, 2] - points[:, 2].min())
        span = points[-1] - points[0]
        size = float(numpy.linalg.norm(span))
        self.lean = math.degrees(math.acos(max(-1.0, min(1.0, -span[2] / size)))) if size > 0.0 else 0.0
        self.bearing = math.atan2(span[1], span[0])

    def hangs(self):
        return self.length > 0.0 and self.drop >= HANGING_SHARE * self.length


def hanging_strands(skeleton):
    found = chains(skeleton)
    positions = skeleton.positions
    owner = numpy.full(skeleton.count, -1, dtype=numpy.int64)
    arc = numpy.zeros(skeleton.count)
    for index, (chain, branched) in enumerate(found):
        own = chain[1:] if branched else chain
        owner[own] = index
        arc[own] = arc_positions(positions[chain])[len(chain) - len(own):]
    strands = []
    for chain, branched in found:
        if not branched or skeleton.kinds[chain[-1]] != 0:
            continue
        strand = Strand(chain, positions, int(skeleton.orders[chain[1]]))
        if strand.hangs():
            strands.append(strand)
    return strands, owner, arc


def dominant(strands):
    totals = {}
    for strand in strands:
        totals[strand.order] = totals.get(strand.order, 0.0) + strand.length
    order = max(totals, key=lambda key: (totals[key], -key))
    return order, [strand for strand in strands if strand.order == order]


def strand_statistics(skeleton):
    every, owner, arc = hanging_strands(skeleton)
    if not every:
        return {"count": 0}
    order, strands = dominant(every)
    report = {"count": len(strands), "order": order}
    if len(strands) < MIN_STRANDS:
        return report
    siblings = {}
    for strand in strands:
        siblings.setdefault(int(owner[strand.attach]), []).append((float(arc[strand.attach]), strand.length))
    spacings = []
    changes = []
    for found in siblings.values():
        if len(found) < MIN_SIBLINGS:
            continue
        places, lengths = numpy.array(sorted(found)).T
        gaps = numpy.diff(places)
        if gaps.mean() > 0.0:
            spacings.extend(gaps / gaps.mean())
        pairs = 0.5 * (lengths[1:] + lengths[:-1])
        changes.extend(numpy.abs(numpy.diff(lengths)) / numpy.maximum(pairs, 1e-9))
    forks = {}
    for strand in every:
        forks.setdefault(strand.attach, []).append(strand.length)
    branched = sum(1 for strand in strands if any(length >= FORK_SHARE * strand.length for node in strand.nodes for length in forks.get(node, ())))
    leans = numpy.array([strand.lean for strand in strands])
    report.update({
        "length_cv": round(coefficient_of_variation([strand.length for strand in strands]), 4),
        "drop_cv": round(coefficient_of_variation([strand.drop for strand in strands]), 4),
        "neighbour_length_change": round(float(numpy.mean(changes)) if changes else 0.0, 4),
        "spacing_cv": round(float(numpy.std(spacings)) if len(spacings) >= 2 else 0.0, 4),
        "branched_share": round(branched / len(strands), 4),
        "lean_spread": round(float(leans.std()), 3),
        "mean_drop": round(float(numpy.mean([strand.drop for strand in strands])), 4),
        "radius_cv": round(coefficient_of_variation([skeleton.radii[strand.nodes[0]] for strand in strands]), 4),
    })
    report["irregular"] = all(report[key] >= limit for key, limit in IRREGULAR.items())
    return report


SWAY_DEFAULTS = {"strength": 0.0, "by_order": [1.0]}
HEM_DEFAULTS = {"height": 0.3, "rise": 0.0, "variation": 0.0, "order": 2}


def axis_starts(parents, orders, kinds):
    starts = numpy.arange(len(parents))
    for node in range(1, len(parents)):
        parent = parents[node]
        if orders[node] == orders[parent] and kinds[node] == kinds[parent]:
            starts[node] = starts[parent]
    return starts


class Sway:
    def __init__(self, given, seed):
        values = {**SWAY_DEFAULTS, **(given or {})}
        self.strength = float(values["strength"])
        self.by_order = values["by_order"]
        self.seed = seed
        self.targets = None

    def prepare(self, parents, orders, kinds):
        if self.strength <= 0.0:
            return
        starts = axis_starts(parents, orders, kinds)
        rng = numpy.random.default_rng([self.seed, 7])
        bearings = rng.uniform(0.0, 2.0 * math.pi, len(parents))
        shares = rng.uniform(0.0, 1.0, len(parents))
        self.targets = [(math.cos(bearings[start]), math.sin(bearings[start]), 0.0) for start in starts]
        self.rates = [self.strength * shares[start] * float(self.by_order[min(int(orders[node]), len(self.by_order) - 1)]) for node, start in enumerate(starts)]

    def pull(self, node):
        if self.targets is None or self.rates[node] <= 0.0:
            return []
        return [(self.targets[node], self.rates[node])]


def hem_keep(positions, parents, orders, kinds, given, seed):
    values = {**HEM_DEFAULTS, **given}
    keep = numpy.ones(len(parents), dtype=bool)
    starts = axis_starts(parents, orders, kinds)
    spread = float(numpy.hypot(positions[:, 0] - positions[0, 0], positions[:, 1] - positions[0, 1]).max())
    rng = numpy.random.default_rng([seed, 8])
    shares = rng.uniform(-1.0, 1.0, len(parents))
    base = positions[0][2]
    floors = numpy.full(len(parents), -math.inf)
    for node in range(1, len(parents)):
        start = starts[node]
        if kinds[node] != 0 or orders[node] < values["order"]:
            floors[node] = floors[parents[node]]
        elif start == node:
            reach = math.hypot(*(positions[node][:2] - positions[0][:2])) / max(spread, 1e-9)
            floors[node] = base + values["height"] * (1.0 + values["variation"] * shares[node]) + values["rise"] * (1.0 - min(reach, 1.0)) ** 2
        else:
            floors[node] = floors[start]
        keep[node] = keep[parents[node]] and positions[node][2] >= floors[node]
    return keep
