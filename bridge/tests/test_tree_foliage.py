import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from blendworks_bridge.gltf_extras import read_glb
from blendworks_bridge.kit_limits import MAX_INSTANCES
from blendworks_bridge.tree_foliage import ATTRIBUTES
from blendworks_bridge.tree_skeleton import from_property
from blendworks_bridge.tree_species import FOLIAGE_DEFAULTS
from tree_mesh_helpers import SMALL

VARIED = ("leaf_hue", "leaf_saturation", "leaf_value", "leaf_age", "leaf_damage", "leaf_shape", "leaf_seed")
STILL = {"size": 0.0, "curl": 0.0, "fold": 0.0, "tilt": 0.0, "hue": 0.0, "saturation": 0.0, "value": 0.0, "age": 0.0, "damage": 0.0}
LEAF_VERTICES = 9


def foliage_clusters():
    return FOLIAGE_DEFAULTS["clusters"]


def foliage_variation():
    return FOLIAGE_DEFAULTS["variation"]


def grow(bridge, name="Grown", **extra):
    return bridge.ok("grow_tree", name=name, limit=0, **{**SMALL, **extra})


def face_values(mesh, key):
    values = numpy.zeros(len(mesh.polygons), dtype=numpy.float32)
    mesh.attributes[key].data.foreach_get("value", values)
    return values


def leaf_faces(mesh):
    materials = numpy.zeros(len(mesh.polygons), dtype=numpy.int32)
    mesh.polygons.foreach_get("material_index", materials)
    return materials == 0


def leaf_corners(mesh):
    points = numpy.zeros(3 * len(mesh.vertices))
    mesh.vertices.foreach_get("co", points)
    points = points.reshape(-1, 3)
    twig_vertices = min(polygon.vertices[0] for polygon, leafy in zip(mesh.polygons, leaf_faces(mesh)) if leafy)
    return points[twig_vertices:].reshape(-1, LEAF_VERTICES, 3)


def chord_lengths(corners):
    return numpy.linalg.norm(corners[:, 7] - corners[:, 1], axis=1)


def curl_angles(corners):
    first = corners[:, 4] - corners[:, 1]
    last = corners[:, 7] - corners[:, 4]
    cosine = numpy.einsum("ij,ij->i", first, last) / (numpy.linalg.norm(first, axis=1) * numpy.linalg.norm(last, axis=1))
    return numpy.degrees(numpy.arccos(numpy.clip(cosine, -1.0, 1.0)))


def test_every_leaf_varies_in_size_curl_colour_age_damage_and_shape(bridge):
    grow(bridge)
    varied = bridge.ok("tree_leaves", name="Grown", leaves_name="Varied", species="oak", seed=3)
    still = bridge.ok("tree_leaves", name="Grown", leaves_name="Still", species="oak", seed=3, variation=STILL, jitter={"size": 0.0, "roll": 0.0}, clusters={"shade_growth": 0.0}, shapes=1)
    for reply, name in ((varied, "Varied"), (still, "Still")):
        mesh = bpy.data.objects[name].data
        leafy = leaf_faces(mesh)
        assert reply["leaves"] > 1000 and leafy.sum() == 8 * reply["leaves"]
        spreads = {key: float(face_values(mesh, key)[leafy].std()) for key in VARIED}
        corners = leaf_corners(mesh)
        chords = chord_lengths(corners)
        spreads["size"] = float(chords.std() / chords.mean())
        spreads["curl"] = float(curl_angles(corners).std())
        if name == "Varied":
            for key in ("leaf_hue", "leaf_saturation", "leaf_value", "leaf_age", "leaf_damage", "leaf_shape", "leaf_seed", "curl"):
                assert spreads[key] > 0.0, (key, spreads)
            assert len(numpy.unique(face_values(mesh, "leaf_shape")[leafy])) == 3
            assert 0.05 < float(numpy.mean(face_values(mesh, "leaf_damage")[leafy] > 0.0)) < 0.5
            varied_spreads = spreads
        else:
            for key in ("leaf_hue", "leaf_saturation", "leaf_value", "leaf_age", "leaf_damage", "leaf_shape"):
                assert spreads[key] < 1e-6, (key, spreads)
            assert spreads["curl"] < 1e-2, spreads
            assert varied_spreads["size"] > spreads["size"] + 0.05, (varied_spreads["size"], spreads["size"])
    for key in ("size_cv", "curl_spread", "hue_spread", "saturation_spread", "value_spread", "age_spread", "damage_spread"):
        assert varied["variation"][key] > 0.0 and still["variation"][key] < 1e-6 or key == "size_cv", (key, varied["variation"], still["variation"])


