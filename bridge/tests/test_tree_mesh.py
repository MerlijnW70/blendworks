import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bmesh
import bpy
import numpy

from blendworks_bridge.topology import mesh_report
from blendworks_bridge.tree_skeleton import PROPERTY
from tree_helpers import plain
from tree_mesh_helpers import LEVELS, RADIUS_TOLERANCE, SMALL, SMALL_ROOTS, radius_errors, self_intersections, shells, uv_scales, weighted_share

UV_BAND = (0.8, 1.25)
UV_SHARE = 0.97
VOXEL = dict(junction="voxel", min_radius=0.012)


def grow(bridge, name, levels=False, **extra):
    settings = dict(LEVELS if levels else SMALL, **extra)
    return bridge.ok("grow_tree", name=name, roots=SMALL_ROOTS, limit=0, **settings)


def closed_shell(obj, reply):
    report = mesh_report(obj.data)
    assert report["manifold"], (obj.name, report)
    assert report["inconsistent_edges"] == 0 and report["open_edges"] == 0 and report["pinched_vertices"] == 0, report
    assert report["volume"] > 0.0, report
    assert shells(obj) == 1
    assert len(obj.modifiers) == 0
    assert reply["manifold"] and reply["shells"] == 1 and reply["volume"] > 0.0


def test_the_bark_is_one_closed_manifold_shell_for_both_tree_kinds_and_junctions(bridge):
    for levels in (False, True):
        for junction in ("skin", "voxel"):
            name = f"{'Built' if levels else 'Grown'}{junction}"
            grow(bridge, name, levels)
            extra = VOXEL if junction == "voxel" else {}
            reply = bridge.ok("tree_mesh", name=name, **extra)
            bark = bpy.data.objects[reply["name"]]
            closed_shell(bark, reply)
            assert reply["junction"] == junction
            assert bark.type == "MESH" and bark.data.uv_layers.active is not None
            assert not [name for name in ("tree_radius", "tree_tangent", "tree_material", "tree_axis") if name in bark.data.attributes]
            bridge.ok("delete", names=[reply["name"]])


def test_the_mesh_radius_matches_the_skeleton_radius_at_every_node_outside_the_flare(bridge):
    for levels, extra in ((False, {}), (True, {}), (False, VOXEL)):
        name = "Built" if levels else "Grown"
        grow(bridge, name, levels)
        reply = bridge.ok("tree_mesh", name=name, **extra)
        errors, total = radius_errors(bpy.data.objects[reply["name"]], reply)
        worst = max(errors.items(), key=lambda item: abs(item[1]))
        assert len(errors) > (100 if extra else max(150, 0.3 * total)), (len(errors), total)
        assert abs(worst[1]) <= RADIUS_TOLERANCE, (name, extra, worst)
        bridge.ok("delete", names=[reply["name"], name])


def test_junctions_have_no_self_intersections(bridge):
    for levels in (False, True):
        for extra in ({}, VOXEL):
            name = "Built" if levels else "Grown"
            grow(bridge, name, levels)
            reply = bridge.ok("tree_mesh", name=name, **extra)
            bark = bpy.data.objects[reply["name"]]
            assert self_intersections(bark) == 0, (name, extra)
            assert reply["self_intersections"] == 0
            bridge.ok("delete", names=[reply["name"], name])


def test_bark_uvs_are_metres_along_and_around_every_branch(bridge):
    for levels in (False, True):
        name = "Built" if levels else "Grown"
        grow(bridge, name, levels)
        reply = bridge.ok("tree_mesh", name=name)
        bark = bpy.data.objects[reply["name"]]
        reach = 1.5 * max(reply["flare"]["height"], reply["root_flare"]["length"])
        around, along, areas = uv_scales(bark, ["bark", "roots"], reach)
        for scale in (around, along):
            assert weighted_share(scale, areas, *UV_BAND) >= UV_SHARE, (name, weighted_share(scale, areas, *UV_BAND))
            assert abs(float(numpy.median(scale)) - 1.0) < 0.02
        bridge.ok("delete", names=[reply["name"], name])


def seam_facing(obj):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    layer = bm.loops.layers.uv.active
    bm.normal_update()
    facing = []
    for edge in bm.edges:
        if len(edge.link_loops) != 2:
            continue
        first, second = edge.link_loops
        a = (first[layer].uv, first.link_loop_next[layer].uv)
        b = (second.link_loop_next[layer].uv, second[layer].uv)
        jumps = (a[0] - b[0], a[1] - b[1])
        if all(abs(jump.x) > 1e-4 and abs(jump.y) < 1e-5 for jump in jumps) and abs(a[0].y - a[1].y) > 1e-4:
            normal = (edge.link_faces[0].normal + edge.link_faces[1].normal).normalized()
            facing.append(numpy.array(normal) * edge.calc_length())
    bm.free()
    return numpy.array(facing)


