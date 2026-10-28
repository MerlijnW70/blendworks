import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy

from tree_helpers import flat, signed_turn, tree_of

ANGLE_SLACK = 1e-9
LENGTH_SLACK = 1e-9
LEVELS = dict(method="levels", envelope="conical", height=10.0, trunk_height=2.0, levels=3, branches=[12, 6], down_angle=[60.0, 45.0], rotate=[137.5, -100.0], length_ratio=[0.4, 0.5], curve=[0.0, 0.0, 0.0], segments=[20, 6, 3])


def wrapped(angle):
    return (angle + 180.0) % 360.0 - 180.0


def unit(vector):
    return vector / numpy.linalg.norm(vector)


def turns(tree, stem, axis):
    laterals = tree.laterals(stem)
    directions = [flat(tree.positions[child] - tree.positions[tree.parents[child]], axis) for child in laterals]
    return [signed_turn(first, second, axis) for first, second in zip(directions, directions[1:])]


def offset_along(tree, stem, node):
    path = stem[: stem.index(node) + 1]
    return tree.arc_length(path)


def test_consecutive_children_turn_by_rotate_at_every_level(bridge):
    bridge.ok("grow_tree", name="Tree", **LEVELS)
    tree = tree_of("Tree")
    trunk = tree.stem_from(0)
    trunk_turns = turns(tree, trunk, numpy.array([0.0, 0.0, 1.0]))
    assert len(trunk_turns) == 11
    assert max(abs(wrapped(turn - 137.5)) for turn in trunk_turns) < ANGLE_SLACK, trunk_turns
    checked = 0
    for first in tree.laterals(trunk):
        stem = tree.stem_from(first)
        axis = unit(tree.positions[first] - tree.positions[tree.parents[first]])
        for turn in turns(tree, stem, axis):
            assert abs(wrapped(turn + 100.0)) < ANGLE_SLACK, turn
            checked += 1
    assert checked > 30


def test_child_lengths_follow_length_ratio(bridge):
    bridge.ok("grow_tree", name="Tree", **LEVELS)
    tree = tree_of("Tree")
    trunk_length, base = LEVELS["height"], LEVELS["trunk_height"]
    trunk = tree.stem_from(0)
    deeper = 0
    for first in tree.laterals(trunk):
        offset = tree.positions[tree.parents[first]][2]
        stem = tree.stem_from(first)
        length = tree.arc_length(stem)
        expected = trunk_length * 0.4 * (0.2 + 0.8 * (trunk_length - offset) / (trunk_length - base))
        assert abs(length - expected) < LENGTH_SLACK, (length, expected)
        for child in tree.laterals(stem):
            along = tree.arc_length(stem[: stem.index(tree.parents[child]) + 1])
            child_length = tree.arc_length(tree.stem_from(child))
            assert abs(child_length - 0.5 * (length - 0.6 * along)) < LENGTH_SLACK, (child_length, length, along)
            deeper += 1
    assert deeper > 30


def test_tips_follow_ratio_power_and_unbranched_runs_follow_taper(bridge):
    bridge.ok("grow_tree", name="Tree", tip_radius=0.02, taper=0.5, ratio_power=1.5, **LEVELS)
    tree = tree_of("Tree")
    starts = [0] + [node for node in range(1, len(tree.parents)) if tree.orders[node] != tree.orders[tree.parents[node]]]
    stem_of = {}
    arc = {}
    lengths = {}
    for first in starts:
        stem = tree.stem_from(first)
        travelled = 0.0
        for node in stem:
            if node:
                travelled += float(numpy.linalg.norm(tree.positions[node] - tree.positions[tree.parents[node]]))
            stem_of[node] = first
            arc[node] = travelled
        lengths[first] = travelled
    tips = [node for node, below in enumerate(tree.children) if not below]
    for tip in tips:
        expected = 0.02 * (lengths[stem_of[tip]] / LEVELS["height"]) ** 1.5
        assert abs(tree.radii[tip] - expected) <= 1e-12 + 1e-9 * expected, (tip, tree.radii[tip], expected)
    runs = 0
    for node, below in enumerate(tree.children):
        if len(below) == 1 and stem_of.get(below[0]) == stem_of[node]:
            length = lengths[stem_of[node]]
            expected = (1.0 - 0.5 * arc[node] / length) / (1.0 - 0.5 * arc[below[0]] / length)
            assert abs(tree.radii[node] / tree.radii[below[0]] - expected) < 1e-9, node
            runs += 1
    assert runs > 100


def test_a_levels_tree_too_big_for_max_nodes_is_refused_before_growth(bridge):
    message = bridge.refuse("grow_tree", "bad_args", name="Tree", method="levels", levels=4, branches=[200], max_nodes=50_000)
    assert "may need" in message and "max_nodes 50000" in message, message
    message = bridge.refuse("grow_tree", "bad_args", name="Tree", method="levels", points=10)
    assert "points" in message and "other method" in message, message
    message = bridge.refuse("grow_tree", "bad_args", name="Tree", method="levels", envelope="Missing")
    assert "built-in crown shape" in message, message
    assert "Tree" not in [entry["name"] for entry in bridge.ok("scene_info")["objects"]]


run(globals())
