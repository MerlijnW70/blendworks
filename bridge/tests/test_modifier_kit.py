import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import settled_snapshot, vertices

CASES = {
    "displace": {"strength": 0.1, "texture": {"type": "clouds", "size": 0.5, "depth": 2}, "mid_level": 0.5},
    "weld": {"distance": 0.001, "mode": "all"},
    "screw": {"angle": 360.0, "steps": 8, "axis": "z"},
    "curve": {"curve": "Rail", "axis": "pos_x"},
    "simple_deform": {"method": "taper", "factor": 0.5, "axis": "z"},
    "wireframe": {"thickness": 0.05},
    "lattice": {"lattice": "Cage", "strength": 0.5},
    "shrinkwrap": {"target": "Ball", "method": "nearest_surfacepoint"},
    "triangulate": {"quad_method": "beauty", "min_vertices": 4},
    "weighted_normal": {"mode": "face_area", "weight": 50, "keep_sharp": True},
    "bevel": {"width": 0.1, "segments": 1, "limit_method": "angle", "angle": 30.0},
    "solidify": {"thickness": 0.1, "offset": -1.0},
}


def scene(bridge, twin=True):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("add_primitive", type="sphere", name="Ball", radius=1.0, location=[6.0, 0.0, 0.0])
    bridge.ok("curve_from_points", name="Rail", points=[[0, 0, 0], [0, 2, 0], [0, 4, 0]])
    lattice = bpy.data.objects.new("Cage", bpy.data.lattices.new("Cage"))
    bpy.context.scene.collection.objects.link(lattice)
    if twin:
        bridge.ok("duplicate", name="Box", new_name="Twin", linked=True)


def test_every_whitelisted_modifier_can_be_added_live(bridge):
    scene(bridge)
    for kind, settings in CASES.items():
        result = bridge.ok("add_modifier", name="Box", modifier_name=f"M_{kind}", **{kind: settings})
        assert result["kind"] == kind and result["modifier"] == f"M_{kind}" and result["applied"] is False
        assert result["evaluated_mesh"]["faces"] > 0
    assert [modifier.name for modifier in bpy.data.objects["Box"].modifiers] == [f"M_{kind}" for kind in CASES]


def test_every_modifier_refuses_unknown_fields(bridge):
    scene(bridge)
    for kind in CASES:
        message = bridge.refuse("add_modifier", "bad_args", name="Box", **{kind: {"bogus_field": 1}})
        assert "bogus_field" in message, kind
    assert bpy.data.objects["Box"].modifiers.keys() == []


def test_every_modifier_rolls_back_when_it_fails_to_apply(bridge):
    scene(bridge)
    before = settled_snapshot()
    textures = len(bpy.data.textures)
    for kind, settings in CASES.items():
        message = bridge.refuse("add_modifier", "bad_args", name="Twin", apply=True, **{kind: settings})
        assert "shares its mesh" in message, kind
        assert settled_snapshot() == before, kind
        assert len(bpy.data.textures) == textures, kind
    assert bpy.data.objects["Twin"].modifiers.keys() == []


def test_add_modifier_needs_exactly_one_kind(bridge):
    scene(bridge)
    bridge.refuse("add_modifier", "bad_args", name="Box")
    bridge.refuse("add_modifier", "bad_args", name="Box", weld={}, triangulate={})
    bridge.refuse("add_modifier", "bad_args", name="Box", weld={"mode": "sideways"})
    bridge.refuse("add_modifier", "bad_args", name="Box", weld={"distance": -1.0})
    bridge.refuse("add_modifier", "bad_args", name="Box", curve={})
    bridge.refuse("add_modifier", "not_found", name="Ghost", weld={})


def test_modifier_targets_are_checked(bridge):
    scene(bridge)
    bridge.refuse("add_modifier", "not_found", name="Box", curve={"curve": "Ghost"})
    bridge.refuse("add_modifier", "bad_args", name="Box", curve={"curve": "Ball"})
    bridge.refuse("add_modifier", "bad_args", name="Box", lattice={"lattice": "Ball"})
    bridge.refuse("add_modifier", "bad_args", name="Box", shrinkwrap={"target": "Box"})
    bridge.refuse("add_modifier", "bad_args", name="Box", shrinkwrap={"target": "Rail"})
    bridge.refuse("add_modifier", "not_found", name="Box", weld={"vertex_group": "Missing"})
    bridge.refuse("add_modifier", "bad_args", name="Box", displace={"texture": {"type": "voronoi", "depth": 2}})
    bridge.refuse("add_modifier", "bad_args", name="Box", displace={"texture_object": "Ball"})
    assert bpy.data.objects["Box"].modifiers.keys() == []
    assert len(bpy.data.textures) == 0


def test_weld_merges_duplicate_vertices(bridge):
    vertices_data = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [1, 0, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]]
    bridge.ok("mesh_from_data", name="Strip", vertices=vertices_data, faces=[[0, 1, 2, 3], [4, 5, 6, 7]])
    result = bridge.ok("add_modifier", name="Strip", weld={"distance": 0.001}, apply=True)
    assert result["applied"] is True and result["mesh"]["vertices"] == 6 and result["mesh"]["faces"] == 2


