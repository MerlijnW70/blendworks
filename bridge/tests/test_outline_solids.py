import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import euler, is_closed_manifold, open_edge_count, outward_normals, settled_snapshot, uv_is_clean, vertices, volume

PLATE = [[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]]
HOLE_A = [[1.0, 1.0], [1.0, 2.0], [2.0, 2.0], [2.0, 1.0]]
HOLE_B = [[2.5, 1.0], [2.5, 2.0], [3.5, 2.0], [3.5, 1.0]]
L_SHAPE = [[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [1.0, 1.0], [1.0, 2.0], [0.0, 2.0]]


def radii(name, z=None):
    return [math.hypot(vertex.x, vertex.y) for vertex in vertices(name) if z is None or abs(vertex.z - z) < 1e-9]


def test_plate_with_two_holes_has_the_expected_euler_characteristic(bridge):
    result = bridge.ok("extrude_outline", name="Plate", outline=PLATE, holes=[HOLE_A, HOLE_B], depth=0.5)
    assert result["mesh"]["vertices"] == 24 and result["holes"] == 2
    assert euler("Plate") == 2 - 2 * 2
    assert result["manifold"] is True and is_closed_manifold("Plate")
    close(volume("Plate"), (12.0 - 2.0) * 0.5, 1e-5)
    assert outward_normals("Plate") > 0.5
    close(list(bpy.data.objects["Plate"].dimensions), [4.0, 3.0, 0.5], 1e-6)


def test_plate_without_holes_is_a_box_and_winding_does_not_matter(bridge):
    result = bridge.ok("extrude_outline", name="Box", outline=PLATE, depth=0.5)
    assert euler("Box") == 2 and result["mesh"]["faces"] == 4 + 2 * 2
    close(volume("Box"), 6.0, 1e-5)
    bridge.ok("extrude_outline", name="Reversed", outline=list(reversed(PLATE)), holes=[list(reversed(HOLE_A))], depth=1.0)
    close(volume("Reversed"), 11.0, 1e-5)
    assert is_closed_manifold("Reversed")


def test_caps_false_leaves_an_open_wall(bridge):
    result = bridge.ok("extrude_outline", name="Duct", outline=PLATE, holes=[HOLE_A], depth=0.5, caps=False)
    assert result["manifold"] is False and result["mesh"]["faces"] == 8
    assert open_edge_count("Duct") == 16


def test_concave_outline_is_triangulated_correctly(bridge):
    result = bridge.ok("extrude_outline", name="L", outline=L_SHAPE, depth=1.0)
    close(volume("L"), 3.0, 1e-5)
    assert result["manifold"] is True and euler("L") == 2


def test_chamfer_matches_the_hand_worked_frustum_volume(bridge):
    bridge.ok("extrude_outline", name="Block", outline=[[-1, -1], [1, -1], [1, 1], [-1, 1]], depth=1.0, chamfer=0.1)
    inner = (2 - 0.2) ** 2
    frustum = 0.1 / 3.0 * (inner + math.sqrt(inner * 4.0) + 4.0)
    close(volume("Block"), 2 * frustum + 0.8 * 4.0, 1e-5)
    assert is_closed_manifold("Block")
    rounded = bridge.ok("extrude_outline", name="Soft", outline=[[-1, -1], [1, -1], [1, 1], [-1, 1]], depth=1.0, chamfer=0.1, bevel_segments=4)
    assert rounded["manifold"] is True
    assert volume("Soft") > volume("Block")


def test_centered_extrusion_straddles_z_zero(bridge):
    bridge.ok("extrude_outline", name="Slab", outline=PLATE, depth=0.5, centered=True)
    zs = [vertex.z for vertex in vertices("Slab")]
    close([min(zs), max(zs)], [-0.25, 0.25], 1e-6)


def test_outline_solid_uvs_are_clean(bridge):
    bridge.ok("extrude_outline", name="Plate", outline=PLATE, holes=[HOLE_A], depth=0.5, chamfer=0.05)
    uv_is_clean(bridge, "Plate")


def test_extrude_outline_refuses_bad_outlines(bridge):
    bow_tie = [[0, 0], [2, 2], [2, 0], [0, 2]]
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=bow_tie, depth=1.0)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=PLATE, holes=[[[5, 5], [5, 6], [6, 6]]], depth=1.0)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=PLATE, holes=[[[-1, 1], [1, 1], [1, 2], [-1, 2]]], depth=1.0)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=PLATE, holes=[HOLE_A, [[1.2, 1.2], [1.2, 1.8], [1.8, 1.8], [1.8, 1.2]]], depth=1.0)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=PLATE, holes=[HOLE_A, [[1.5, 1.5], [3.0, 1.5], [3.0, 2.5], [1.5, 2.5]]], depth=1.0)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=PLATE, depth=1.0, chamfer=0.6)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=[[0, 0], [1, 0], [1, 1], [0, 1]], depth=4.0, chamfer=0.9)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=[[0, 0], [1, 0], [2, 0]], depth=1.0)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=PLATE, depth=0.0)
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=PLATE)


