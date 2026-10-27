import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Vector

from harness import close, run
from kit_helpers import is_closed_manifold, open_edge_count, regular_polygon_area, settled_snapshot, uv_is_clean, vertices, volume

from blendworks_bridge.sweeping import transport_frames

RECTANGLE = {"preset": "rectangle", "width": 0.2, "height": 0.1}


def ring_centre(points):
    return sum(points, Vector((0.0, 0.0, 0.0))) / len(points)


def rings_of(name, count, size):
    points = vertices(name)
    return [points[k * size : (k + 1) * size] for k in range(count)]


def ring_normal(ring):
    normal = Vector((0.0, 0.0, 0.0))
    for index, point in enumerate(ring):
        normal += point.cross(ring[(index + 1) % len(ring)])
    return normal.normalized()


def roll_errors(rings, closed):
    return max(roll_per_pair(rings, closed))


def roll_per_pair(rings, closed):
    centres = [ring_centre(ring) for ring in rings]
    normals = [ring_normal(ring) for ring in rings]
    count = len(rings)
    pairs = []
    for k in range(count if closed else count - 1):
        following = (k + 1) % count
        turn = normals[k].rotation_difference(normals[following])
        worst = 0.0
        for before, after in zip(rings[k], rings[following]):
            first = (before - centres[k]) - normals[k] * (before - centres[k]).dot(normals[k])
            second = (after - centres[following]) - normals[following] * (after - centres[following]).dot(normals[following])
            worst = max(worst, (turn @ first).angle(second, 0.0))
        pairs.append(worst)
    return pairs


def test_circle_swept_along_a_quarter_bend_keeps_its_frame_and_length(bridge):
    result = bridge.ok(
        "sweep", name="Bend", preset="rectangle", width=0.2, height=0.1, waypoints=[[0, 0, 0], [1, 0, 0], [1, 1, 0]], fillet_radius=0.25, fillet_segments=16
    )
    expected = 0.75 * 2 + 16 * 2 * 0.25 * math.sin(math.pi / 64)
    close(result["length"], expected, 1e-6)
    rings = rings_of("Bend", result["rings"], 4)
    for ring in rings:
        for first, point in zip(rings[0], ring):
            close(point.z, first.z, 1e-6)
    assert roll_errors(rings, False) < 0.01
    assert result["manifold"] is True


def test_sweep_does_not_flip_through_the_up_direction(bridge):
    path = [[0, 0, 0], [0, 0, 2], [1.5, 0, 2], [1.5, 1.5, 2], [1.5, 1.5, 0.5]]
    result = bridge.ok("sweep", name="Snake", **RECTANGLE, waypoints=path, fillet_radius=0.3, fillet_segments=12)
    rings = rings_of("Snake", result["rings"], 4)
    assert roll_errors(rings, False) < 0.01
    assert result["manifold"] is True


def test_sweep_along_a_helix_is_twist_free(bridge):
    helix = [[math.cos(i * math.tau / 48), math.sin(i * math.tau / 48), i * 0.02] for i in range(97)]
    result = bridge.ok("sweep", name="Spring", **RECTANGLE, waypoints=helix)
    assert roll_errors(rings_of("Spring", result["rings"], 4), False) < 0.01


def test_closed_path_has_no_seam_gap_even_with_frame_drift(bridge):
    loop = []
    for i in range(120):
        t = i * math.tau / 120
        loop.append([0.3 * (math.sin(t) + 2 * math.sin(2 * t)), 0.3 * (math.cos(t) - 2 * math.cos(2 * t)), -0.3 * math.sin(3 * t)])
    points = [Vector(point) for point in loop]
    _, _, holonomy = transport_frames(points, True, Vector((0, 0, 1)))
    assert abs(holonomy) > 0.2
    result = bridge.ok("sweep", name="Knot", **RECTANGLE, waypoints=loop, closed=True)
    rings = rings_of("Knot", result["rings"], 4)
    pairs = roll_per_pair(rings, True)
    share = abs(holonomy) / len(rings)
    assert max(pairs) < 1.3 * share + 0.002
    assert pairs[-1] < 1.3 * share + 0.002
    assert result["manifold"] is True and result["closed"] is True
    for k in range(len(rings)):
        edge = (rings[k][0] - rings[k - 1][0]).length
        spine = (ring_centre(rings[k]) - ring_centre(rings[k - 1])).length
        assert 0.85 < edge / spine < 1.5, (k, edge, spine)


