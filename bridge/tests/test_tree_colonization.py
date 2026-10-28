import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy

from blendworks_bridge.tree_colonize import SHOOT, Colonization, Group, Nodes
from blendworks_bridge.tree_shapes import RevolutionEnvelope
from tree_helpers import distances_to, grow_core, mean_direction, tree_of

SLACK = 1e-9
SMALL_TREE = dict(height=6.0, trunk_height=1.5, crown_radius=2.0, points=900, influence=0.9, kill=0.2, step=0.12)
SMALL_ROOTS = dict(points=500, depth=0.8, radius=1.4, influence=0.6, kill=0.18, step=0.1)
DOWNWARD = [0.0, 0.0, -0.5]


def cylinder_outside(points, bottom, top, radius):
    spread = numpy.hypot(points[:, 0], points[:, 1])
    radial = numpy.maximum(spread - radius, 0.0)
    vertical = numpy.maximum(numpy.maximum(bottom - points[:, 2], points[:, 2] - top), 0.0)
    return numpy.hypot(radial, vertical)


def box_outside(points, low, high):
    return numpy.linalg.norm(numpy.maximum(numpy.maximum(low - points, points - high), 0.0), axis=1)


def test_every_point_within_kill_distance_of_a_node_is_removed(bridge):
    skeleton, grown = grow_core(**SMALL_TREE, seed=4, roots=SMALL_ROOTS)
    for remaining, kill in zip(grown.report["remaining"], grown.report["kill"]):
        assert len(remaining) < 0.2 * SMALL_TREE["points"]
        assert numpy.all(distances_to(remaining, skeleton.positions) >= kill), distances_to(remaining, skeleton.positions).min()
    assert grown.report["points"] == [900, 500]
    assert sum(len(remaining) for remaining in grown.report["remaining"]) == sum(grown.report["remaining_points"])


def test_no_crown_node_lies_outside_the_envelope_by_more_than_one_step(bridge):
    for shape_tropism in ([0.5, 0.0, -0.3], [0.0, 0.0, 0.0]):
        result = bridge.ok("grow_tree", name="Tree", envelope="cylindrical", tropism=shape_tropism, seed=2, **SMALL_TREE)
        tree = tree_of("Tree")
        crown = tree.positions[result["growth"]["trunk_nodes"]:][tree.kinds[result["growth"]["trunk_nodes"]:] == SHOOT]
        assert len(crown) > 200
        outside = cylinder_outside(crown, SMALL_TREE["trunk_height"], SMALL_TREE["height"], SMALL_TREE["crown_radius"])
        assert outside.max() <= SMALL_TREE["step"] + SLACK, outside.max()
        if shape_tropism[0]:
            assert outside.max() > 0.5 * SMALL_TREE["step"]
        bridge.ok("delete", names=["Tree"])


def test_a_mesh_envelope_bounds_the_crown_and_its_face_order_changes_nothing(bridge):
    low = numpy.array([-1.5, -1.0, 2.0])
    high = numpy.array([2.5, 1.0, 5.0])
    corners = [[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]
    faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    bridge.ok("mesh_from_data", name="Box", vertices=corners, faces=faces)
    bridge.ok("mesh_from_data", name="Shuffled", vertices=corners[::-1], faces=[[7 - index for index in face] for face in faces[::-1]])
    first = bridge.ok("grow_tree", name="Tree", envelope="Box", points=800, influence=0.9, kill=0.2, step=0.12, trunk_height=1.0, tropism=[0.6, 0.0, 0.0], seed=9, limit=0)
    tree = tree_of("Tree")
    crown = tree.positions[first["growth"]["trunk_nodes"]:]
    assert len(crown) > 150
    assert box_outside(crown, low, high).max() <= 0.12 + SLACK
    bridge.ok("grow_tree", name="Again", envelope="Shuffled", points=800, influence=0.9, kill=0.2, step=0.12, trunk_height=1.0, tropism=[0.6, 0.0, 0.0], seed=9, limit=0)
    assert numpy.array_equal(tree_of("Again").positions, tree.positions)
    assert numpy.array_equal(tree_of("Again").radii, tree.radii)


def test_downward_tropism_tilts_the_mean_branch_direction_down(bridge):
    level = bridge.ok("grow_tree", name="Level", seed=6, **SMALL_TREE)
    bent = bridge.ok("grow_tree", name="Bent", seed=6, tropism=DOWNWARD, **SMALL_TREE)
    level_mean = mean_direction(tree_of("Level"), level["growth"]["trunk_nodes"])
    bent_mean = mean_direction(tree_of("Bent"), bent["growth"]["trunk_nodes"])
    assert bent_mean[2] < level_mean[2] - 0.1, (level_mean, bent_mean)


def test_the_seed_repeats_and_the_point_order_changes_nothing(bridge):
    first = grow_core(**SMALL_TREE, seed=12, roots=SMALL_ROOTS)[0]
    again = grow_core(**SMALL_TREE, seed=12, roots=SMALL_ROOTS)[0]
    other = grow_core(**SMALL_TREE, seed=13, roots=SMALL_ROOTS)[0]
    for name in ("positions", "parents", "radii", "orders", "kinds"):
        assert numpy.array_equal(getattr(first, name), getattr(again, name)), name
    assert first.count != other.count or not numpy.array_equal(first.positions, other.positions)
    envelope = RevolutionEnvelope("spherical", 1.0, 4.0, 1.5)
    points = envelope.sample(numpy.random.default_rng(3), 700)
    shuffled = points[numpy.random.default_rng(8).permutation(len(points))]
    results = []
    for cloud in (points, shuffled, points[::-1]):
        nodes = Nodes(5000)
        nodes.add(numpy.zeros(3), -1, SHOOT)
        nodes.add(numpy.array([0.0, 0.0, 1.0]), 0, SHOOT)
        Colonization(nodes, [Group(SHOOT, cloud, envelope, 0.8, 0.15, 0.1, [0.0, 0.0, 0.1])], 0.0).run()
        results.append(nodes.view())
    assert results[0][0].shape[0] > 100
    for other_result in results[1:]:
        assert numpy.array_equal(other_result[0], results[0][0]) and numpy.array_equal(other_result[1], results[0][1])


def test_growth_stops_at_max_nodes_and_says_so(bridge):
    result = bridge.ok("grow_tree", name="Tree", max_nodes=300, seed=1, **SMALL_TREE)
    assert result["nodes"] == 300 and result["growth"]["stopped"] == "max_nodes"
    assert len(tree_of("Tree").parents) == 300


run(globals())
