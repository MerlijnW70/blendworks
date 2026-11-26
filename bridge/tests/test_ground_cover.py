import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from cover_helpers import attribute_of, evaluated_instances, make_plane, points_of

PRESETS = {
    "meadow": {"short_grass", "tall_grass", "sedges", "daisies", "buttercups", "knapweed", "fallen_leaves", "twigs", "pebbles", "base_tufts", "base_pebbles", "thatch", "dead_leaves", "dead_twigs"},
    "forest_floor": {"leaf_litter", "twigs", "pebbles", "grass_tufts", "sedges", "base_tufts"},
    "dry_steppe": {"bunch_grass", "dry_tufts", "pebbles", "twigs", "base_pebbles", "yellow_flowers"},
    "lawn": {"lawn_grass", "daisies"},
}


def test_every_preset_covers_a_plot_with_its_populations(bridge):
    make_plane(bridge, size=8.0)
    bridge.ok("add_primitive", type="cylinder", name="Trunk", radius=0.2, depth=2.0, location=[1.0, 1.0, 1.0])
    for preset, names in PRESETS.items():
        result = bridge.ok("ground_cover", target="Ground", name=preset, preset=preset, density_scale=0.3, trees=["Trunk"], obstacles=["Trunk"], seed=2, budget=40_000)
        reported = {entry["name"] for entry in result["populations"]}
        assert reported == names, (preset, reported)
        assert result["count"] == sum(len(points_of(name)) for name in result["objects"])
        assert all(entry["triangles_per_element"] and max(entry["triangles_per_element"]) <= 400 for entry in result["populations"])
        assert bpy.data.collections[f"{preset}_elements"].children


def test_auto_form_uses_geometry_near_and_cards_far_and_view_only_keeps_what_the_camera_sees(bridge):
    make_plane(bridge, size=30.0)
    bridge.ok("add_camera", name="Eye", location=[0.0, -14.0, 1.0])
    bridge.ok("look_at", name="Eye", point=[0.0, 0.0, 0.0])
    populations = [{"name": "grass", "element": "grass", "density": 4.0, "variants": 2, "card_distance": 5.0, "triangles": 60}]
    result = bridge.ok("ground_cover", target="Ground", populations=populations, camera="Eye", near=6.0, view_only=True, seed=3)
    points = points_of("GroundCover_grass")
    picks = attribute_of("GroundCover_grass", "gc_pick")
    distances = numpy.linalg.norm(points - [0.0, -14.0, 1.0], axis=1)
    assert numpy.all(picks[distances < 4.9] < 2) and numpy.all(picks[distances > 5.1] >= 2)
    assert 0.0 < result["populations"][0]["card_share"] < 1.0
    assert points[:, 1].min() > -14.0 and numpy.abs(points[:, 0]).max() < 15.0
    behind = points[:, 1] < -13.0
    assert behind.sum() < 0.02 * len(points)
    assert bpy.context.scene.cycles.transparent_max_bounces >= 512
    meshes = {mesh for _, mesh in evaluated_instances("GroundCover_grass")}
    geometry, cards = {"GroundCover_grass_e000", "GroundCover_grass_e001"}, {"GroundCover_grass_e002", "GroundCover_grass_e003"}
    assert meshes <= geometry | cards and meshes & geometry and meshes & cards


def test_colour_variation_tints_instances_and_realize_merges_them(bridge):
    make_plane(bridge, size=6.0)
    populations = [{"name": "tufts", "element": "tuft", "density": 6.0, "variants": 1, "form": "cards", "color_variation": 0.4}]
    bridge.ok("ground_cover", target="Ground", populations=populations, seed=1, wind=True)
    tint = attribute_of("GroundCover_tufts", "gc_tint")
    assert tint.min() >= -0.4 - 1e-6 and tint.max() <= 0.4 + 1e-6 and tint.std() > 0.15
    element = bpy.data.objects["GroundCover_tufts_e000"]
    assert element.data.color_attributes.active_color.name == "wind"
    material = element.data.materials[0]
    assert any(node.type == "ATTRIBUTE" and node.attribute_type == "INSTANCER" and node.attribute_name == "gc_tint" for node in material.node_tree.nodes)
    bridge.ok("ground_cover", target="Ground", name="Merged", populations=populations, seed=1, realize=True)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    merged = bpy.data.objects["Merged_tufts"].evaluated_get(depsgraph)
    assert len(merged.data.polygons) == len(points_of("Merged_tufts")) * len(element.data.polygons)
    assert not evaluated_instances("Merged_tufts")
    layer = bpy.context.view_layer.layer_collection.children["GroundCover_elements"]
    assert layer.exclude


run(globals())