def test_closed_planar_loop_is_a_torus_with_the_right_volume(bridge):
    loop = [[2 * math.cos(i * math.tau / 64), 2 * math.sin(i * math.tau / 64), 0.0] for i in range(64)]
    result = bridge.ok("sweep", name="Ring", preset="circle", radius=0.1, segments=16, waypoints=loop, closed=True)
    assert result["mesh"]["vertices"] == 64 * 16 and result["mesh"]["faces"] == 64 * 16
    perimeter = 64 * 2 * 2 * math.sin(math.pi / 64)
    assert abs(volume("Ring") / (regular_polygon_area(0.1, 16) * perimeter) - 1.0) < 0.01


def test_caps_close_an_open_sweep_and_volume_is_exact(bridge):
    result = bridge.ok("sweep", name="Rod", preset="circle", radius=0.1, segments=32, waypoints=[[0, 0, 0], [2, 0, 0]])
    close(volume("Rod"), regular_polygon_area(0.1, 32) * 2.0, 1e-6)
    assert result["mesh"]["faces"] == 32 + 2 and result["manifold"] is True
    open_rod = bridge.ok("sweep", name="Hose", preset="circle", radius=0.1, segments=32, waypoints=[[0, 1, 0], [2, 1, 0]], caps=False)
    assert open_rod["manifold"] is False and open_edge_count("Hose") == 64


def test_scale_tapers_linearly_along_the_path(bridge):
    bridge.ok("sweep", name="Taper", preset="circle", radius=0.2, segments=16, waypoints=[[0, 0, 0], [0, 0, 1.5], [0, 0, 3]], scale_end=0.5)
    area = regular_polygon_area(0.2, 16)
    close(volume("Taper"), 3.0 / 3.0 * area * (1 + 0.5 + 0.25), 1e-6)
    sizes = sorted(vertex.z for vertex in vertices("Taper"))
    assert sizes[0] == 0.0 and sizes[-1] == 3.0


def test_twist_turns_the_end_ring(bridge):
    path = [[0, 0, 0], [0, 0, 0.25], [0, 0, 0.5], [0, 0, 0.75], [0, 0, 1]]
    result = bridge.ok("sweep", name="Twist", **RECTANGLE, waypoints=path, up=[1, 0, 0], twist=90.0)
    rings = rings_of("Twist", result["rings"], 4)
    start, end = rings[0][0], rings[-1][0]
    close(list(start), [-0.05, 0.1, 0.0], 1e-6)
    close(list(end), [-0.1, -0.05, 1.0], 1e-6)


def test_up_sets_which_way_the_profile_height_points(bridge):
    bridge.ok("sweep", name="Flat", **RECTANGLE, waypoints=[[0, 0, 0], [3, 0, 0]])
    close(list(bpy.data.objects["Flat"].dimensions), [3.0, 0.2, 0.1], 1e-6)
    bridge.ok("sweep", name="Tall", **RECTANGLE, waypoints=[[0, 2, 0], [3, 2, 0]], up=[0, 1, 0])
    close(list(bpy.data.objects["Tall"].dimensions), [3.0, 0.1, 0.2], 1e-6)


def test_mitred_corner_keeps_the_bar_thickness(bridge):
    result = bridge.ok("sweep", name="Elbow", preset="rectangle", width=0.1, height=0.1, waypoints=[[0, 0, 0], [1, 0, 0], [1, 1, 0]])
    close(volume("Elbow"), 0.1 * 0.1 * 2.0, 1e-6)
    assert result["manifold"] is True


