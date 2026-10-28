import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from blendworks_bridge.gltf_extras import read_glb
from blendworks_bridge.kit_limits import MAX_INSTANCES
from blendworks_bridge.tree_skeleton import PROPERTY
from tree_helpers import plain
from tree_mesh_helpers import LEVELS, SMALL, SMALL_ROOTS, Skeleton, segment_distances

ANGLE_SLACK = 0.5


def grow(bridge, name="Grown", levels=False, **extra):
    settings = dict(LEVELS if levels else SMALL, **extra)
    return bridge.ok("grow_tree", name=name, roots=SMALL_ROOTS, limit=0, **settings)


def chains_with_heights(tree):
    starts = [0] + [node for node in range(1, len(tree.parents)) if tree.main_child(tree.parents[node]) != node]
    chains = []
    owner = {}
    for index, start in enumerate(starts):
        nodes = [tree.parents[start]] if start > 0 else []
        own = [start]
        while tree.main_child(own[-1]) is not None:
            own.append(tree.main_child(own[-1]))
        chains.append(nodes + own)
        owner.update({node: index for node in own})
    heights = [1] * len(chains)
    for index in sorted(range(len(chains)), key=lambda index: -starts[index]):
        for node in chains[index]:
            for child in tree.children[node] if owner[node] == index else ():
                if owner[child] != index:
                    heights[index] = max(heights[index], heights[owner[child]] + 1)
    return chains, heights


def leaf_frames(name):
    leaves = sorted((obj for obj in bpy.data.objects if obj.parent is not None and obj.parent.name == name), key=lambda obj: obj.name)
    origins = numpy.array([list(obj.matrix_world.translation) for obj in leaves])
    axes = numpy.array([list(obj.matrix_world.to_3x3().normalized().col[0]) for obj in leaves])
    return origins, axes


def nearest_chain(tree, chains, point):
    best = None
    for index, nodes in enumerate(chains):
        if len(nodes) < 2:
            continue
        line = tree.positions[nodes]
        gaps = segment_distances(point[None, :], line[:-1], line[1:])[0]
        segment = int(numpy.argmin(gaps))
        if best is None or gaps[segment] < best[1]:
            best = (index, float(gaps[segment]), segment)
    return best


def test_leaves_sit_at_twig_tips_and_along_the_last_orders_only(bridge):
    for levels, orders in ((False, 1), (False, 2), (True, 2)):
        grow(bridge, levels=levels)
        reply = bridge.ok("tree_leaves", name="Grown", orders=orders, realize=False, density=12.0)
        tree = Skeleton(bpy.data.objects["Grown"])
        chains, heights = chains_with_heights(tree)
        origins, _ = leaf_frames(reply["name"])
        assert len(origins) == reply["leaves"] > 100
        leafy = [index for index, height in enumerate(heights) if height <= orders and tree.kinds[chains[index][-1]] == 0]
        tips = [node for node in range(1, len(tree.parents)) if not tree.children[node] and tree.kinds[node] == 0]
        for origin in origins:
            if min(numpy.linalg.norm(tree.positions[tip] - origin) - tree.radii[tip] for tip in tips) <= 1e-6:
                continue
            near = [index for index in leafy if len(chains[index]) > 1 and segment_distances(origin[None, :], tree.positions[chains[index]][:-1], tree.positions[chains[index]][1:]).min() <= tree.radii[chains[index]].max() + 1e-6]
            assert near, (levels, orders, origin)
        for tip in tips:
            assert numpy.linalg.norm(origins - tree.positions[tip], axis=1).min() <= tree.radii[tip] + 1e-6, tip
        assert 0 < len(leafy) < len(chains)
        bridge.ok("new_scene")


def transported(normal, points, tangents):
    for index in range(len(points) - 1):
        step = points[index + 1] - points[index]
        square = float(step @ step)
        if square < 1e-18:
            continue
        reflected = normal - (2.0 / square) * float(step @ normal) * step
        turned = tangents[index] - (2.0 / square) * float(step @ tangents[index]) * step
        second = tangents[index + 1] - turned
        square_two = float(second @ second)
        normal = reflected if square_two < 1e-18 else reflected - (2.0 / square_two) * float(second @ reflected) * second
    return normal


