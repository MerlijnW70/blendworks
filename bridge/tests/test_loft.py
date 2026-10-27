import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import euler, is_closed_manifold, open_edge_count, outward_normals, regular_polygon_area, settled_snapshot, uv_is_clean, volume

SQUARE = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]]


def circle_section(radius, z, segments=16):
    return {"preset": "circle", "radius": radius, "segments": segments, "position": [0.0, 0.0, z]}


def test_loft_between_two_circles_is_a_frustum_with_hand_counted_topology(bridge):
    result = bridge.ok("loft", name="Cone", sections=[circle_section(1.0, 0.0), circle_section(0.5, 2.0)])
    assert result["mesh"] == {"vertices": 32, "edges": 48, "faces": 18, "triangles": 16 * 2 + 14 * 2}
    assert euler("Cone") == 2 and result["manifold"] is True
    area = regular_polygon_area(1.0, 16)
    close(volume("Cone"), 2.0 / 3.0 * area * (1 + 0.5 + 0.25), 1e-5)
    assert outward_normals("Cone") == 1.0
    uv_is_clean(bridge, "Cone")


def test_loft_fills_in_points_without_changing_the_shape(bridge):
    midpoints = [[-0.5, -0.5], [0.0, -0.5], [0.5, -0.5], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5], [-0.5, 0.5], [-0.5, 0.0]]
    sections = [
        {"profile": SQUARE, "position": [0.0, 0.0, 0.0]},
        {"profile": midpoints, "position": [0.0, 0.0, 2.0]},
    ]
    result = bridge.ok("loft", name="Prism", sections=sections)
    assert result["points_per_section"] == 8
    close(volume("Prism"), 2.0, 1e-5)
    assert is_closed_manifold("Prism")
    bridge.ok("loft", name="Dense", sections=sections, samples=12)
    close(volume("Dense"), 2.0, 1e-5)


def test_loft_aligns_start_points_to_avoid_twist(bridge):
    turned = [[0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5], [0.5, -0.5]]
    sections = [{"profile": SQUARE, "position": [0.0, 0.0, 0.0]}, {"profile": turned, "position": [0.0, 0.0, 2.0]}]
    bridge.ok("loft", name="Straight", sections=sections)
    close(volume("Straight"), 2.0, 1e-5)
    bridge.ok("loft", name="Twisted", sections=sections, align=False)
    assert abs(volume("Twisted") - 2.0) > 0.1


def test_loft_orients_each_section_and_follows_any_direction(bridge):
    sections = [
        {"preset": "circle", "radius": 1.0, "segments": 16, "position": [0.0, 0.0, 0.0], "rotation": [-90.0, 0.0, 0.0]},
        {"preset": "circle", "radius": 0.5, "segments": 16, "position": [0.0, 2.0, 0.0], "rotation": [-90.0, 0.0, 0.0]},
    ]
    bridge.ok("loft", name="Sideways", sections=sections)
    close(list(bpy.data.objects["Sideways"].dimensions), [2.0, 2.0, 2.0], 1e-5)
    area = regular_polygon_area(1.0, 16)
    close(volume("Sideways"), 2.0 / 3.0 * area * 1.75, 1e-5)
    backwards = [
        {"preset": "circle", "radius": 1.0, "segments": 16, "position": [0.0, 0.0, 0.0], "rotation": [90.0, 0.0, 0.0]},
        {"preset": "circle", "radius": 0.5, "segments": 16, "position": [0.0, 2.0, 0.0], "rotation": [-90.0, 0.0, 0.0]},
    ]
    result = bridge.ok("loft", name="Mixed", sections=backwards)
    assert result["manifold"] is True and outward_normals("Mixed") == 1.0


def test_closed_loft_is_a_ring(bridge):
    sections = []
    count = 32
    for index in range(count):
        angle = math.tau * index / count
        sections.append(
            {
                "preset": "circle",
                "radius": 0.1,
                "segments": 8,
                "position": [math.cos(angle), math.sin(angle), 0.0],
                "rotation": [0.0, 90.0, math.degrees(angle) + 90.0],
            }
        )
    result = bridge.ok("loft", name="Ring", sections=sections, closed=True)
    assert result["mesh"]["vertices"] == 256 and result["mesh"]["faces"] == 256
    assert euler("Ring") == 0 and result["manifold"] is True
    expected = regular_polygon_area(0.1, 8) * count * 2.0 * math.sin(math.pi / count)
    assert abs(volume("Ring") / expected - 1.0) < 0.02


def test_open_loft_without_caps_keeps_its_boundary(bridge):
    sections = [circle_section(1.0, 0.0, 12), circle_section(1.0, 1.0, 12)]
    result = bridge.ok("loft", name="Sleeve", sections=sections, caps=False)
    assert result["manifold"] is False and open_edge_count("Sleeve") == 24


def test_loft_refuses_bad_sections(bridge):
    pair = [circle_section(1.0, 0.0), circle_section(1.0, 1.0)]
    bridge.refuse("loft", "bad_args", name="A", sections=[circle_section(1.0, 0.0)])
    bridge.refuse("loft", "bad_args", name="A", sections=pair, closed=True)
    bridge.refuse("loft", "bad_args", name="A", sections=pair, samples=8)
    bridge.refuse("loft", "bad_args", name="A", sections=[{"position": [0, 0, 0]}, circle_section(1.0, 1.0)])
    bridge.refuse("loft", "bad_args", name="A", sections=[{"preset": "circle", "radius": 1.0, "profile": SQUARE, "position": [0, 0, 0]}, circle_section(1.0, 1.0)])
    bridge.refuse("loft", "bad_args", name="A", sections=[circle_section(1.0, 0.0), circle_section(1.0, 0.0)])
    bridge.refuse("loft", "bad_args", name="A", sections=[{"preset": "circle", "radius": 1.0}, circle_section(1.0, 1.0)])
    bridge.refuse("loft", "bad_args", name="A", sections=[{"profile": [[0, 0], [1, 0], [2, 0]], "position": [0, 0, 0]}, circle_section(1.0, 1.0)])


def test_failed_loft_leaves_the_scene_unchanged(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    before = settled_snapshot()
    bridge.refuse("loft", "bad_args", name="A", sections=[circle_section(1.0, 0.0), circle_section(1.0, 0.0)])
    assert settled_snapshot() == before


run(globals())