def test_sweep_follows_a_curve_object_without_changing_it(bridge):
    bridge.ok("curve_from_points", name="Rail", points=[[0, 0, 0], [1, 0, 0], [1, 1, 0]], bevel_depth=0.05)
    result = bridge.ok("sweep", name="Bar", **RECTANGLE, curve="Rail")
    close(result["length"], 2.0, 1e-6)
    close(bpy.data.curves["Rail"].bevel_depth, 0.05, 1e-6)
    bridge.ok("curve_from_points", name="Loop", points=[[0, 0, 5], [1, 0, 5], [1, 1, 5], [0, 1, 5]], closed=True)
    loop = bridge.ok("sweep", name="Frame", **RECTANGLE, curve="Loop")
    assert loop["closed"] is True and loop["manifold"] is True
    close(loop["length"], 4.0, 1e-6)


def test_sweep_uvs_run_along_the_length(bridge):
    bridge.ok("sweep", name="Pipe", preset="circle", radius=0.1, segments=16, waypoints=[[0, 0, 0], [1, 0, 0], [2, 0, 0]])
    uv_is_clean(bridge, "Pipe")
    mesh = bpy.data.objects["Pipe"].data
    layer = mesh.uv_layers.active.data
    side = next(polygon for polygon in mesh.polygons if len(polygon.vertices) == 4)
    corners = [layer[index].uv for index in side.loop_indices]
    along = abs(corners[3][1] - corners[0][1])
    around = abs(corners[1][0] - corners[0][0])
    close(along / around, 1.0 / (2 * 0.1 * math.sin(math.pi / 16)), 1e-4)


def test_sweep_refuses_bad_arguments(bridge):
    straight = [[0, 0, 0], [1, 0, 0]]
    bridge.ok("curve_from_points", name="Rail", points=[[0, 0, 0], [1, 0, 0]])
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1)
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=straight, curve="Rail")
    bridge.refuse("sweep", "bad_args", name="A", waypoints=straight)
    bridge.refuse("sweep", "bad_args", name="A", waypoints=straight, preset="circle", radius=0.1, profile=[[0, 0], [1, 0], [0, 1]])
    bridge.refuse("sweep", "bad_args", name="A", waypoints=straight, preset="circle")
    bridge.refuse("sweep", "bad_args", name="A", waypoints=straight, preset="circle", radius=0.1, width=1.0)
    bridge.refuse("sweep", "bad_args", name="A", waypoints=straight, profile=[[0, 0], [1, 0], [2, 0]])
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=[[0, 0, 0], [0, 0, 0], [1, 0, 0]])
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=[[0, 0, 0], [1, 0, 0], [0, 0, 0.0001]])
    bridge.refuse("sweep", "not_found", name="A", preset="circle", radius=0.1, curve="Ghost")
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, curve="Box")
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=straight, up=[0, 0, 0])


def test_sweep_refuses_unfit_fillets_and_closed_mismatches(bridge):
    corner = [[0, 0, 0], [1, 0, 0], [1, 1, 0]]
    message = bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=corner, fillet_radius=2.0)
    assert "largest radius" in message and "1.0" in message
    loop = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=loop, closed=True, twist=90.0)
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=loop, closed=True, scale_end=2.0)
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=loop[:2], closed=True)
    bridge.ok("sweep", name="Turned", preset="circle", radius=0.05, waypoints=loop, closed=True, twist=360.0)


def test_failed_sweep_leaves_the_scene_unchanged(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    before = settled_snapshot()
    bridge.refuse("sweep", "bad_args", name="A", preset="circle", radius=0.1, waypoints=[[0, 0, 0], [1, 0, 0], [1, 1, 0]], fillet_radius=5.0)
    assert settled_snapshot() == before
    assert is_closed_manifold("Box")


run(globals())
