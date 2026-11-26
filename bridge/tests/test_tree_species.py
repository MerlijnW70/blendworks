import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run
from natural_stats import baked_pixels

import bpy
import numpy

from blendworks_bridge.tree_presets import SPECIES
from blendworks_bridge.tree_species import BARK_MATERIALS, FOLIAGE, LEAF_MATERIALS, SPECIES_NAMES, SPECIES_PROPERTY

SMALL = {"oak": {"points": 900}, "maple": {"points": 700}, "olive": {"points": 700}, "birch": {"branches": [10, 8, 3]}, "pine": {"branches": [12, 8, 3]}, "willow": {"branches": [6, 16, 2]}}


def principled(material):
    return next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")


def attribute_names(material):
    return {node.attribute_name for node in material.node_tree.nodes if node.type == "ATTRIBUTE"}


def test_every_species_preset_combines_skeleton_bark_leaves_and_twigs(bridge):
    assert set(SPECIES) == set(SPECIES_NAMES) == set(FOLIAGE) == set(LEAF_MATERIALS)
    for species in SPECIES_NAMES:
        bridge.ok("new_scene")
        grown = bridge.ok("grow_tree", name="Tree", preset=species, seed=2, limit=0, **SMALL[species])
        assert grown["species"] == species and grown["pipe_error"] < 1e-6
        assert bpy.data.objects["Tree"][SPECIES_PROPERTY] == species
        mesh = bridge.ok("tree_mesh", name="Tree", min_radius=0.012)
        assert mesh["manifold"] and mesh["shells"] == 1, (species, mesh)
        assert mesh["materials"][0] == f"{species}_bark"
        bark = bpy.data.objects[mesh["name"]]
        assert bark[SPECIES_PROPERTY] == species
        assert any(node.type == "TEX_NOISE" for node in bpy.data.materials[f"{species}_bark"].node_tree.nodes)
        leaves = bridge.ok("tree_leaves", name=mesh["name"])
        assert leaves["species"] == species and leaves["layout"] == "clusters"
        assert leaves["material"] == f"{species}_leaf" and leaves["twig_material"] == f"{species}_bark"
        material = bpy.data.materials[f"{species}_leaf"]
        shader = principled(material)
        assert shader.inputs["Thin Wall"].default_value and shader.inputs["Subsurface Weight"].default_value > 0.0
        assert shader.inputs["Alpha"].is_linked
        assert {"leaf_hue", "leaf_saturation", "leaf_value", "leaf_age", "leaf_damage", "leaf_shape", "leaf_seed"} <= attribute_names(material)
        foliage = bpy.data.objects[leaves["name"]]
        assert [slot.material.name for slot in foliage.material_slots] == [f"{species}_leaf", f"{species}_bark"]
        shapes = numpy.zeros(len(foliage.data.polygons), dtype=numpy.float32)
        foliage.data.attributes["leaf_shape"].data.foreach_get("value", shapes)
        assert len(numpy.unique(shapes[shapes > 0.0])) >= 3, species
        assert leaves["variation"]["shapes"] >= 3


def test_species_differ_in_leaf_layout_and_willow_clusters_hang(bridge):
    bridge.ok("grow_tree", name="Tree", preset="maple", seed=2, limit=0, points=500)
    hanging = {}
    for species in ("willow", "maple", "pine"):
        reply = bridge.ok("tree_leaves", name="Tree", leaves_name=species, species=species, realize=False, variants=2)
        copies = [obj for obj in bpy.data.objects if obj.parent is not None and obj.parent.name == species]
        hanging[species] = float(numpy.mean([obj.matrix_world.to_3x3().normalized().col[0][2] for obj in copies]))
        variant = bpy.data.meshes[reply["variants"][0]]
        leafy = sum(1 for polygon in variant.polygons if polygon.material_index == 0)
        per_leaf = {"willow": 2, "maple": 8, "pine": 2}[species]
        assert leafy % per_leaf == 0, (species, leafy)
    assert hanging["willow"] < -0.6 < hanging["maple"], hanging



def bark_at(bridge, material, height):
    name = f"{material}_{int(height)}"
    bridge.ok("add_primitive", type="plane", name=name, size=0.5)
    mesh = bpy.data.objects[name].data
    for vertex in mesh.vertices:
        vertex.co.z += height
    bridge.ok("assign_material", name=name, material=material)
    bridge.ok("bake", names=[name], channels=["base_color"], size=32, device="cpu", overwrite=True, samples={"base_color": 1}, time_limit=600.0)
    return baked_pixels(f"{name}_base_color", 32).reshape(-1, 3).mean(axis=0)


def test_the_pine_bark_turns_from_grey_brown_furrows_low_down_to_orange_flakes_up_the_trunk(bridge):
    bridge.ok("new_scene")
    pine = BARK_MATERIALS["pine"]
    assert pine["upper_start"] < pine["upper_end"] < SPECIES["pine"]["height"]
    bridge.ok("material_procedural", name="Pine", bark={**pine, "coordinates": "uv", "grain": "y"})
    bridge.ok("material_procedural", name="Plain", bark={**pine, "upper_end": 0.0, "coordinates": "uv", "grain": "y"})
    low, high = bark_at(bridge, "Pine", 1.0), bark_at(bridge, "Pine", 12.0)
    assert high[0] / high[1] > 1.25 * low[0] / low[1] and high[0] > 1.5 * low[0], (low, high)
    still_low, still_high = bark_at(bridge, "Plain", 1.0), bark_at(bridge, "Plain", 12.0)
    assert numpy.abs(still_high - still_low).max() < 0.03, (still_low, still_high)

run(globals())