def test_failed_extrusion_leaves_the_scene_unchanged(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    before = settled_snapshot()
    bridge.refuse("extrude_outline", "bad_args", name="A", outline=[[0, 0], [2, 2], [2, 0], [0, 2]], depth=1.0)
    assert settled_snapshot() == before


def test_gear_has_the_requested_teeth_outer_diameter_and_module(bridge):
    result = bridge.ok("gear", name="Gear", teeth=20, module=0.01, thickness=0.01)
    close(result["outer_diameter"], 0.01 * (20 + 2), 1e-12)
    close(result["pitch_diameter"], 0.2, 1e-12)
    close(result["root_diameter"], 0.01 * (20 - 2.5), 1e-12)
    assert result["module"] == 0.01 and result["teeth"] == 20
    ring = radii("Gear", 0.0)
    close(max(ring), 0.11, 1e-6)
    close(min(ring), 0.0875, 1e-6)
    tips = [value for value in ring if abs(value - 0.11) < 1e-6]
    assert len(tips) == 2 * 20
    assert result["manifold"] is True and is_closed_manifold("Gear")
    close(list(bpy.data.objects["Gear"].dimensions)[2], 0.01, 1e-7)


def test_gear_pitch_is_pi_times_module_and_phase_by_one_tooth_is_the_same_gear(bridge):
    result = bridge.ok("gear", name="Pitched", teeth=12, pitch=math.pi * 0.005, thickness=0.004)
    close(result["module"], 0.005, 1e-12)
    close(result["outer_diameter"], 0.005 * 14, 1e-12)
    bridge.ok("gear", name="A", teeth=12, module=0.005, thickness=0.004)
    bridge.ok("gear", name="B", teeth=12, module=0.005, thickness=0.004, phase=30.0)
    first = {(round(v.x, 5), round(v.y, 5), round(v.z, 5)) for v in vertices("A")}
    second = {(round(v.x, 5), round(v.y, 5), round(v.z, 5)) for v in vertices("B")}
    assert first == second


def test_gear_with_bore_chamfer_and_simple_teeth(bridge):
    bridge.ok("gear", name="Plain", teeth=12, module=0.01, thickness=0.01, tooth_profile="simple")
    assert len(vertices("Plain")) == 144
    result = bridge.ok("gear", name="Bored", teeth=20, module=0.01, thickness=0.01, bore=0.04, chamfer=0.0005)
    assert euler("Bored") == 0 and result["manifold"] is True
    bore = [value for value in radii("Bored") if abs(value - 0.02) < 1e-6]
    assert len(bore) == 48 * 2
    area_low = math.pi * 0.0875 ** 2
    area_high = math.pi * 0.11 ** 2
    assert (area_low - math.pi * 0.02 ** 2) * 0.01 * 0.95 < volume("Bored") < area_high * 0.01


def test_gear_refuses_bad_parameters(bridge):
    bridge.refuse("gear", "bad_args", name="A", teeth=20, thickness=0.01)
    bridge.refuse("gear", "bad_args", name="A", teeth=20, module=0.01, pitch=0.03, thickness=0.01)
    bridge.refuse("gear", "bad_args", name="A", teeth=5, module=0.01, thickness=0.01)
    bridge.refuse("gear", "bad_args", name="A", teeth=20, module=0.01, thickness=0.01, bore=0.2)
    bridge.refuse("gear", "bad_args", name="A", teeth=6, module=0.01, thickness=0.01, pressure_angle=35.0)
    bridge.refuse("gear", "bad_args", name="A", teeth=20, module=0.01, thickness=0.01, chamfer=0.01)


def test_sprocket_matches_roller_chain_geometry(bridge):
    pitch = 0.0127
    result = bridge.ok("sprocket", name="Sprocket", teeth=18, chain_pitch=pitch, thickness=0.005, bore=0.03)
    close(result["pitch_diameter"], pitch / math.sin(math.pi / 18), 1e-12)
    close(result["outer_diameter"], pitch * (0.6 + 1.0 / math.tan(math.pi / 18)), 1e-12)
    rings = radii("Sprocket", 0.0)
    close(max(rings), result["outer_diameter"] / 2.0, 1e-6)
    seat_radius = 0.625 * pitch / 2.0 * 1.01
    centre = (result["pitch_diameter"] / 2.0, 0.0)
    nearest = min(math.hypot(v.x - centre[0], v.y - centre[1]) for v in vertices("Sprocket") if abs(v.z) < 1e-9)
    assert nearest <= seat_radius + 1e-9
    seats = [math.hypot(v.x - centre[0], v.y - centre[1]) for v in vertices("Sprocket") if abs(v.z) < 1e-9 and math.hypot(v.x - centre[0], v.y - centre[1]) < seat_radius * 1.001]
    assert len(seats) == 9
    assert euler("Sprocket") == 0 and result["manifold"] is True


def test_sprocket_refuses_bad_parameters(bridge):
    bridge.refuse("sprocket", "bad_args", name="A", teeth=18, chain_pitch=0.0127, roller_diameter=0.0125, thickness=0.005)
    bridge.refuse("sprocket", "bad_args", name="A", teeth=18, chain_pitch=0.0127, thickness=0.005, bore=0.08)
    bridge.refuse("sprocket", "bad_args", name="A", teeth=4, chain_pitch=0.0127, thickness=0.005)
    bridge.refuse("sprocket", "bad_args", name="A", teeth=18, thickness=0.005)


run(globals())
