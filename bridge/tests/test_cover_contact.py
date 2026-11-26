import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy
from mathutils import Vector

from cover_helpers import attribute_of, base_points, evaluated_instances, make_plane, make_soil, points_of, surface_below, world_tree

FLOAT_TOLERANCE = 2e-4
THIN_LITTER = 0.004
BAKE_SIZE = 32
CONTACT_FLOOR = 0.64
SAMPLE = 400


def hill(bridge):
    bridge.ok("heightfield", name="Hill", size=[16.0, 16.0], resolution=65, height=3.0, scale=10.0, octaves=3, seed=8)


def test_element_bases_sit_on_or_below_the_surface_on_a_slope_and_tilt_with_it(bridge):
    hill(bridge)
    populations = [
        {"name": "grass", "element": "grass", "density": 3.0, "form": "auto", "card_distance": 6.0, "variants": 2, "align": 0.5, "tilt": 10.0},
        {"name": "leaves", "element": "leaf", "density": 2.0, "variants": 2},
        {"name": "stones", "element": "pebble", "density": 1.0, "variants": 2},
        {"name": "twigs", "element": "twig", "density": 0.5, "variants": 2},
    ]
    bridge.ok("ground_cover", target="Hill", populations=populations, point=[8.0, 8.0, 2.0], near=4.0, seed=6)
    tree = world_tree("Hill")
    highest, lowest_base, checked = -math.inf, -math.inf, 0
    depths = {}
    tilts = []
    for population in ("grass", "leaves", "stones", "twigs"):
        instances = evaluated_instances(f"GroundCover_{population}")
        assert len(instances) == len(points_of(f"GroundCover_{population}"))
        for matrix, mesh_name in instances[:SAMPLE]:
            local = base_points(mesh_name)
            world = local @ matrix[:3, :3].T + matrix[:3, 3]
            raised = (local[:, 2] - local[:, 2].min()) * numpy.linalg.norm(matrix[:3, 2])
            gaps = []
            for point, lift in zip(world, raised):
                location, _ = surface_below(tree, point)
                if location is not None:
                    gaps.append(point[2] - location.z - lift)
            if gaps:
                highest = max(highest, max(gaps))
                lowest_base = max(lowest_base, min(gaps))
                checked += len(gaps)
            height = numpy.ptp([vertex.co.z for vertex in bpy.data.meshes[mesh_name].vertices]) * numpy.linalg.norm(matrix[:3, 2])
            location, _ = surface_below(tree, matrix[:3, 3])
            if location is not None:
                depths.setdefault(population, []).append((location.z - matrix[2, 3]) - 0.5 * height)
            if population == "leaves":
                _, normal, _, _ = tree.find_nearest(Vector(matrix[:3, 3]))
                axis = matrix[:3, 2] / numpy.linalg.norm(matrix[:3, 2])
                tilts.append(math.degrees(math.acos(min(1.0, abs(float(numpy.dot(axis, normal)))))))
    assert checked > 2000
    assert highest <= FLOAT_TOLERANCE + 1e-3, highest
    assert lowest_base <= FLOAT_TOLERANCE, lowest_base
    for population, shares in depths.items():
        assert numpy.percentile(shares, 90) < THIN_LITTER, (population, numpy.percentile(shares, 90))
    assert numpy.median(tilts) < 6.0, numpy.median(tilts)


def test_dense_cover_writes_a_contact_attribute_that_darkens_the_ground_material(bridge):
    make_plane(bridge, size=10.0, cuts=8)
    make_soil(bridge)
    bridge.ok("add_primitive", type="cube", name="Marker", size=0.2, location=[-2.5, 0.0, 2.0])
    result = bridge.ok("ground_cover", target="Ground", seed=1, populations=[
        {"name": "patch", "element": "grass", "density": 40.0, "variants": 1, "form": "cards", "distance": [{"objects": ["Marker"], "max": 3.0}]},
    ])
    assert result["contact"]["attribute"] == "cover_density" and result["contact"]["darkened"] == ["Soil"]
    values = attribute_of("Ground", "cover_density")
    vertices = points_of("Ground")
    near = numpy.linalg.norm(vertices[:, :2] - [-2.5, 0.0], axis=1) < 1.0
    far = vertices[:, 0] > 2.5
    assert values[near].mean() > 0.5 and values[far].max() < 0.05, (values[near].mean(), values[far].max())
    material = bpy.data.materials["Soil"]
    nodes = material.node_tree.nodes
    mix = nodes["gc_contact_mix"]
    principled = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    assert principled.inputs["Base Color"].links[0].from_node == mix
    assert nodes["gc_contact_attribute"].attribute_name == "cover_density"
    assert abs(nodes["gc_contact_strength"].inputs[1].default_value - 0.2) < 1e-6
    count = len(nodes)
    assert "darken" in bridge.refuse("ground_cover", "bad_args", target="Ground", name="Black", darken=0.5, populations=[{"name": "patch", "element": "tuft", "density": 5.0}])
    bridge.ok("ground_cover", target="Ground", name="Again", seed=2, darken=0.3, populations=[{"name": "patch", "element": "tuft", "density": 5.0, "variants": 1, "form": "cards"}])
    assert len(nodes) == count and abs(nodes["gc_contact_strength"].inputs[1].default_value - 0.3) < 1e-6
    calm = bridge.ok("ground_cover", target="Ground", name="Calm", darken=0.0, contact_attribute="calm_cover", populations=[{"name": "patch", "element": "tuft", "density": 5.0, "variants": 1, "form": "cards"}])
    assert calm["contact"]["darkened"] == [] and "calm_cover" in bpy.data.objects["Ground"].data.attributes