def path_between(tree, nodes, first, second):
    line = tree.positions[nodes]
    directions = numpy.diff(line, axis=0)
    directions /= numpy.linalg.norm(directions, axis=1, keepdims=True)
    points = [first[0]] + [line[index] for index in range(first[1] + 1, second[1] + 1)] + [second[0]]
    tangents = [directions[first[1]]] + [directions[index] for index in range(first[1] + 1, second[1] + 1)] + [directions[second[1]]]
    return numpy.array(points), numpy.array(tangents), directions


def outward(axis, tangent):
    across = axis - float(axis @ tangent) * tangent
    return across / numpy.linalg.norm(across)


def segment_table(tree, chains):
    rows = [(index, segment) for index, nodes in enumerate(chains) for segment in range(len(nodes) - 1)]
    starts = numpy.array([tree.positions[chains[index][segment]] for index, segment in rows])
    spans = numpy.array([tree.positions[chains[index][segment + 1]] for index, segment in rows]) - starts
    return rows, starts, spans


def anchor_of(origin, axis, table):
    rows, starts, spans = table
    offsets = origin - starts
    across = spans @ axis
    square = numpy.einsum("ij,ij->i", spans, spans)
    determinant = float(axis @ axis) * square - across * across
    usable = numpy.abs(determinant) > 1e-18
    share = numpy.where(usable, (float(axis @ axis) * numpy.einsum("ij,ij->i", spans, offsets) - across * (offsets @ axis)) / numpy.where(usable, determinant, 1.0), 0.0)
    share = numpy.clip(share, 0.0, 1.0)
    points = starts + share[:, None] * spans
    rest = origin - points
    gaps = numpy.linalg.norm(rest - (rest @ axis)[:, None] * axis[None, :], axis=1)
    best = int(numpy.argmin(gaps))
    return rows[best][0], rows[best][1], points[best], float(gaps[best])


def test_consecutive_leaves_along_a_twig_differ_by_the_divergence(bridge):
    for divergence in (137.5, 90.0):
        grow(bridge)
        reply = bridge.ok("tree_leaves", name="Grown", realize=False, divergence=divergence, density=10.0, tip_leaves=2, angle=90.0)
        tree = Skeleton(bpy.data.objects["Grown"])
        chains, _ = chains_with_heights(tree)
        origins, axes = leaf_frames(reply["name"])
        table = segment_table(tree, chains)
        found = [anchor_of(origin, axis, table) for origin, axis in zip(origins, axes)]
        checked = 0
        for index in range(len(origins) - 1):
            if found[index][0] != found[index + 1][0] or max(found[index][3], found[index + 1][3]) > 1e-5:
                continue
            nodes = chains[found[index][0]]
            points, tangents, directions = path_between(tree, nodes, (found[index][2], found[index][1]), (found[index + 1][2], found[index + 1][1]))
            if found[index + 1][1] < found[index][1]:
                continue
            second_tangent = directions[found[index + 1][1]]
            first_out = outward(axes[index], directions[found[index][1]])
            second_out = outward(axes[index + 1], second_tangent)
            moved = transported(first_out, points, tangents)
            moved -= float(moved @ second_tangent) * second_tangent
            moved /= numpy.linalg.norm(moved)
            turn = math.degrees(math.atan2(float(numpy.cross(moved, second_out) @ second_tangent), float(moved @ second_out))) % 360.0
            assert min(abs(turn - divergence), 360.0 - abs(turn - divergence)) <= ANGLE_SLACK, (divergence, turn, index)
            checked += 1
        assert checked > 100
        bridge.ok("new_scene")


