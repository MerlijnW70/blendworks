import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy

from blendworks_bridge.tree_presets import PRESETS
from blendworks_bridge.tree_skeleton import check_tree
from tree_helpers import tree_of
from tree_shape_helpers import angle_between, grown_tree, segment, stem_starts

CURVED = dict(method="levels", envelope="cylindrical", height=10.0, trunk_height=2.0, levels=2, branches=[8], down_angle=[70.0], rotate=[137.5], length_ratio=[0.5], segments=[20, 30], tip_radius=0.02)
PIPE_LIMIT = 1e-6
SPREAD_TOLERANCE = 0.15


def signed_turns(tree, stem):
    first = numpy.cross(segment(tree, stem[0]), segment(tree, stem[1]))
    axis = first / numpy.linalg.norm(first)
    turns = []
    for previous, node in zip(stem, stem[1:]):
        before, after = segment(tree, previous), segment(tree, node)
        turns.append(math.degrees(math.atan2(float(numpy.dot(numpy.cross(before, after), axis)), float(numpy.dot(before, after)))))
    return turns


def arcs(tree, stem):
    lengths = [float(numpy.linalg.norm(tree.positions[node] - tree.positions[tree.parents[node]])) for node in stem]
    return numpy.cumsum(lengths), numpy.array(lengths)


def test_curve_back_bends_the_second_half_of_a_stem_the_other_way(bridge):
    tree, _ = grown_tree(**CURVED, curve=[0.0, 40.0], curve_back=[0.0, -60.0])
    checked = 0
    for first in stem_starts(tree):
        stem = tree.stem_from(first)
        ends, lengths = arcs(tree, stem)
        length = ends[-1]
        turns = signed_turns(tree, stem)
        early = [turn for turn, start, end in zip(turns, ends[:-1], ends[1:]) if end <= 0.5 * length]
        late = [turn for turn, start, end in zip(turns, ends[:-1], ends[1:]) if start >= 0.5 * length]
        assert early and late
        assert min(early) > 0.0 and max(late) < 0.0, (early, late)
        for turn, start, end in zip(turns, ends[:-1], ends[1:]):
            step = end - start
            expected = 2.0 * 40.0 * step / length if end <= 0.5 * length else 2.0 * -60.0 * step / length if start >= 0.5 * length else None
            if expected is not None:
                assert abs(turn - expected) < 1e-6, (turn, expected)
        checked += 1
    assert checked >= 6
    plain, _ = grown_tree(**CURVED, curve=[0.0, 40.0])
    for first in stem_starts(plain):
        assert min(signed_turns(plain, plain.stem_from(first))) > 0.0


def test_curve_variation_repeats_for_a_seed_and_spreads_as_asked(bridge):
    shares = []
    for seed in (1, 2, 3):
        tree, _ = grown_tree(**CURVED, curve=[0.0, 0.0], curve_variation=[0.0, 30.0], seed=seed)
        again, _ = grown_tree(**CURVED, curve=[0.0, 0.0], curve_variation=[0.0, 30.0], seed=seed)
        assert numpy.array_equal(tree.positions, again.positions)
        for first in stem_starts(tree):
            stem = tree.stem_from(first)
            ends, lengths = arcs(tree, stem)
            turns = numpy.radians(numpy.abs(signed_turns(tree, stem)))
            shares.extend(turns / (math.radians(30.0) * lengths[1:] / ends[-1]))
    shares = numpy.array(shares)
    assert len(shares) > 500
    assert shares.max() <= 1.0 + 1e-9, shares.max()
    assert abs(math.sqrt(numpy.mean(shares**2)) - 1.0 / math.sqrt(3.0)) < SPREAD_TOLERANCE / math.sqrt(3.0), math.sqrt(numpy.mean(shares**2))
    other, _ = grown_tree(**CURVED, curve=[0.0, 0.0], curve_variation=[0.0, 30.0], seed=4)
    assert not numpy.allclose(other.positions, tree.positions)
    straight, _ = grown_tree(**CURVED, curve=[0.0, 0.0])
    for first in stem_starts(straight):
        stem = straight.stem_from(first)
        assert max(angle_between(segment(straight, previous), segment(straight, node)) for previous, node in zip(stem, stem[1:])) < 1e-9


