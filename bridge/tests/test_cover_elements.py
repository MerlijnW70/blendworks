import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from cover_helpers import points_of

KINDS = ("grass", "tuft", "sedge", "flower", "twig", "leaf", "pebble")
GOLDEN = 360.0 * (1.0 - 2.0 / (1.0 + math.sqrt(5.0)))


def triangles_of(name):
    mesh = bpy.data.objects[name].data
    return sum(len(polygon.vertices) - 2 for polygon in mesh.polygons)


def uv_values(name):
    mesh = bpy.data.objects[name].data
    layer = mesh.uv_layers.get("UVMap")
    assert layer is not None, name
    values = numpy.empty(len(layer.uv) * 2)
    layer.uv.foreach_get("vector", values)
    return values


def colours(name):
    mesh = bpy.data.objects[name].data
    layer = mesh.color_attributes["wind"]
    values = numpy.empty(len(layer.data) * 4)
    layer.data.foreach_get("color", values)
    return values.reshape(-1, 4)


def test_every_kind_and_form_keeps_its_triangle_budget_with_uvs_and_preset_materials(bridge):
    for kind in KINDS:
        for form, budgets in (("geometry", (None, 60, 24)), ("cards", (None, 12))):
            for index, budget in enumerate(budgets):
                name = f"{kind}_{form}_{index}"
                extra = {} if budget is None else {"triangles": budget}
                if kind == "flower" and budget is not None and budget < 14:
                    extra = {"triangles": 14 if form == "geometry" else 12}
                result = bridge.ok("ground_element", kind=kind, form=form, name=name, seed=index, **extra)
                assert result["triangles"] == triangles_of(name) <= result["budget"], (name, result)
                assert result["triangles"] > 0
                uvs = uv_values(name)
                assert uvs.min() >= -1e-6 and uvs.max() <= 1.0 + 1e-6, name
                assert all(material is not None for material in bpy.data.objects[name].data.materials), name
    blade = bpy.data.objects["grass_geometry_0"].data.materials[0]
    card = bpy.data.objects["grass_cards_0"].data.materials[0]
    assert any(node.type == "ATTRIBUTE" and node.attribute_name == "gc_blade" for node in blade.node_tree.nodes)
    principled = next(node for node in card.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    assert principled.inputs["Alpha"].is_linked
    assert not next(node for node in blade.node_tree.nodes if node.type == "BSDF_PRINCIPLED").inputs["Alpha"].is_linked
    leaf_card = bpy.data.objects["leaf_cards_0"].data.materials[0]
    assert next(node for node in leaf_card.node_tree.nodes if node.type == "BSDF_PRINCIPLED").inputs["Alpha"].is_linked


def test_a_grass_clump_follows_its_blade_count_heights_and_dry_tip_share(bridge):
    params = {"blades": 200, "height": [0.2, 0.3], "dry_tips": 0.3, "spread": 0.05, "lean": 10.0, "curvature": 0.2}
    result = bridge.ok("ground_element", kind="grass", params=params, triangles=5000, name="Clump", seed=4)
    assert result["blades"] == 200
    points = points_of("Clump")
    assert points[:, 2].min() >= -1e-6 and points[:, 2].max() <= 0.3 + 1e-6
    mesh = bpy.data.objects["Clump"].data
    dry = numpy.empty(len(mesh.vertices))
    mesh.attributes["gc_dry"].data.foreach_get("value", dry)
    blade = numpy.empty(len(mesh.vertices))
    mesh.attributes["gc_blade"].data.foreach_get("value", blade)
    blades = {}
    for phase, start in zip(blade.tolist(), dry.tolist()):
        blades[phase] = start
    assert len(blades) == 200
    share = sum(1 for start in blades.values() if start < 1.5) / 200.0
    assert abs(share - 0.3) < 3.0 * math.sqrt(0.3 * 0.7 / 200.0) + 1e-9, share
    roots = points[points[:, 2] < 1e-6]
    assert numpy.linalg.norm(roots[:, :2], axis=1).max() <= 0.05 + 0.01
    thin = bridge.ok("ground_element", kind="grass", params={"blades": 200}, triangles=150, name="Thin", seed=4)
    assert thin["triangles"] <= 150 and thin["segments"] == 1


def test_flower_petals_turn_by_the_golden_angle(bridge):
    bridge.ok("ground_element", kind="flower", params={"petals": 21, "head_tilt": 0.0, "leaves": 0}, triangles=2000, name="Daisy", seed=2)
    mesh = bpy.data.objects["Daisy"].data
    owner = {}

    def root(index):
        while owner.get(index, index) != index:
            index = owner[index]
        return index

    petal_faces = [list(polygon.vertices) for polygon in mesh.polygons if polygon.material_index == 1]
    for corners in petal_faces:
        for corner in corners[1:]:
            owner[root(corner)] = root(corners[0])
    petals = {}
    for corners in petal_faces:
        petals.setdefault(root(corners[0]), set()).update(corners)
    groups = [numpy.array([mesh.vertices[index].co[:] for index in sorted(petals[key])]) for key in sorted(petals, key=lambda key: min(petals[key]))]
    disc = numpy.array([mesh.vertices[index].co[:] for polygon in mesh.polygons if polygon.material_index == 2 for index in polygon.vertices])
    centre = disc.mean(axis=0)
    axis = numpy.mean([numpy.array(polygon.normal[:]) for polygon in mesh.polygons if polygon.material_index == 2], axis=0)
    axis /= numpy.linalg.norm(axis)
    first = numpy.cross(axis, [1.0, 0.0, 0.0])
    first /= numpy.linalg.norm(first)
    second = numpy.cross(axis, first)
    tips = numpy.array([group[numpy.argmax(numpy.linalg.norm(group - centre, axis=1))] for group in groups])
    angles = numpy.degrees(numpy.arctan2((tips - centre) @ second, (tips - centre) @ first))
    steps = numpy.mod(numpy.diff(angles), 360.0)
    steps = numpy.where(steps > 180.0, 360.0 - steps, steps)
    assert len(groups) == 21
    assert numpy.all(numpy.abs(steps - GOLDEN) < 4.0), steps


def test_the_same_seed_gives_the_same_element_and_another_seed_another(bridge):
    for kind in KINDS:
        bridge.ok("ground_element", kind=kind, name=f"{kind}_a", seed=7)
        bridge.ok("ground_element", kind=kind, name=f"{kind}_b", seed=7)
        bridge.ok("ground_element", kind=kind, name=f"{kind}_c", seed=8)
        first, again, other = points_of(f"{kind}_a"), points_of(f"{kind}_b"), points_of(f"{kind}_c")
        assert numpy.array_equal(first, again), kind
        assert first.shape != other.shape or not numpy.allclose(first, other), kind


def test_wind_colours_bend_blades_from_root_to_tip_and_keep_litter_still(bridge):
    bridge.ok("ground_element", kind="grass", wind=True, name="Windy", seed=1)
    points, wind = points_of("Windy"), colours("Windy")
    assert bpy.data.objects["Windy"].data.color_attributes.active_color.name == "wind"
    roots = points[:, 2] < 1e-6
    assert numpy.allclose(wind[roots, 2], 0.0)
    assert wind[:, 2].max() > 0.99 and numpy.corrcoef(points[:, 2], wind[:, 2])[0, 1] > 0.8
    assert numpy.all(wind[:, 3] >= wind[:, 2] - 1e-6)
    assert len(numpy.unique(numpy.round(wind[:, 1], 6))) > 10
    for kind in ("twig", "leaf", "pebble"):
        bridge.ok("ground_element", kind=kind, wind=True, name=f"Still_{kind}", seed=1)
        assert numpy.allclose(colours(f"Still_{kind}")[:, 2], 0.0), kind
    bridge.ok("ground_element", kind="grass", name="Calm", seed=1)
    assert "wind" not in bpy.data.objects["Calm"].data.color_attributes


def test_ground_element_refuses_fields_of_another_kind_and_too_small_budgets(bridge):
    assert "petals" in bridge.refuse("ground_element", "bad_args", kind="grass", params={"petals": 5})
    assert "at least 14" in bridge.refuse("ground_element", "bad_args", kind="flower", triangles=10)
    assert "smallest, largest" in bridge.refuse("ground_element", "bad_args", kind="pebble", params={"size": [0.05, 0.01]})
    bridge.ok("ground_element", kind="leaf", name="Taken")
    assert "already exists" in bridge.refuse("ground_element", "bad_args", kind="leaf", name="Taken")


run(globals())
