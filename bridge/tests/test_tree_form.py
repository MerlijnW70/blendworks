import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy

from blendworks_bridge.tree_skeleton import check_tree
from tree_shape_helpers import FORM_LEVELS, LIMBS, SMALL_CROWN, angle_between, expected_pull, grown_tree, lean_profile, mean_tip_direction, segment, stem_starts, tips_of_order, unit

DOWN = numpy.array([0.0, 0.0, -1.0])
UP = numpy.array([0.0, 0.0, 1.0])
TURN_SLACK = 1e-9
TRUNK_TOP_LIMIT = 5.0


def limb_turns_follow(tree, target, rate_of):
    checked = 0
    for first in stem_starts(tree):
        stem = tree.stem_from(first)
        for previous, node in zip(stem, stem[1:]):
            heading = segment(tree, previous)
            measured = angle_between(heading, segment(tree, node))
            expected = expected_pull(tree, node, heading, target, rate_of(node))
            assert abs(measured - expected) < TURN_SLACK, (node, measured, expected)
            checked += 1
    return checked


def test_gravitropism_bends_each_segment_by_strength_order_weight_and_thinness(bridge):
    for thinness in (0.0, 1.5):
        tree, _ = grown_tree(**LIMBS, gravitropism={"strength": 0.4, "by_order": [0.0, 0.7], "thinness": thinness})
        rate = lambda node: 0.4 * 0.7 * (LIMBS["tip_radius"] / tree.radii[node]) ** thinness
        assert limb_turns_follow(tree, DOWN, rate) > 80
        trunk = tree.stem_from(0)
        assert max(lean_profile(tree, trunk[1:])) < 1e-9


def test_weeping_comes_from_order_and_thinness_while_the_trunk_stays_up(bridge):
    weeping = dict(FORM_LEVELS, gravitropism={"strength": 3.0, "by_order": [0.0, 0.0, 1.0], "thinness": 1.0})
    tree, _ = grown_tree(**weeping)
    direction, count = mean_tip_direction(tree, 2)
    assert count > 30
    assert direction[2] < -0.5, direction
    limbs = [tree.stem_from(first)[-1] for first in stem_starts(tree) if tree.orders[first] == 1]
    assert numpy.mean([segment(tree, end)[2] for end in limbs]) > 0.4
    trunk = tree.stem_from(0)
    assert lean_profile(tree, [trunk[-1]])[0] < TRUNK_TOP_LIMIT
    upright, _ = grown_tree(**dict(weeping, gravitropism={"strength": 3.0, "by_order": [0.0], "thinness": 1.0}))
    direction, _ = mean_tip_direction(upright, 2)
    assert direction[2] > 0.3, direction


def test_phototropism_turns_shoots_towards_the_light(bridge):
    light = numpy.array([1.0, 0.0, 0.2])
    tree, _ = grown_tree(**LIMBS, phototropism={"direction": light.tolist(), "strength": 0.3, "by_order": [0.0, 1.0], "thinness": 1.0})
    rate = lambda node: 0.3 * (LIMBS["tip_radius"] / tree.radii[node])
    assert limb_turns_follow(tree, unit(light), rate) > 80
    plain, _ = grown_tree(**LIMBS)
    lit, _ = mean_tip_direction(tree, 1)
    unlit, _ = mean_tip_direction(plain, 1)
    assert numpy.dot(lit, unit(light)) > numpy.dot(unlit, unit(light)) + 0.3


def cantilever_curvature(plain, stem, index, stiffness):
    beyond = stem[index:]
    starts = plain.positions[plain.parents[beyond]]
    ends = plain.positions[beyond]
    weights = plain.radii[beyond] ** 2 * numpy.linalg.norm(ends - starts, axis=1)
    centre = (weights[:, None] * 0.5 * (starts + ends)).sum(axis=0) / weights.sum()
    arm = float(numpy.hypot(*(centre - starts[0])[:2]))
    return 4.0 * weights.sum() * arm / (stiffness * plain.radii[stem[index]] ** 4)