def baked_halves(bridge):
    bridge.ok("bake", names=["Ground"], channels=["base_color"], size=BAKE_SIZE, device="cpu", overwrite=True, samples={"base_color": 1}, time_limit=600.0, float_buffer=True)
    pixels = numpy.array(bpy.data.images["Ground_base_color"].pixels[:]).reshape(BAKE_SIZE, BAKE_SIZE, 4)[:, :, :3]
    luminance = pixels @ numpy.array([0.2126, 0.7152, 0.0722])
    eighth = BAKE_SIZE // 8
    return float(luminance[:, :eighth].mean()), float(luminance[:, -eighth:].mean())


def test_ground_darkening_is_a_bounded_multiplier_above_the_calibrated_floor(bridge):
    make_plane(bridge, size=10.0, cuts=8)
    bridge.ok("material_procedural", name="Soil", soil={"pebbles": 0.0})
    bridge.ok("assign_material", name="Ground", material="Soil")
    plain_left, plain_right = baked_halves(bridge)
    bridge.ok("add_primitive", type="cube", name="Marker", size=0.2, location=[-6.0, 0.0, 0.0])
    bridge.ok("transform", name="Marker", scale=[1.0, 80.0, 1.0])
    patch = [{"name": "patch", "element": "grass", "density": 60.0, "variants": 1, "form": "cards", "distance": [{"objects": ["Marker"], "max": 3.0}]}]
    result = bridge.ok("ground_cover", target="Ground", seed=1, darken=0.36, populations=patch)
    assert result["contact"]["darkened"] == ["Soil"]
    values = attribute_of("Ground", "cover_density")
    assert values.max() > 0.95
    covered_left, covered_right = baked_halves(bridge)
    left_ratio, right_ratio = covered_left / plain_left, covered_right / plain_right
    assert CONTACT_FLOOR - 0.02 <= min(left_ratio, right_ratio), (left_ratio, right_ratio)
    assert left_ratio < 0.9 and right_ratio > 0.97, (left_ratio, right_ratio)


def test_cover_thins_gradually_towards_an_obstacle_instead_of_stopping_at_a_hard_edge(bridge):
    make_plane(bridge, size=4.0)
    bridge.ok("add_primitive", type="cylinder", name="Trunk", radius=0.3, depth=2.0, segments=32, location=[0.0, 0.0, 0.5])
    population = {"name": "grass", "element": "grass", "density": 200.0, "variants": 1, "form": "cards", "avoid": 0.1, "avoid_falloff": 0.4}
    bridge.ok("ground_cover", target="Ground", obstacles=["Trunk"], populations=[population], seed=3)
    gap = numpy.linalg.norm(points_of("GroundCover_grass")[:, :2], axis=1) - 0.3
    shares = []
    for low in (0.1, 0.2, 0.3, 0.4):
        inside = (gap >= low) & (gap < low + 0.1)
        area = math.pi * ((0.3 + low + 0.1) ** 2 - (0.3 + low) ** 2)
        shares.append(inside.sum() / area / 200.0)
    full = ((gap > 0.7) & (numpy.abs(points_of("GroundCover_grass")).max(axis=1) < 1.8)).sum()
    assert gap.min() >= 0.1 - 0.01
    assert 0.05 < shares[0] < 0.35 and 0.3 < shares[1] < 0.7 and 0.5 < shares[2] < 0.95, shares
    assert all(later > earlier for earlier, later in zip(shares, shares[1:])), shares
    assert full > 0


def test_a_target_whose_modifiers_change_its_vertices_gets_no_contact_attribute(bridge):
    make_plane(bridge, size=4.0)
    make_soil(bridge)
    bridge.ok("add_modifier", name="Ground", solidify={"thickness": 0.05, "offset": -1.0})
    result = bridge.ok("ground_cover", target="Ground", populations=[{"name": "g", "element": "tuft", "density": 5.0, "variants": 1, "form": "cards"}])
    assert result["contact"]["attribute"] is None and "vertex count" in result["contact"]["note"]
    assert "cover_density" not in bpy.data.objects["Ground"].data.attributes
    assert "gc_contact_mix" not in bpy.data.materials["Soil"].node_tree.nodes


run(globals())
