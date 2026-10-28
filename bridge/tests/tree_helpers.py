import math

import bpy
import numpy

from blendworks_bridge.commands import load
from blendworks_bridge.registry import COMMANDS
from blendworks_bridge.schema import validate
from blendworks_bridge.tree_plan import grow
from blendworks_bridge.tree_skeleton import PROPERTY


class Tree:
    def __init__(self, data):
        self.data = data
        self.positions = numpy.array(data["position"], dtype=float).reshape(-1, 3)
        self.parents = numpy.array(data["parent"], dtype=numpy.int64)
        self.radii = numpy.array(data["radius"], dtype=float)
        self.orders = numpy.array(data["order"], dtype=numpy.int64)
        self.kinds = numpy.array(data["kind"], dtype=numpy.int64)
        self.children = [[] for _ in range(len(self.parents))]
        for node in range(1, len(self.parents)):
            self.children[self.parents[node]].append(node)

    def branchings(self):
        return [node for node, below in enumerate(self.children) if len(below) >= 2]

    def stem_from(self, first):
        nodes = [first]
        while True:
            same = [child for child in self.children[nodes[-1]] if self.orders[child] == self.orders[first]]
            if not same:
                return nodes
            nodes.append(same[0])

    def arc_length(self, nodes):
        points = numpy.vstack([self.positions[self.parents[nodes[0]]], self.positions[nodes]])
        return float(numpy.linalg.norm(numpy.diff(points, axis=0), axis=1).sum())

    def laterals(self, stem):
        found = []
        for node in stem:
            for child in self.children[node]:
                if self.orders[child] == self.orders[stem[0]] + 1 and self.kinds[child] == 0:
                    found.append(child)
        return found


def plain(value):
    if hasattr(value, "to_dict"):
        return {key: plain(item) for key, item in value.to_dict().items()}
    if hasattr(value, "to_list"):
        return value.to_list()
    return value


def tree_of(name):
    return Tree(plain(bpy.data.objects[name][PROPERTY]))


class Context:
    def depsgraph(self):
        bpy.context.view_layer.update()
        return bpy.context.evaluated_depsgraph_get()


def grow_core(**args):
    load()
    checked = validate(COMMANDS["grow_tree"].schema, args)
    return grow(Context(), checked, numpy.array(checked["location"], dtype=float))


def distances_to(points, nodes):
    gaps = numpy.sqrt(((points[:, None, :] - nodes[None, :, :]) ** 2).sum(axis=2))
    return gaps.min(axis=1) if len(nodes) else numpy.full(len(points), math.inf)


def signed_turn(first, second, axis):
    return math.degrees(math.atan2(float(numpy.dot(numpy.cross(first, second), axis)), float(numpy.dot(first, second))))


def flat(vector, axis):
    projected = vector - numpy.dot(vector, axis) * axis
    return projected / numpy.linalg.norm(projected)


def mean_direction(tree, first):
    segments = tree.positions[first:] - tree.positions[tree.parents[first:]]
    shoots = tree.kinds[first:] == 0
    units = segments[shoots] / numpy.linalg.norm(segments[shoots], axis=1)[:, None]
    return units.mean(axis=0)
