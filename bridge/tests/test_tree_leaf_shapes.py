import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy
from mathutils import Vector

from blendworks_bridge.tree_crown import render_alpha, setup_scene
from blendworks_bridge.tree_species import FOLIAGE, LEAF_MATERIALS, SPECIES_NAMES, foliage_settings
from blendworks_bridge.tree_sprays import SprayStyle, make_leaves

SIZE = 96
SHAPE_VALUES = (1.0 / 6.0, 0.5, 5.0 / 6.0)
LEAST_DIFFERENCE = 0.1


def outline(bridge, species, shape_value, folder):
    material = f"shape_{species}"
    if material not in bpy.data.materials:
        params = {**LEAF_MATERIALS[species], "cutout": True, "petiole": foliage_settings(species, {})["clusters"]["petiole"]}
        bridge.ok("material_procedural", name=material, leaf=params)
    card = bpy.data.objects.get("Card") or bridge.ok("add_primitive", type="plane", name="Card", size=1.0) and bpy.data.objects["Card"]
    card.data.materials.clear()
    card.data.materials.append(bpy.data.materials[material])
    card["leaf_shape"] = shape_value
    scene = setup_scene([card], SIZE, 4)
    data = bpy.data.cameras.new("shape-camera")
    data.type = "ORTHO"
    data.ortho_scale = 1.0
    camera = bpy.data.objects.new("shape-camera", data)
    scene.collection.objects.link(camera)
    camera.location = Vector((0.0, 0.0, 2.0))
    try:
        return render_alpha(scene, camera, folder, f"{species}-{shape_value:.2f}") > 0.5
    finally:
        bpy.data.objects.remove(camera)
        bpy.data.cameras.remove(data)
        bpy.data.scenes.remove(scene)


def difference(first, second):
    return float((first ^ second).sum() / max(1, (first | second).sum()))


def test_each_leaf_shape_value_cuts_a_different_outline_for_every_species(bridge, tmp_path=None):
    import tempfile

    bridge.ok("new_scene")
    with tempfile.TemporaryDirectory() as folder:
        for species in SPECIES_NAMES:
            masks = [outline(bridge, species, value, folder) for value in SHAPE_VALUES]
            assert all(mask.sum() > 0.02 * mask.size for mask in masks), species
            for first in range(3):
                for second in range(first + 1, 3):
                    assert difference(masks[first], masks[second]) > LEAST_DIFFERENCE, (species, first, second, difference(masks[first], masks[second]))


def test_the_shapes_of_a_species_differ_in_length_as_well(bridge):
    for species in SPECIES_NAMES:
        args = {**foliage_settings(species, {}), "seed": 1}
        style = SprayStyle(args)
        leaves = make_leaves(style, numpy.random.default_rng(1), type("Units", (), {"length": numpy.full(400, 0.2), "rotation": numpy.broadcast_to(numpy.identity(3), (400, 3, 3)), "origin": numpy.zeros((400, 3)), "spray": numpy.arange(400), "scale": numpy.ones(400)})())
        means = [leaves.length[leaves.shape == shape].mean() / leaves.blade[leaves.shape == shape].mean() for shape in range(style.shapes)]
        assert max(means) > 1.3 * min(means), (species, means)


run(globals())