def test_triangulate_splits_every_quad(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    result = bridge.ok("add_modifier", name="Box", triangulate={}, apply=True)
    assert result["mesh"]["faces"] == 12 and result["mesh"]["triangles"] == 12


def test_bevel_modifier_gives_the_hand_counted_chamfer(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    result = bridge.ok("add_modifier", name="Box", bevel=CASES["bevel"], apply=True)
    assert result["mesh"] == {"vertices": 24, "edges": 48, "faces": 26, "triangles": 44}


def test_growing_modifiers_are_refused_before_blender_builds_them(bridge):
    bridge.ok("add_primitive", type="sphere", name="Ball", segments=256, rings=128)
    message = bridge.refuse("add_modifier", "bad_args", name="Ball", bevel={"segments": 100, "limit_method": "none", "width": 0.001})
    assert "mesh_vertices limit is 2000000" in message and "Lower segments" in message, message
    assert len(bpy.data.objects["Ball"].modifiers) == 0
    bridge.ok("mesh_from_data", name="Edge", vertices=[[1, 0, 0], [1, 0, 1]], edges=[[0, 1]])
    message = bridge.refuse("add_modifier", "bad_args", name="Edge", screw={"steps": 10_000, "iterations": 10_000}, apply=True)
    assert "at least 200000000 vertices" in message and "Lower steps or iterations" in message, message
    assert len(bpy.data.objects["Edge"].modifiers) == 0


def test_solidify_gives_a_plane_thickness(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=2.0)
    result = bridge.ok("add_modifier", name="Sheet", solidify={"thickness": 0.1, "offset": -1.0})
    assert result["evaluated_mesh"]["vertices"] == 8 and result["evaluated_mesh"]["faces"] == 6
    zs = [vertex.z for vertex in vertices("Sheet")]
    assert max(zs) == 0.0
    close(bpy.data.objects["Sheet"].dimensions[2], 0.1, 1e-6)


def test_displace_uses_a_built_in_noise_texture_within_its_range(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=2.0)
    bridge.ok("subdivide", name="Sheet", cuts=10)
    result = bridge.ok("add_modifier", name="Sheet", displace={"strength": 0.2, "mid_level": 0.5, "texture": {"type": "clouds", "size": 0.4}}, apply=True)
    zs = [vertex.z for vertex in vertices("Sheet")]
    assert result["applied"] is True and max(zs) > 0.001 and min(zs) < -0.001
    assert max(abs(z) for z in zs) <= 0.2 * 0.5 + 1e-6
    assert [texture.type for texture in bpy.data.textures] == ["CLOUDS"]


def test_shrinkwrap_snaps_a_sheet_onto_a_sphere(bridge):
    bridge.ok("add_primitive", type="sphere", name="Ball", radius=1.0, segments=48, rings=24)
    bridge.ok("add_primitive", type="plane", name="Sheet", size=1.0, location=[0.0, 0.0, 3.0])
    bridge.ok("subdivide", name="Sheet", cuts=8)
    bridge.ok("add_modifier", name="Sheet", shrinkwrap={"target": "Ball", "method": "nearest_surfacepoint"}, apply=True)
    radii = [(bpy.data.objects["Sheet"].matrix_world @ vertex).length for vertex in vertices("Sheet")]
    assert min(radii) > 0.99 and max(radii) < 1.0 + 1e-6


def test_curve_modifier_bends_a_bar_along_the_curve(bridge):
    bridge.ok("add_primitive", type="cube", name="Bar", size=1.0)
    bridge.ok("transform", name="Bar", scale=[4.0, 0.2, 0.2])
    bridge.ok("apply_transform", name="Bar")
    bridge.ok("subdivide", name="Bar", cuts=8)
    bridge.ok("curve_from_points", name="Rail", points=[[0, 0, 0], [0, 2, 0], [0, 4, 0]])
    bridge.ok("add_modifier", name="Bar", curve={"curve": "Rail", "axis": "pos_x"}, apply=True)
    size = bpy.data.objects["Bar"].dimensions
    assert size[1] > 3.0 and size[0] < 1.0


def test_screw_turns_an_edge_into_a_cylinder_wall(bridge):
    bridge.ok("mesh_from_data", name="Edge", vertices=[[1, 0, 0], [1, 0, 1]], edges=[[0, 1]])
    result = bridge.ok("add_modifier", name="Edge", screw={"angle": 360.0, "steps": 8, "axis": "z", "merge": True}, apply=True)
    assert result["mesh"]["faces"] == 8


def test_simple_deform_and_lattice_and_wireframe_change_the_mesh(bridge):
    scene(bridge, twin=False)
    bridge.ok("add_modifier", name="Box", simple_deform={"method": "taper", "factor": 0.5, "axis": "z"}, apply=True)
    for vertex in vertices("Box"):
        close(abs(vertex.x), 1.25 if vertex.z > 0 else 0.75, 1e-6)
    bridge.ok("add_primitive", type="cube", name="Frame", size=2.0, location=[-6.0, 0.0, 0.0])
    wire = bridge.ok("add_modifier", name="Frame", wireframe={"thickness": 0.05})
    assert wire["evaluated_mesh"]["faces"] > 6 * 2
    cage = bridge.ok("add_modifier", name="Ball", lattice={"lattice": "Cage"})
    assert cage["evaluated_mesh"]["vertices"] == len(bpy.data.objects["Ball"].data.vertices)


def test_apply_modifier_applies_what_add_modifier_added(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("add_modifier", name="Box", bevel={"width": 0.1, "segments": 1, "limit_method": "angle"})
    bridge.ok("add_modifier", name="Box", triangulate={})
    assert bridge.info("Box")["mesh"]["vertices"] == 8
    result = bridge.ok("apply_modifier", name="Box")
    assert result["applied"] == ["Bevel", "Triangulate"]
    assert bridge.info("Box")["mesh"]["vertices"] == 24 and bridge.info("Box")["modifiers"] == []


def test_apply_modifier_rolls_back_when_the_mesh_is_shared(bridge):
    scene(bridge)
    bridge.ok("add_modifier", name="Twin", weld={"distance": 0.001})
    before = settled_snapshot()
    bridge.refuse("apply_modifier", "bad_args", name="Twin", modifier="Weld")
    assert settled_snapshot() == before


run(globals())
