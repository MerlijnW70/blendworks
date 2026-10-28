import math

import numpy

from tree_helpers import Tree, grow_core

FORM_LEVELS = dict(method="levels", envelope="conical", height=10.0, trunk_height=2.0, levels=3, branches=[12, 6], down_angle=[60.0, 45.0], rotate=[137.5], length_ratio=[0.5, 0.6], curve=[0.0, 0.0, 0.0], segments=[20, 8, 4], tip_radius=0.02)
LIMBS = dict(method="levels", envelope="cylindrical", height=10.0, trunk_height=2.0, levels=2, branches=[10], down_angle=[50.0], rotate=[137.5], length_ratio=[0.5], curve=[0.0, 0.0], segments=[20, 12], tip_radius=0.02)
SMALL_CROWN = dict(height=6.0, trunk_height=2.0, crown_radius=2.0, points=900, influence=0.9, kill=0.2, step=0.12, tip_radius=0.01)


def grown_tree(**args):
    skeleton, grown = grow_core(**args)
    return Tree(skeleton.to_property()), grown


def unit(vector):
    return vector / numpy.linalg.norm(vector)


def segment(tree, node):
    return unit(tree.positions[node] - tree.positions[tree.parents[node]])


def angle_between(first, second):
    return math.atan2(float(numpy.linalg.norm(numpy.cross(first, second))), float(numpy.dot(first, second)))


def stem_starts(tree):
    return [node for node in range(1, len(tree.parents)) if tree.orders[node] != tree.orders[tree.parents[node]] and tree.kinds[node] == 0]


def tips_of_order(tree, lowest):
    return [node for node, below in enumerate(tree.children) if not below and node and tree.kinds[node] == 0 and tree.orders[node] >= lowest]


def mean_tip_direction(tree, lowest):
    tips = tips_of_order(tree, lowest)
    return unit(numpy.mean([segment(tree, tip) for tip in tips], axis=0)), len(tips)


def lean_profile(tree, nodes):
    return [math.degrees(angle_between(segment(tree, node), numpy.array([0.0, 0.0, 1.0]))) for node in nodes]


def bend_turns(tree, stem):
    return [angle_between(segment(tree, first), segment(tree, second)) for first, second in zip(stem, stem[1:])]


def expected_pull(tree, node, previous, target, rate):
    sine = float(numpy.linalg.norm(numpy.cross(previous, target)))
    length = float(numpy.linalg.norm(tree.positions[node] - tree.positions[tree.parents[node]]))
    return min(rate * length * sine, angle_between(previous, target))