def test_stiffness_sags_each_limb_by_its_cantilever_load(bridge):
    plain, _ = grown_tree(**LIMBS)
    sagged, _ = grown_tree(**LIMBS, stiffness=2e5)
    checked = 0
    for first in stem_starts(plain):
        stem = plain.stem_from(first)
        for index in range(1, len(stem)):
            heading = segment(sagged, stem[index - 1])
            length = float(numpy.linalg.norm(plain.positions[stem[index]] - plain.positions[stem[index - 1]]))
            expected = min(cantilever_curvature(plain, stem, index, 2e5) * length, angle_between(heading, DOWN))
            assert abs(angle_between(heading, segment(sagged, stem[index])) - expected) < TURN_SLACK, (stem[index], expected)
            checked += 1
    assert checked > 80
    assert numpy.allclose(sagged.positions[sagged.stem_from(0)], plain.positions[plain.stem_from(0)], atol=1e-9)


def test_lower_stiffness_sags_more(bridge):
    heights = []
    curvatures = []
    for stiffness in (None, 1e6, 2.5e5):
        tree, grown = grown_tree(**(dict(FORM_LEVELS) if stiffness is None else dict(FORM_LEVELS, stiffness=stiffness)))
        heights.append(float(tree.positions[tips_of_order(tree, 1)][:, 2].mean()))
        curvatures.append(grown.report.get("form", {}).get("largest_sag_curvature"))
    assert heights[0] > heights[1] + 0.05 > heights[2] + 0.2, heights
    assert abs(curvatures[2] / curvatures[1] - 4.0) < 1e-3, curvatures


def lean_grows(lean, least):
    steps = numpy.diff(lean)
    return bool(numpy.all(steps >= -1e-9) and lean[-1] - lean[0] > least)


def test_wind_bends_the_trunk_more_with_height_and_streams_the_crown_downwind(bridge):
    wind = {"vector": [1.2, 0.0, 0.0], "profile": 0.3, "thinness": 1.0}
    levels, _ = grown_tree(**FORM_LEVELS, wind=wind)
    trunk = levels.stem_from(0)[1:]
    lean = lean_profile(levels, trunk)
    assert lean_grows(lean, 10.0), lean
    for node in trunk[1:]:
        heading = segment(levels, levels.parents[node])
        height = levels.positions[levels.parents[node]][2] / FORM_LEVELS["height"]
        rate = 1.2 * max(height, 0.0) ** 0.3 * (FORM_LEVELS["tip_radius"] / levels.radii[node])
        assert abs(angle_between(heading, segment(levels, node)) - expected_pull(levels, node, heading, numpy.array([1.0, 0.0, 0.0]), rate)) < TURN_SLACK
    calm, _ = grown_tree(**SMALL_CROWN, seed=5)
    blown, grown = grown_tree(**SMALL_CROWN, seed=5, wind=wind)
    shift = blown.positions[blown.kinds == 0][:, 0].mean() - calm.positions[calm.kinds == 0][:, 0].mean()
    assert shift > 0.5, shift
    assert lean_grows(lean_profile(blown, list(range(1, grown.trunk_nodes))), 2.0)
    leaning, lean_report = grown_tree(**SMALL_CROWN, seed=5, tropism=[0.5, 0.0, 0.0])
    uniform = lean_profile(leaning, list(range(1, lean_report.trunk_nodes)))
    assert uniform[0] > 20.0
    assert not lean_grows(uniform, 2.0), uniform
    assert max(uniform) - min(uniform) < 1e-6, uniform


def test_gnarl_moves_trunk_nodes_sideways_within_the_amplitude(bridge):
    gnarl = {"amplitude": 0.3, "wavelength": 1.5, "radius_power": 1.0, "by_order": [1.0, 0.5]}
    plain, _ = grown_tree(**FORM_LEVELS, seed=4)
    gnarled, grown = grown_tree(**FORM_LEVELS, seed=4, gnarl=gnarl)
    check_tree(gnarled.parents)
    trunk = plain.stem_from(0)
    assert gnarled.stem_from(0) == trunk
    moved = gnarled.positions[trunk] - plain.positions[trunk]
    sizes = numpy.linalg.norm(moved, axis=1)
    bounds = 0.3 * gnarled.radii[trunk] / gnarled.radii[0]
    assert numpy.all(sizes <= bounds + 1e-12), (sizes - bounds).max()
    assert sizes.max() <= 0.3
    assert sizes.max() > 0.1 and grown.report["form"]["largest_gnarl"] > 0.1
    assert numpy.abs(moved[:, 2]).max() < 1e-9


