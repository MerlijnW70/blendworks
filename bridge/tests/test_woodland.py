import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy
from mathutils.kdtree import KDTree

from harness import run
from blendworks_bridge.cover_nodes import TRANSFORM
from blendworks_bridge.limits_woodland import WOODLAND_INSTANCE_BYTES, WOODLAND_TRIANGLE_BYTES

STANDS = [
    {"kind": "copse", "centre": [-20.0, 10.0], "radius": 14.0},
    {"kind": "forest", "outline": [[10.0, -10.0], [60.0, -10.0], [60.0, 50.0], [10.0, 50.0]]},
    {"kind": "hedgerow", "line": [[-60.0, -40.0], [60.0, -45.0]]},
]
CHEAP = {"species": ["oak"], "shrubs": ["hazel"], "variants": 1, "points_share": 0.06, "detail": "low", "understorey_variants": 2, "parallel": False}
GRASS = [{"name": "grass", "element": "grass", "density": 6.0, "params": {"blades": 4}, "attribute": {"name": "meadow_canopy", "range": [0.9, 0.1]}}]


def ground(bridge):
    bridge.ok("heightfield", name="land", size=[160.0, 160.0], resolution=81, seed=2, height=1.5, scale=60.0, octaves=2, hurst=0.6)
    bridge.ok("transform", name="land", location=[-80.0, -80.0, 0.0])
    bridge.ok("material_procedural", name="ground", grass_ground={})
    bridge.ok("assign_material", name="land", material="ground")


def instance_positions(name):
    obj = bpy.data.objects[name]
    values = numpy.zeros(len(obj.data.vertices) * 16, dtype=numpy.float32)
    obj.data.attributes[TRANSFORM].data.foreach_get("value", values)
    return values.reshape(-1, 4, 4)[:, 3, :3]


def canopy_values(points):
    land = bpy.data.objects["land"]
    values = numpy.zeros(len(land.data.vertices), dtype=numpy.float32)
    land.data.attributes["meadow_canopy"].data.foreach_get("value", values)
    tree = KDTree(len(land.data.vertices))
    for index, vertex in enumerate(land.data.vertices):
        world = land.matrix_world @ vertex.co
        tree.insert((world.x, world.y, 0.0), index)
    tree.balance()
    return numpy.array([values[tree.find((x, y, 0.0))[1]] for x, y in points[:, :2].tolist()]), values


def test_stands_are_instanced_variants_with_canopy_on_the_ground(bridge):
    ground(bridge)
    result = bridge.ok("woodland", ground=["land"], stands=STANDS, seed=3, **CHEAP)
    layers = result["layers"]
    for layer in ("trees", "shrubs", "herbs", "ferns"):
        assert layers[layer]["count"] > 0 and layers[layer]["object"], (layer, layers[layer])
        instancer = bpy.data.objects[layers[layer]["object"]]
        assert instancer.modifiers[0].type == "NODES" and len(instancer.data.vertices) == layers[layer]["count"]
        assert len(bpy.data.collections[f"Woodland_{layer}_variants"].objects) == layers[layer]["variants"]
    assert layers["trees"]["variants"] == 3 and layers["shrubs"]["variants"] == 1
    assert result["plants"] == sum(layer["count"] for layer in layers.values())
    stems = instance_positions(layers["trees"]["object"])
    under, values = canopy_values(stems)
    assert under.mean() > 0.6 and values.min() == 0.0, (under.mean(), values.min())
    assert result["canopy"]["shaded_materials"] == ["ground"]
    nodes = bpy.data.materials["ground"].node_tree.nodes
    assert sum(1 for node in nodes if node.type == "ATTRIBUTE" and node.attribute_name == "meadow_canopy") >= 2


def test_grass_under_the_canopy_is_sparser_than_in_the_open(bridge):
    ground(bridge)
    bridge.ok("woodland", ground=["land"], stands=STANDS, seed=3, **CHEAP)
    bridge.ok("ground_cover", target="land", name="Cover", populations=GRASS, seed=1, budget=200_000)
    blades = instance_positions("Cover_grass")
    at_blades, values = canopy_values(blades)
    shaded, open_ground = float((values > 0.7).mean()), float((values < 0.05).mean())
    under = float((at_blades > 0.7).mean()) / shaded
    outside = float((at_blades < 0.05).mean()) / open_ground
    assert under < 0.4 * outside, (under, outside)


def test_the_budgets_hold_and_refuse_what_does_not_fit(bridge):
    ground(bridge)
    message = bridge.refuse("woodland", "bad_args", ground=["land"], stands=STANDS, budget={"triangles": 1000}, **CHEAP)
    assert "budget.triangles" in message
    message = bridge.refuse("woodland", "bad_args", ground=["land"], stands=STANDS, budget={"plants": 50}, **CHEAP)
    assert "budget.plants" in message
    assert "Woodland" not in bpy.data.objects
    result = bridge.ok("woodland", ground=["land"], stands=STANDS, budget={"triangles": 3_000_000, "memory": 1_000_000_000}, **CHEAP)
    budget = result["budget"]
    assert budget["triangles"] <= 3_000_000 and budget["memory"] <= 1_000_000_000
    assert budget["memory"] == budget["triangles"] * WOODLAND_TRIANGLE_BYTES + budget["plants"] * WOODLAND_INSTANCE_BYTES
    measured = {**CHEAP, "species": ["maple"], "variants": 2, "detail": "full", "points_share": 1.0, "understorey": False}
    roomy = bridge.ok("woodland", name="Roomy", ground=["land"], stands=STANDS[:1], **measured)["budget"]
    tight = bridge.ok("woodland", name="Tight", ground=["land"], stands=STANDS[:1], budget={"triangles": roomy["estimated_triangles"] - 1}, **measured)["budget"]
    assert roomy["variants"]["mature"] == 2 and roomy["details"]["mature"] == "full"
    assert tight["estimated_triangles"] < roomy["estimated_triangles"] and (tight["details"] != roomy["details"] or tight["variants"] != roomy["variants"])
    assert tight["triangles"] <= roomy["estimated_triangles"] - 1
    unique = sum(len(obj.data.loop_triangles) for collection in bpy.data.collections if collection.name.startswith("Woodland_") and collection.name.endswith("_variants") for obj in collection.objects if not obj.data.calc_loop_triangles())
    assert unique == budget["triangles"]


def test_the_same_seed_repeats(bridge):
    ground(bridge)
    first = bridge.ok("woodland", ground=["land"], stands=STANDS, seed=5, **CHEAP)
    positions = {layer: instance_positions(first["layers"][layer]["object"]) for layer in ("trees", "shrubs")}
    bridge.ok("new_scene")
    ground(bridge)
    second = bridge.ok("woodland", ground=["land"], stands=STANDS, seed=5, **CHEAP)
    for layer in ("trees", "shrubs"):
        assert numpy.array_equal(positions[layer], instance_positions(second["layers"][layer]["object"])), layer
    assert first["budget"]["triangles"] == second["budget"]["triangles"]


run(globals())
