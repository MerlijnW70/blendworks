import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import settled_snapshot, vertices

AMPLITUDE = 0.05


def sheet(bridge, name="Sheet"):
    bridge.ok("add_primitive", type="plane", name=name, size=2.0)
    bridge.ok("subdivide", name=name, cuts=10)


def positions(name):
    return [tuple(round(c, 7) for c in vertex) for vertex in vertices(name)]


def test_jitter_is_bounded_and_follows_the_normals(bridge):
    sheet(bridge)
    before = positions("Sheet")
    result = bridge.ok("displace_noise", name="Sheet", amplitude=AMPLITUDE, seed=7)
    assert result["displaced_vertices"] == 144 and result["max_displacement"] <= AMPLITUDE + 1e-7
    after = positions("Sheet")
    moved = 0
    for old, new in zip(before, after):
        close(new[:2], old[:2], 1e-6)
        assert abs(new[2]) <= AMPLITUDE + 1e-6
        moved += abs(new[2]) > 1e-6
    assert moved > 100
    assert max(abs(new[2]) for new in after) > AMPLITUDE * 0.7


def test_jitter_in_any_direction_stays_inside_the_amplitude_ball(bridge):
    sheet(bridge)
    before = positions("Sheet")
    bridge.ok("displace_noise", name="Sheet", amplitude=AMPLITUDE, seed=1, direction="any")
    after = positions("Sheet")
    lengths = [sum((a - b) ** 2 for a, b in zip(old, new)) ** 0.5 for old, new in zip(before, after)]
    assert max(lengths) <= AMPLITUDE + 1e-6 and max(lengths) > AMPLITUDE * 0.5
    assert any(abs(new[0] - old[0]) > 1e-4 for old, new in zip(before, after))


def test_the_same_seed_gives_the_same_wear_and_another_seed_differs(bridge):
    sheet(bridge, "A")
    sheet(bridge, "B")
    sheet(bridge, "C")
    bridge.ok("displace_noise", name="A", amplitude=AMPLITUDE, seed=11)
    bridge.ok("displace_noise", name="B", amplitude=AMPLITUDE, seed=11)
    bridge.ok("displace_noise", name="C", amplitude=AMPLITUDE, seed=12)
    assert positions("A") == positions("B")
    assert positions("A") != positions("C")
    sheet(bridge, "D")
    sheet(bridge, "E")
    bridge.ok("displace_noise", name="D", amplitude=AMPLITUDE, seed=3, mode="dents", radius=0.3)
    bridge.ok("displace_noise", name="E", amplitude=AMPLITUDE, seed=3, mode="dents", radius=0.3)
    assert positions("D") == positions("E")


def test_coincident_vertices_move_together_so_seams_do_not_crack(bridge):
    corners = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [1, 0, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]]
    bridge.ok("mesh_from_data", name="Seam", vertices=corners, faces=[[0, 1, 2, 3], [4, 5, 6, 7]])
    bridge.ok("displace_noise", name="Seam", amplitude=AMPLITUDE, seed=2, direction="any")
    points = vertices("Seam")
    close(list(points[1]), list(points[4]), 1e-7)
    close(list(points[2]), list(points[7]), 1e-7)


def test_a_face_selection_masks_the_wear(bridge):
    sheet(bridge)
    before = positions("Sheet")
    result = bridge.ok("displace_noise", name="Sheet", amplitude=AMPLITUDE, seed=4, box={"min": [-1, -1, -1], "max": [0, 1, 1]})
    after = positions("Sheet")
    assert 0 < result["displaced_vertices"] < 144
    for old, new in zip(before, after):
        if old[0] > 0.0 + 1e-6 and abs(old[0]) > 0.21:
            assert old == new
    assert any(old != new for old, new in zip(before, after))


def test_a_vertex_group_masks_and_weights_the_wear(bridge):
    sheet(bridge)
    plain = bridge.ok("duplicate", name="Sheet", new_name="Plain")
    group = bpy.data.objects["Sheet"].vertex_groups.new(name="Wear")
    group.add([0, 1, 2], 1.0, "REPLACE")
    group.add([3], 0.5, "REPLACE")
    bridge.ok("displace_noise", name="Plain", amplitude=AMPLITUDE, seed=9)
    result = bridge.ok("displace_noise", name="Sheet", amplitude=AMPLITUDE, seed=9, vertex_group="Wear")
    full = positions("Plain")
    masked = positions("Sheet")
    for index in (0, 1, 2):
        assert masked[index] == full[index]
    close(masked[3][2], full[3][2] * 0.5, 1e-6)
    assert all(masked[index][2] == 0.0 for index in range(4, 144))
    assert result["max_displacement"] <= AMPLITUDE + 1e-7


def test_dents_press_bounded_facets_into_the_surface(bridge):
    sheet(bridge)
    result = bridge.ok("displace_noise", name="Sheet", amplitude=AMPLITUDE, mode="dents", count=5, radius=0.35, seed=5)
    zs = [vertex.z for vertex in vertices("Sheet")]
    assert result["max_displacement"] <= AMPLITUDE + 1e-7
    assert max(zs) <= 1e-7 and min(zs) >= -AMPLITUDE - 1e-6
    dented = sum(1 for z in zs if z < -1e-6)
    assert 5 <= dented < 144
    assert min(zs) < -AMPLITUDE * 0.4


def test_dents_respect_a_mask(bridge):
    sheet(bridge)
    bridge.ok("displace_noise", name="Sheet", amplitude=AMPLITUDE, mode="dents", count=8, radius=0.35, seed=5, box={"min": [0.0, -1, -1], "max": [1, 1, 1]})
    assert all(abs(vertex.z) < 1e-7 for vertex in vertices("Sheet") if vertex.x < -0.2)


def test_displace_noise_refuses_bad_arguments(bridge):
    sheet(bridge)
    bridge.refuse("displace_noise", "bad_args", name="Sheet", amplitude=AMPLITUDE, mode="dents")
    bridge.refuse("displace_noise", "bad_args", name="Sheet", amplitude=AMPLITUDE, radius=0.3)
    bridge.refuse("displace_noise", "bad_args", name="Sheet", amplitude=0.0)
    bridge.refuse("displace_noise", "bad_args", name="Sheet", amplitude=AMPLITUDE, seed=-1)
    bridge.refuse("displace_noise", "bad_args", name="Sheet", amplitude=AMPLITUDE, mode="melt")
    bridge.refuse("displace_noise", "not_found", name="Sheet", amplitude=AMPLITUDE, vertex_group="Ghost")
    bridge.refuse("displace_noise", "bad_args", name="Sheet", amplitude=AMPLITUDE, box={"min": [5, 5, 5], "max": [6, 6, 6]})
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("displace_noise", "bad_args", name="Sheet", amplitude=AMPLITUDE, box={"min": [1, 0, 0], "max": [0, 1, 1]})


def test_failed_wear_leaves_the_scene_unchanged(bridge):
    sheet(bridge)
    before = settled_snapshot()
    bridge.refuse("displace_noise", "not_found", name="Sheet", amplitude=AMPLITUDE, vertex_group="Ghost")
    bridge.refuse("displace_noise", "bad_args", name="Sheet", amplitude=AMPLITUDE, box={"min": [5, 5, 5], "max": [6, 6, 6]})
    assert settled_snapshot() == before


run(globals())
