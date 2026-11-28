"""Branch radii by pipe model, taper and branch order."""

import numpy


def children_lists(parents):
    children = [[] for _ in range(len(parents))]
    for node in range(1, len(parents)):
        children[int(parents[node])].append(node)
    return children


class Taper:
    def __init__(self, stem_of, fraction, taper):
        self.stem_of = stem_of
        self.fraction = fraction
        self.taper = float(taper)

    def factor(self, node, child):
        if self.stem_of[node] < 0 or self.stem_of[node] != self.stem_of[child]:
            return 1.0
        return (1.0 - self.taper * self.fraction[node]) / (1.0 - self.taper * self.fraction[child])


def pipe_radii(parents, tip_radii, exponent, taper=None):
    count = len(parents)
    children = children_lists(parents)
    radii = numpy.zeros(count)
    for node in range(count - 1, -1, -1):
        below = children[node]
        if not below:
            radii[node] = tip_radii[node]
        elif len(below) == 1:
            child = below[0]
            radii[node] = radii[child] * (taper.factor(node, child) if taper is not None else 1.0)
        else:
            radii[node] = float(numpy.sum(radii[below] ** exponent)) ** (1.0 / exponent)
    return radii


def branch_orders(parents, kinds, radii, preset=None):
    count = len(parents)
    children = children_lists(parents)
    orders = numpy.zeros(count, dtype=numpy.int64) if preset is None else numpy.array(preset, dtype=numpy.int64)
    if preset is None or orders[0] < 0:
        orders[0] = 0
    for node in range(count):
        below = [child for child in children[node] if preset is None or preset[child] < 0]
        if not below:
            continue
        same = [child for child in below if kinds[child] == kinds[node]]
        main = max(same, key=lambda child: (radii[child], -child)) if same else None
        for child in below:
            orders[child] = orders[node] if child == main else orders[node] + 1
    return orders


def pipe_error(parents, radii, exponent):
    children = children_lists(parents)
    worst = 0.0
    branchings = 0
    for node, below in enumerate(children):
        if len(below) < 2:
            continue
        branchings += 1
        own = radii[node] ** exponent
        worst = max(worst, abs(own - float(numpy.sum(radii[below] ** exponent))) / own)
    return worst, branchings
