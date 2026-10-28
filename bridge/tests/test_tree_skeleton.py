import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from blendworks_bridge.kit_limits import MAX_TREE_POINTS
from blendworks_bridge.tree_skeleton import FORMAT, PROPERTY, VERSION
from tree_helpers import tree_of

CROWN = dict(height=6.0, trunk_height=1.5, crown_radius=2.0, points=800, influence=0.9, kill=0.2, step=0.12)
ROOTS = dict(points=400, depth=0.8, radius=1.4, influence=0.6, kill=0.18, step=0.1)
LEVELS = dict(method="levels", envelope="tend_flame", height=8.0, trunk_height=1.5, branches=[16, 6, 3], levels=4, segments=[16, 6, 4, 3])
PIPE_SLACK = 1e-6


def pipe_errors(tree, exponent):
    errors = []
    for node in tree.branchings():
        own = tree.radii[node] ** exponent
        errors.append(abs(own - float(numpy.sum(tree.radii[tree.children[node]] ** exponent))) / own)
    return errors


def test_radii_follow_the_pipe_model_at_every_branching(bridge):
    for exponent in (2.0, 2.5):
        for name, settings in (("Grown", dict(CROWN, roots=ROOTS)), ("Built", dict(LEVELS, roots=ROOTS))):
            result = bridge.ok("grow_tree", name=name, exponent=exponent, tip_radius=0.006, seed=5, **settings)
            tree = tree_of(name)
            errors = pipe_errors(tree, exponent)
            assert len(errors) > 50 and max(errors) < PIPE_SLACK, (name, exponent, max(errors))
            assert result["pipe_error"] == max(errors) and result["exponent"] == exponent
            assert tree.radii[0] == tree.radii.max()
            tips = [node for node, below in enumerate(tree.children) if not below and tree.kinds[node] == 0]
            if name == "Grown":
                assert numpy.all(tree.radii[tips] == 0.006)
            bridge.ok("delete", names=[name])


def test_the_skeleton_is_one_tree_with_roots_below_and_shoots_above_the_base(bridge):
    for name, settings in (("Grown", CROWN), ("Built", LEVELS)):
        upward = dict(ROOTS, tropism=[0.0, 0.0, 0.8])
        bridge.ok("grow_tree", name=name, location=[3.0, -2.0, 1.0], roots=upward, seed=7, **settings)
        tree = tree_of(name)
        assert numpy.flatnonzero(tree.parents < 0).tolist() == [0]
        assert numpy.all(tree.parents[1:] < numpy.arange(1, len(tree.parents)))
        reached = numpy.zeros(len(tree.parents), dtype=bool)
        reached[0] = True
        for node in range(1, len(tree.parents)):
            assert reached[tree.parents[node]]
            reached[node] = True
        roots = tree.kinds == 1
        assert roots.sum() > 100 and numpy.all(tree.positions[roots, 2] < tree.positions[0, 2])
        assert numpy.all(tree.positions[1:][~roots[1:], 2] > tree.positions[0, 2])
        first_roots = [node for node in numpy.flatnonzero(roots) if not roots[tree.parents[node]]]
        assert first_roots and all(tree.parents[node] == 0 for node in first_roots)
        assert numpy.allclose(bpy.data.objects[name].location, [3.0, -2.0, 1.0])