def test_the_same_seed_gives_the_same_leaves(bridge):
    grow(bridge)
    first = bridge.ok("tree_leaves", name="Grown", leaves_name="First", seed=9)
    second = bridge.ok("tree_leaves", name="Grown", leaves_name="Second", seed=9)
    other = bridge.ok("tree_leaves", name="Grown", leaves_name="Other", seed=10)
    points = {name: numpy.array([list(vertex.co) for vertex in bpy.data.objects[name].data.vertices]) for name in ("First", "Second", "Other")}
    assert first["leaves"] == second["leaves"] == other["leaves"]
    assert numpy.array_equal(points["First"], points["Second"])
    assert not numpy.allclose(points["First"], points["Other"])


def test_cards_carry_the_leaf_preset_and_a_given_leaf_can_replace_them(bridge):
    grow(bridge)
    bridge.ok("material_procedural", name="Leaf", leaf={"cutout": True, "translucency": 0.4})
    reply = bridge.ok("tree_leaves", name="Grown", material="Leaf")
    leaves = bpy.data.objects[reply["name"]]
    assert [material.name for material in leaves.data.materials] == ["Leaf"]
    uvs = numpy.array([list(item.vector) for item in leaves.data.uv_layers.active.uv]).reshape(-1, 4, 2)
    assert uvs.min() >= 0.0 and uvs.max() <= 1.0 and len(uvs) == 2 * reply["leaves"]
    assert numpy.allclose(uvs[:, :, 1].min(axis=1), 0.0) and numpy.allclose(uvs[:, :, 1].max(axis=1), 1.0)
    assert numpy.allclose(uvs[:, :, 0].max(axis=1) - uvs[:, :, 0].min(axis=1), 0.5)
    per_card = uvs.reshape(-1, 8, 2)
    assert numpy.allclose(per_card.min(axis=1), 0.0) and numpy.allclose(per_card.max(axis=1), 1.0)
    principled = next(node for node in bpy.data.materials["Leaf"].node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    assert principled.inputs["Alpha"].is_linked
    assert principled.inputs["Transmission Weight"].default_value > 0.0 or principled.inputs["Transmission Weight"].is_linked
    bridge.ok("mesh_from_data", name="Needles", vertices=[[0, 0, 0], [0.1, -0.003, 0], [0.1, 0.003, 0], [0.09, 0.03, 0.01], [0.09, -0.03, 0.01]], faces=[[0, 1, 2], [0, 2, 3], [0, 4, 1]])
    needles = bridge.ok("tree_leaves", name="Grown", leaves_name="Needled", source="Needles", tip_leaves=0)
    assert len(bpy.data.objects["Needled"].data.vertices) == 5 * needles["leaves"]


def test_the_leaf_count_stays_within_the_instance_limit(bridge):
    grow(bridge)
    message = bridge.refuse("tree_leaves", "bad_args", name="Grown", density=500.0, orders=6)
    assert str(MAX_INSTANCES) in message
    bridge.refuse("tree_leaves", "bad_args", name="Grown", material="Missing")


def test_the_skeleton_survives_tree_mesh_and_a_glb_export(bridge):
    grow(bridge, location=[1.0, 2.0, 0.0])
    expected = plain(bpy.data.objects["Grown"][PROPERTY])
    reply = bridge.ok("tree_mesh", name="Grown", keep_skeleton=False)
    exported = bridge.ok("export", path="tree.glb")
    assert exported["skeletons"] == [reply["name"]]
    document, _ = read_glb(os.path.join(bridge.workspace, "tree.glb"))
    nodes = {node.get("name"): node for node in document["nodes"]}
    assert nodes[reply["name"]]["extras"][PROPERTY] == expected
    bridge.ok("new_scene")
    bridge.ok("import", path="tree.glb")
    imported = bpy.data.objects[reply["name"]]
    assert plain(imported[PROPERTY]) == expected
    again = bridge.ok("tree_mesh", name=reply["name"], mesh_name="Rebuilt")
    assert again["manifold"] and again["shells"] == 1
    assert plain(bpy.data.objects["Rebuilt"][PROPERTY]) == expected
    leaves = bridge.ok("tree_leaves", name="Rebuilt")
    assert leaves["leaves"] > 100


run(globals())