def test_every_preset_keeps_the_pipe_model_and_a_valid_skeleton(bridge):
    for name in PRESETS:
        result = bridge.ok("grow_tree", name=f"Tree_{name}", preset=name, seed=2, limit=0)
        assert result["preset"] == name and result["version"] == 1
        assert result["pipe_error"] < PIPE_LIMIT, (name, result["pipe_error"])
        tree = tree_of(f"Tree_{name}")
        check_tree(tree.parents)
        shoots = tree.kinds == 0
        assert numpy.all(tree.positions[shoots][1:, 2] > tree.positions[0, 2]), name
        assert result["nodes"] > 1000, (name, result["nodes"])
        if name != "default":
            assert "form" in result["growth"], name


def test_the_presets_have_their_forms(bridge):
    willow, _ = grown_tree(preset="weeping_willow")
    tips = [node for node, below in enumerate(willow.children) if not below and willow.orders[node] >= 2]
    assert numpy.mean([segment(willow, tip)[2] for tip in tips]) < -0.7
    oak, oak_grown = grown_tree(preset="gnarled_oak")
    assert oak_grown.report["form"]["kinks"] > 50 and oak_grown.report["form"]["largest_gnarl"] > 0.2
    coastal, coastal_grown = grown_tree(preset="windswept_coastal")
    crown = coastal.positions[coastal_grown.trunk_nodes:][coastal.kinds[coastal_grown.trunk_nodes:] == 0]
    assert crown[:, 0].mean() > 1.0
    default, _ = grown_tree(preset="default")
    plain, _ = grown_tree()
    assert numpy.array_equal(default.positions, plain.positions)


def test_given_fields_replace_the_preset_and_objects_merge(bridge):
    hanging = lambda tree: numpy.mean([segment(tree, node)[2] for node, below in enumerate(tree.children) if not below and tree.orders[node] >= 2])
    merged, _ = grown_tree(preset="weeping_willow", height=6.0, gravitropism={"thinness": 1.0})
    assert abs(merged.positions[merged.stem_from(0)][:, 2].max() - 6.0) < 0.5
    assert hanging(merged) < -0.5
    replaced, _ = grown_tree(preset="weeping_willow", gravitropism={"strength": 0.0})
    assert hanging(replaced) > 0.0
    message = bridge.refuse("grow_tree", "bad_args", name="Tree", preset="weeping_willow", method="colonization")
    assert "weeping_willow" in message and "levels" in message, message
    message = bridge.refuse("grow_tree", "bad_args", name="Tree", preset="gnarled_oak", curve_back=[10.0])
    assert "curve_back" in message and "other method" in message, message


def test_shoots_bent_into_the_ground_are_cut_and_the_radii_rebuilt(bridge):
    tree, grown = grown_tree(**dict(CURVED, down_angle=[100.0]), curve=[0.0, 0.0], gravitropism={"strength": 2.0, "by_order": [0.0, 1.0]})
    assert grown.report["form"]["pruned"] > 0
    shoots = numpy.flatnonzero(tree.kinds == 0)[1:]
    assert numpy.all(tree.positions[shoots, 2] > 0.0)
    check_tree(tree.parents)
    children = [[] for _ in tree.parents]
    for node in range(1, len(tree.parents)):
        children[tree.parents[node]].append(node)
    for node, below in enumerate(children):
        if len(below) >= 2:
            assert abs(tree.radii[node] ** 2 - float(numpy.sum(tree.radii[below] ** 2))) <= 1e-9 * tree.radii[node] ** 2


run(globals())