def test_the_skeleton_survives_a_gltf_export_and_import_node_for_node(bridge):
    bridge.ok("grow_tree", name="Oak", roots=ROOTS, seed=3, **CROWN)
    bridge.ok("grow_tree", name="Fir", location=[5.0, 0.0, 0.0], **LEVELS)
    bridge.ok("add_primitive", type="cube", name="Crate", location=[0.0, 6.0, 0.0])
    before = {name: tree_of(name) for name in ("Oak", "Fir")}
    exported = bridge.ok("export", path="trees.glb")
    assert exported["skeletons"] == ["Fir", "Oak"]
    bridge.ok("new_scene")
    bridge.ok("import", path="trees.glb")
    for name, tree in before.items():
        after = tree_of(name)
        assert after.data["format"] == FORMAT and after.data["version"] == VERSION and after.data["count"] == len(tree.parents)
        for column in ("positions", "parents", "radii", "orders", "kinds"):
            assert numpy.array_equal(getattr(after, column), getattr(tree, column)), (name, column)
        page = bridge.ok("tree_skeleton", name=name, offset=0, limit=5)
        assert page["nodes"] == len(tree.parents) and page["page"]["next_offset"] == 5
    assert PROPERTY not in bpy.data.objects["Crate"].keys()
    bridge.ok("export", path="plain.glb", names=["Crate"])
    assert "skeletons" not in bridge.ok("export", path="plain.glb", names=["Crate"])


def test_pages_cover_every_node_once(bridge):
    result = bridge.ok("grow_tree", name="Tree", offset=0, limit=7, seed=1, **CROWN)
    tree = tree_of("Tree")
    assert result["page"]["columns"] == ["x", "y", "z", "parent", "radius", "order", "kind"]
    rows = list(result["page"]["nodes"])
    offset = result["page"]["next_offset"]
    while offset is not None:
        page = bridge.ok("tree_skeleton", name="Tree", offset=offset, limit=1000)["page"]
        rows.extend(page["nodes"])
        offset = page["next_offset"]
    assert len(rows) == len(tree.parents) == result["nodes"]
    assert [row[3] for row in rows] == tree.parents.tolist()
    assert numpy.allclose([row[:3] for row in rows], tree.positions, atol=1e-6)
    assert numpy.allclose([row[4] for row in rows], tree.radii, atol=1e-6)
    bridge.ok("add_primitive", type="cube", name="Box")
    assert "no tree skeleton" in bridge.refuse("tree_skeleton", "bad_args", name="Box")
    bridge.refuse("tree_skeleton", "not_found", name="Nothing")


def test_the_preview_is_a_curve_beveled_by_the_node_radii(bridge):
    bridge.ok("grow_tree", name="Tree", roots=ROOTS, seed=2, **CROWN)
    tree = tree_of("Tree")
    curve = bpy.data.objects["Tree"].data
    assert bpy.data.objects["Tree"].type == "CURVE" and curve.bevel_depth == 1.0
    starts = [node for node in range(1, len(tree.parents)) if tree.orders[node] != tree.orders[tree.parents[node]] or tree.kinds[node] != tree.kinds[tree.parents[node]]]
    assert len(curve.splines) == len(starts) + 1
    for spline in curve.splines:
        radii = numpy.array([point.radius for point in spline.points])
        assert numpy.all(numpy.diff(radii[1:]) <= 1e-6), "radii grow towards a tip"
    evaluated = bpy.data.objects["Tree"].evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    assert len(mesh.polygons) > 1000
    corners = numpy.array([vertex.co for vertex in mesh.vertices])
    evaluated.to_mesh_clear()
    assert numpy.all(corners.max(axis=0) >= tree.positions.max(axis=0)) and numpy.all(corners.min(axis=0) <= tree.positions.min(axis=0))


def test_attraction_points_over_the_cap_are_refused_before_growth(bridge):
    message = bridge.refuse("grow_tree", "bad_args", name="Tree", points=MAX_TREE_POINTS, roots={"points": 10})
    assert f"cap of {MAX_TREE_POINTS}" in message, message
    message = bridge.refuse("grow_tree", "bad_args", name="Tree", step=0.01, trunk_height=500.0, height=900.0)
    assert "trunk alone" in message and "max_nodes" in message, message
    message = bridge.refuse("grow_tree", "bad_args", name="Tree", kill=2.0, influence=1.0)
    assert "kill must be smaller" in message
    bridge.refuse("grow_tree", "bad_args", name="Tree", taper=0.5)
    assert bridge.ok("scene_info")["objects"] == []


run(globals())