def test_twist_turns_successive_laterals_by_the_rate_in_both_methods(bridge):
    rotate = FORM_LEVELS["rotate"][0]
    twisted, _ = grown_tree(**FORM_LEVELS, twist=25.0)
    trunk = twisted.stem_from(0)
    laterals = twisted.laterals(trunk)
    for first, second in zip(laterals, laterals[1:]):
        heights = twisted.positions[twisted.parents[[first, second]]][:, 2]
        flat = [unit(segment(twisted, node) * numpy.array([1.0, 1.0, 0.0])) for node in (first, second)]
        turn = math.degrees(math.atan2(numpy.cross(flat[0], flat[1])[2], numpy.dot(flat[0], flat[1])))
        expected = rotate + 25.0 * (heights[1] - heights[0])
        assert abs((turn - expected + 180.0) % 360.0 - 180.0) < 1e-6, (turn, expected)
    plain, report = grown_tree(**SMALL_CROWN, seed=2)
    rolled, _ = grown_tree(**SMALL_CROWN, seed=2, twist=-40.0)
    checked = 0
    for node in range(1, len(plain.parents)):
        parent = plain.parents[node]
        if plain.orders[node] == 1 and plain.orders[parent] == 0 and parent < report.trunk_nodes:
            before = unit(segment(plain, node) * numpy.array([1.0, 1.0, 0.0]))
            after = unit(segment(rolled, node) * numpy.array([1.0, 1.0, 0.0]))
            turn = math.degrees(math.atan2(numpy.cross(before, after)[2], numpy.dot(before, after)))
            assert abs(turn + 40.0 * plain.positions[parent][2]) < 1e-6, (node, turn)
            checked += 1
    assert checked >= 1


def test_kinks_turn_a_straight_trunk_by_the_kink_angle_at_seeded_nodes(bridge):
    kinked, grown = grown_tree(**FORM_LEVELS, seed=9, kink_probability=0.3, kink_angle=20.0)
    trunk = kinked.stem_from(0)
    turns = [math.degrees(angle_between(segment(kinked, first), segment(kinked, second))) for first, second in zip(trunk[1:], trunk[2:])]
    sharp = [turn for turn in turns if turn > 1e-6]
    assert all(abs(turn - 20.0) < 1e-6 for turn in sharp), sharp
    assert 0.1 * len(turns) < len(sharp) < 0.5 * len(turns)
    shoots = int((kinked.kinds == 0).sum()) - 1 - len(kinked.children[0])
    assert abs(grown.report["form"]["kinks"] - 0.3 * shoots) < 4.0 * math.sqrt(0.3 * 0.7 * shoots)


def test_every_new_setting_is_deterministic_for_a_seed(bridge):
    settings = [
        dict(FORM_LEVELS, curve_variation=[10.0, 30.0]),
        dict(FORM_LEVELS, gnarl={"amplitude": 0.2}),
        dict(FORM_LEVELS, kink_probability=0.2),
        dict(SMALL_CROWN, gnarl={"amplitude": 0.2}, kink_probability=0.1, twist=10.0, wind={"vector": [0.5, 0.0, 0.0]}, gravitropism={"strength": 1.0}, phototropism={"direction": [0.0, 1.0, 0.0], "strength": 0.5}, stiffness=1e6),
    ]
    for args in settings:
        first, _ = grown_tree(**args, seed=3)
        again, _ = grown_tree(**args, seed=3)
        other, _ = grown_tree(**args, seed=4)
        assert numpy.array_equal(first.positions, again.positions) and numpy.array_equal(first.radii, again.radii)
        assert first.positions.shape != other.positions.shape or not numpy.allclose(first.positions, other.positions)


run(globals())