def test_clusters_fan_out_of_every_tip_as_a_twig_level_beyond_the_skeleton(bridge):
    grow(bridge)
    skeleton = from_property(bpy.data.objects["Grown"])
    children = numpy.bincount(skeleton.parents[1:], minlength=skeleton.count)
    tips = [node for node in range(1, skeleton.count) if children[node] == 0 and skeleton.kinds[node] == 0]
    for per_tip in (3, 0):
        name = f"Tips{per_tip}"
        reply = bridge.ok("tree_leaves", name="Grown", leaves_name=name, clusters={"per_tip": per_tip, "tip_spread": 30.0}, realize=False)
        copies = [obj for obj in bpy.data.objects if obj.parent is not None and obj.parent.name == name]
        assert len(copies) == reply["clusters"]
        origins = numpy.array([list(obj.matrix_world.translation) for obj in copies])
        axes = numpy.array([list(obj.matrix_world.to_3x3().normalized().col[0]) for obj in copies])
        fanned = 0
        for tip in tips:
            at_tip = numpy.flatnonzero(numpy.linalg.norm(origins - skeleton.positions[tip], axis=1) < 1e-5)
            tangent = skeleton.positions[tip] - skeleton.positions[skeleton.parents[tip]]
            tangent /= numpy.linalg.norm(tangent)
            outward = [index for index in at_tip if math.degrees(math.acos(min(1.0, float(axes[index] @ tangent)))) <= 30.0 + 1e-3]
            assert len(outward) == len(at_tip) == per_tip, (tip, len(at_tip), len(outward))
            fanned += len(outward)
        assert reply["tip_clusters"] == fanned == per_tip * len(tips)


def test_outer_clusters_turn_their_leaves_to_the_sun_more_than_inner_ones(bridge):
    grow(bridge)
    sun = numpy.array([1.0, 0.0, 1.0]) / math.sqrt(2.0)
    correlation = {}
    for name, align in (("Biased", {"sun": list(sun), "factor": 1.0, "inner": 0.0}), ("Even", {"sun": list(sun), "factor": 0.5, "inner": 0.5})):
        bridge.ok("tree_leaves", name="Grown", leaves_name=name, align=align, jitter={"roll": 0.0}, clusters={"per_tip": 1}, realize=False)
        copies = [obj for obj in bpy.data.objects if obj.parent is not None and obj.parent.name == name]
        origins = numpy.array([list(obj.matrix_world.translation) for obj in copies])
        faces = numpy.array([list(obj.matrix_world.to_3x3().normalized().col[2]) for obj in copies])
        centre = origins.mean(axis=0)
        reach = numpy.linalg.norm((origins - centre) / numpy.abs(origins - centre).max(axis=0), axis=1)
        facing = faces @ sun
        inner, outer = numpy.percentile(reach, [30.0, 70.0])
        correlation[name] = float(facing[reach >= outer].mean() - facing[reach <= inner].mean())
    assert correlation["Biased"] > 0.1, correlation
    assert abs(correlation["Even"]) < 0.05, correlation


def test_the_same_seed_gives_the_same_clusters_and_another_seed_others(bridge):
    grow(bridge)
    for name, seed in (("First", 5), ("Second", 5), ("Other", 6)):
        bridge.ok("tree_leaves", name="Grown", leaves_name=name, seed=seed)
    meshes = {name: bpy.data.objects[name].data for name in ("First", "Second", "Other")}
    points = {}
    for name, mesh in meshes.items():
        values = numpy.zeros(3 * len(mesh.vertices))
        mesh.vertices.foreach_get("co", values)
        points[name] = values
    assert numpy.array_equal(points["First"], points["Second"])
    for key in ATTRIBUTES:
        assert numpy.array_equal(face_values(meshes["First"], key), face_values(meshes["Second"], key)), key
    assert points["First"].shape != points["Other"].shape or not numpy.allclose(points["First"], points["Other"])


