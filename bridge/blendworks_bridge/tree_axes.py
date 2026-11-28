"""Tree axes and twigs built from a skeleton."""

import numpy

from .errors import bad_args
from .tree_radii import children_lists
from .tree_skeleton import chains

TIP = "tip"
CUT = "cut"
MERGE_SHARE = 0.25
MAX_TURN = numpy.cos(numpy.radians(75.0))


class Axis:
    def __init__(self, index, nodes, lateral, kind, end):
        self.index = index
        self.nodes = nodes
        self.lateral = lateral
        self.kind = kind
        self.end = end
        self.parent = -1

    @property
    def own(self):
        return self.nodes[1:] if self.lateral else self.nodes


class Twig:
    def __init__(self, nodes):
        self.nodes = nodes


def kept_nodes(skeleton, cut):
    kept = numpy.zeros(skeleton.count, dtype=bool)
    kept[0] = True
    for node in range(1, skeleton.count):
        kept[node] = kept[skeleton.parents[node]] and skeleton.radii[node] >= cut
    return kept


def distinct(skeleton, nodes):
    chosen = [nodes[0]]
    for node in nodes[1:-1]:
        gap = numpy.linalg.norm(skeleton.positions[node] - skeleton.positions[chosen[-1]])
        if gap >= MERGE_SHARE * skeleton.radii[node]:
            chosen.append(node)
    if len(nodes) > 1:
        last = nodes[-1]
        if len(chosen) > 1 and numpy.linalg.norm(skeleton.positions[last] - skeleton.positions[chosen[-1]]) < MERGE_SHARE * skeleton.radii[last]:
            chosen[-1] = last
        else:
            chosen.append(last)
    return chosen


def split_at_turns(skeleton, nodes):
    points = skeleton.positions[nodes]
    steps = numpy.diff(points, axis=0)
    steps /= numpy.maximum(numpy.linalg.norm(steps, axis=1, keepdims=True), 1e-12)
    turns = numpy.flatnonzero(numpy.einsum("ij,ij->i", steps[:-1], steps[1:]) < MAX_TURN) + 1
    pieces = []
    start = 0
    for turn in turns:
        pieces.append(nodes[start : turn + 1])
        start = turn
    pieces.append(nodes[start:])
    return [piece for piece in pieces if len(piece) >= 2]


def build_axes(skeleton, cut):
    kept = kept_nodes(skeleton, cut)
    axes = []
    twigs = []
    node_axis = numpy.full(skeleton.count, -1, dtype=numpy.int64)
    for chain, branched in chains(skeleton):
        own = chain[1:] if branched else chain
        length = 0
        while length < len(own) and kept[own[length]]:
            length += 1
        if length < len(own):
            anchor = [own[length - 1]] if length else chain[:1] if branched else []
            twigs.append(Twig(anchor + own[length:]))
        if length == 0:
            continue
        nodes = ([chain[0]] if branched else []) + own[:length]
        if len(nodes) < 2:
            continue
        pieces = split_at_turns(skeleton, distinct(skeleton, nodes))
        for number, piece in enumerate(pieces):
            last = number == len(pieces) - 1
            axis = Axis(len(axes), piece, branched or number > 0, int(skeleton.kinds[own[0]]), CUT if last and length < len(own) else TIP)
            axes.append(axis)
            node_axis[piece[1:] if axis.lateral else piece] = axis.index
        node_axis[own[:length]] = numpy.where(node_axis[own[:length]] < 0, axes[-1].index, node_axis[own[:length]])
    if not axes or axes[0].lateral:
        raise bad_args("min_radius drops the whole trunk; give a smaller min_radius")
    for axis in axes:
        if axis.lateral:
            axis.parent = int(node_axis[axis.nodes[0]])
    return axes, [twig for twig in twigs if len(twig.nodes) >= 2], node_axis


def heights_from_tips(skeleton):
    children = children_lists(skeleton.parents)
    found = chains(skeleton)
    node_chain = numpy.full(skeleton.count, -1, dtype=numpy.int64)
    for index, (chain, branched) in enumerate(found):
        node_chain[chain[1:] if branched else chain] = index
    height = numpy.ones(len(found), dtype=numpy.int64)
    for index in sorted(range(len(found)), key=lambda index: -found[index][0][1 if found[index][1] else 0]):
        chain, branched = found[index]
        for node in chain[1:] if branched else chain:
            for child in children[node]:
                other = node_chain[child]
                if other != index:
                    height[index] = max(height[index], height[other] + 1)
    return found, node_chain, height
