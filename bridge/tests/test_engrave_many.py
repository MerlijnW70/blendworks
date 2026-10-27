import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from mathutils import Vector
from mathutils.geometry import barycentric_transform, intersect_point_tri

from engrave_checks import broken_tangents, shape_counts, stray_seams, unmapped_triangles, uv_breaks
from harness import run
from kit_helpers import is_closed_manifold

TOP = 0.003
RADIUS = 0.15
SIGNS = ("aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces")


def ring(bridge):
    bridge.ok("sweep", name="Ring", preset="rounded_rectangle", width=0.056, height=2 * TOP, corner_radius=0.0009, segments=2, circle={"centre": [0, 0, 0], "radius": RADIUS, "tolerance": 0.00006}, shading="auto", smooth_angle=40)


def face(radius, angle=0.0, up="outward"):
    return {"ring": {"centre": [0, 0, TOP], "radius": radius, "angle": angle, "up": up}}


def cuts():
    yield "engrave_scale", dict(name="Ring", **face(0.17), step=1, depth=0.0004, length=0.004, width=0.0004, classes=[{"every": 10, "length": 0.0065, "depth": 0.0007}])
    for index in range(24):
        yield "engrave", dict(name="Ring", text=str(15 * index), **face(0.1615, 15 * index), size=0.0045, depth=0.0005)
    for index, sign in enumerate(SIGNS):
        yield "engrave", dict(name="Ring", text="{" + sign + "}", **face(0.137, 30 * index + 15, "inward"), size=0.007, depth=0.0005)
    for index, word in enumerate(("NORTH", "EAST", "SOUTH")):
        yield "engrave", dict(name="Ring", text=word, **face(0.148, 90 * index + 5), size=0.004, depth=0.0004, spacing=1.2)


def test_forty_successive_cuts_keep_the_ring_closed_without_slivers_and_mapped(bridge):
    ring(bridge)
    bridge.ok("duplicate", name="Ring", new_name="Reference")
    original = uv_breaks("Ring")
    plan = list(cuts())
    assert len(plan) == 40 and sum(1 for name, _ in plan if name == "engrave") == 39
    for number, (name, arguments) in enumerate(plan):
        result = bridge.ok(name, **arguments)
        where = (number, name, arguments.get("text"))
        assert result["manifold"] is True and is_closed_manifold("Ring"), where
        assert result["volume_change"] < 0, where
        counts = shape_counts("Ring")
        assert counts["slivers"] == 0 and counts["zero_area"] == 0, (where, counts)
        assert result["quality"]["slivers"] == 0, (where, result["quality"])
        assert unmapped_triangles("Ring") == 0, where
        assert broken_tangents("Ring") == 0, where
        stray = stray_seams("Ring", original, "Reference")
        assert stray == [], (where, stray[:3])


def surface_uv(reference, point):
    found, location, _, index = reference.closest_point_on_mesh(point)
    assert found
    mesh = reference.data
    mesh.calc_loop_triangles()
    layer = mesh.uv_layers.active
    for triangle in mesh.loop_triangles:
        if triangle.polygon_index != index:
            continue
        corners = [mesh.vertices[vertex].co for vertex in triangle.vertices]
        if intersect_point_tri(location, *corners) is not None:
            uvs = [Vector((*layer.uv[loop].vector, 0.0)) for loop in triangle.loops]
            return barycentric_transform(location, *corners, *uvs).to_2d()
    raise AssertionError("no triangle holds the point")


def test_the_floor_of_a_cut_carries_the_mapping_of_the_surface_above_it(bridge):
    ring(bridge)
    bridge.ok("duplicate", name="Ring", new_name="Reference")
    depth = 0.0006
    bridge.ok("engrave", name="Ring", text="88", **face(0.16, 40), size=0.008, depth=depth)
    mesh = bpy.data.objects["Ring"].data
    reference = bpy.data.objects["Reference"]
    layer = mesh.uv_layers.active
    checked = 0
    for polygon in mesh.polygons:
        if polygon.normal.z < 0.99 or abs(polygon.center.z - (TOP - depth)) > 1e-6:
            continue
        for loop in polygon.loop_indices:
            point = mesh.vertices[mesh.loops[loop].vertex_index].co + Vector((0.0, 0.0, depth))
            expected = surface_uv(reference, point)
            assert (Vector(layer.uv[loop].vector) - expected).length < 2e-5, (tuple(point), tuple(layer.uv[loop].vector), tuple(expected))
            checked += 1
    assert checked > 100, checked


run(globals())