def test_clusters_stay_within_the_instance_budget_and_share_meshes_when_linked(bridge):
    grow(bridge)
    message = bridge.refuse("tree_leaves", "bad_args", name="Grown", orders=6, clusters={"spacing": 0.002})
    assert f"the cap is {MAX_INSTANCES} instances" in message
    reply = bridge.ok("tree_leaves", name="Grown", leaves_name="Linked", realize=False, variants=6)
    copies = [obj for obj in bpy.data.objects if obj.parent is not None and obj.parent.name == "Linked"]
    assert len(copies) == reply["clusters"] <= MAX_INSTANCES
    assert len({copy.data.name for copy in copies}) == len(reply["variants"]) == 6
    assert all("leaf_hue" in copy and "leaf_value" in copy for copy in copies)
    bridge.ok("export", path="linked.glb")
    document, _ = read_glb(os.path.join(bridge.workspace, "linked.glb"))
    shared = [index for index, mesh in enumerate(document["meshes"]) if mesh["name"].startswith("Linked_cluster_")]
    assert len(shared) == 6
    assert len([node for node in document["nodes"] if node.get("mesh") in shared]) == len(copies)


def test_foliage_over_the_vertex_cap_is_refused_from_the_counts_before_anything_is_built(bridge):
    import tracemalloc

    from blendworks_bridge.limits import MAX_MESH_VERTICES
    from blendworks_bridge.tree_sprays import SprayStyle, build_sprays, vertex_bound
    from blendworks_bridge.errors import BridgeError

    grow(bridge)
    huge = {"leaves": [80, 80], "forks": [8, 8], "spacing": 0.05}
    tracemalloc.start()
    message = bridge.refuse("tree_leaves", "bad_args", name="Grown", clusters=huge)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert "vertices" in message and str(MAX_MESH_VERTICES) in message, message
    assert peak < 60_000_000, peak
    style = SprayStyle({"clusters": {**foliage_clusters(), **huge}, "variation": foliage_variation(), "card": {"width": 0.5, "fold": 0.0}, "size": 0.1, "shapes": 3, "shape_length": [1, 1, 1], "detail": "full"})
    assert vertex_bound(style, MAX_INSTANCES) > 50 * MAX_MESH_VERTICES
    try:
        build_sprays(style, numpy.random.default_rng(0), numpy.zeros((MAX_INSTANCES, 4, 4)))
    except BridgeError:
        pass
    else:
        raise AssertionError("20000 clusters of 80 leaves on 9 twigs were built")


def test_thin_shoots_beyond_the_last_orders_carry_clusters_when_a_bearing_radius_is_given(bridge):
    grow(bridge)
    plain = bridge.ok("tree_leaves", name="Grown", leaves_name="Plain", orders=1, clusters={"spacing": 0.3})
    bearing = bridge.ok("tree_leaves", name="Grown", leaves_name="Bearing", orders=1, clusters={"spacing": 0.3, "bearing_radius": 0.2})
    assert bearing["clusters"] > 1.1 * plain["clusters"], (plain["clusters"], bearing["clusters"])
    assert bearing["tip_clusters"] == plain["tip_clusters"]


def test_reach_keeps_clusters_to_the_last_metres_of_each_shoot(bridge):
    from blendworks_bridge.tree_leaves import shoot_chains

    grow(bridge)
    skeleton = from_property(bpy.data.objects["Grown"])
    ends = skeleton.positions[[chain[-1] for _, chain, _, _ in shoot_chains(skeleton)]]
    whole = bridge.ok("tree_leaves", name="Grown", leaves_name="Whole", realize=False, clusters={"spacing": 0.1})
    reached = bridge.ok("tree_leaves", name="Grown", leaves_name="Reached", realize=False, clusters={"spacing": 0.1, "reach": 0.3})
    assert reached["tip_clusters"] == whole["tip_clusters"] and reached["clusters"] < 0.8 * whole["clusters"], (whole["clusters"], reached["clusters"])
    copies = [obj for obj in bpy.data.objects if obj.parent is not None and obj.parent.name == "Reached"]
    assert len(copies) == reached["clusters"]
    for copy in copies:
        nearest = float(numpy.linalg.norm(ends - numpy.array(copy.matrix_world.translation), axis=1).min())
        assert nearest <= 0.3 + 0.05, nearest


def test_low_detail_builds_flat_leaves_and_ribbon_twigs_for_distant_lods(bridge):
    grow(bridge)
    full = bridge.ok("tree_leaves", name="Grown", leaves_name="Full", seed=2)
    low = bridge.ok("tree_leaves", name="Grown", leaves_name="Low", seed=2, detail="low")
    assert full["clusters"] == low["clusters"] and full["leaves"] == low["leaves"]
    leafy = leaf_faces(bpy.data.objects["Low"].data)
    assert leafy.sum() == 2 * low["leaves"]
    assert low["triangles"] < 0.35 * full["triangles"]


run(globals())