def test_uv_seams_run_on_the_side_away_from_the_view(bridge):
    for view in ([0.0, -1.0, 0.0], [1.0, 0.0, 0.0]):
        grow(bridge, "Grown")
        reply = bridge.ok("tree_mesh", name="Grown", view=view, bark_noise={"amplitude": 0.0})
        seams = seam_facing(bpy.data.objects[reply["name"]])
        lengths = numpy.linalg.norm(seams, axis=1)
        towards = seams @ numpy.array(view)
        assert len(seams) > 200
        assert float(towards.sum() / lengths.sum()) < -0.5, (view, float(towards.sum() / lengths.sum()))
        assert float(lengths[towards > 0.5 * lengths].sum() / lengths.sum()) < 0.1
        bridge.ok("delete", names=[reply["name"], "Grown"])


def test_a_lod_budget_is_met_within_ten_percent_and_the_radii_still_hold(bridge):
    for budget, extra in ((30_000, {}), (9_000, {}), (150_000, {"junction": "voxel", "min_radius": 0.012})):
        grow(bridge, "Grown")
        reply = bridge.ok("tree_mesh", name="Grown", lod=budget, **extra)
        bark = bpy.data.objects[reply["name"]]
        triangles = sum(len(polygon.vertices) - 2 for polygon in bark.data.polygons)
        assert reply["triangles"] == triangles
        assert abs(triangles / budget - 1.0) <= 0.1, (budget, triangles)
        assert reply["lod"]["budget"] == budget
        closed_shell(bark, reply)
        errors, _ = radius_errors(bark, reply)
        assert len(errors) > (25 if extra else 100) and max(abs(value) for value in errors.values()) <= RADIUS_TOLERANCE, (budget, max(errors.items(), key=lambda item: abs(item[1])))
        bridge.ok("delete", names=[reply["name"], "Grown"])


def test_the_skeleton_stays_on_the_mesh_object(bridge):
    grow(bridge, "Grown", location=[2.0, -1.0, 0.5])
    expected = plain(bpy.data.objects["Grown"][PROPERTY])
    reply = bridge.ok("tree_mesh", name="Grown")
    bark = bpy.data.objects[reply["name"]]
    assert plain(bark[PROPERTY]) == expected
    assert tuple(round(value, 6) for value in bark.location) == (2.0, -1.0, 0.5)
    assert reply["skeleton"]["kept_on"] == "Grown" and bpy.data.objects["Grown"].hide_render
    again = bridge.ok("tree_mesh", name=reply["name"], mesh_name="Again", keep_skeleton=False)
    assert "Grown_bark" not in bpy.data.objects and plain(bpy.data.objects["Again"][PROPERTY]) == expected
    assert again["skeleton"]["kept_on"] is None


def test_cut_twigs_end_in_fresh_wood_and_the_slots_follow_the_parts(bridge):
    grow(bridge, "Grown")
    whole = bridge.ok("tree_mesh", name="Grown", min_radius=0.0)
    assert whole["materials"] == ["bark", "roots"] and whole["cut_ends"] == 0
    reply = bridge.ok("tree_mesh", name="Grown", mesh_name="Pruned", min_radius=0.02, twigs="cards")
    assert reply["materials"] == ["bark", "fresh_wood", "roots"] and reply["cut_ends"] > 10
    bark = bpy.data.objects["Pruned"]
    slots = [material.name for material in bark.data.materials]
    used = {slots[polygon.material_index] for polygon in bark.data.polygons}
    assert used == {"bark", "fresh_wood", "roots"}
    assert reply["nodes_kept"] < whole["nodes_kept"]
    cards = bpy.data.objects[reply["twigs"]["name"]]
    assert reply["twigs"]["cards"] > 50 and len(cards.data.polygons) == 2 * reply["twigs"]["cards"]
    closed_shell(bark, reply)


def test_bad_arguments_are_refused(bridge):
    bridge.ok("add_primitive", type="cube", name="Plain")
    bridge.refuse("tree_mesh", "bad_args", name="Plain")
    grow(bridge, "Grown")
    bridge.refuse("tree_mesh", "bad_args", name="Grown", ring_segments={"min": 12, "max": 8})
    bridge.refuse("tree_mesh", "bad_args", name="Grown", voxel_size=0.01)
    bridge.refuse("tree_mesh", "bad_args", name="Grown", view=[0.0, 0.0, 0.0])
    bridge.refuse("tree_mesh", "bad_args", name="Grown", min_radius=5.0)
    bridge.refuse("tree_mesh", "bad_args", name="Grown", mesh_name="Plain")


run(globals())
