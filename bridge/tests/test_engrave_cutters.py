import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
import numpy

from harness import run
from kit_helpers import is_closed_manifold

from blendworks_bridge.cutters import add_solid
from blendworks_bridge.meshdata import MeshData
from blendworks_bridge.surfaces import CylinderSurface, PlaneSurface, RingSurface, curve_surface
from blendworks_bridge.textlayout import min_edge, text_shapes

ZERO_AREA = 1e-12
SLIVER_ASPECT = 1000.0
SIZE = 0.0068
DEPTH = 0.0005
TEXTS = ("0123456789", "ANNO 1824", "{aries}{taurus}{gemini}{cancer}{leo}{virgo}", "{libra}{scorpio}{sagittarius}{capricorn}{aquarius}{pisces}", "{sun}{moon}{saturn}")


class Context:
    scene = bpy.context.scene

    @staticmethod
    def depsgraph():
        return bpy.context.evaluated_depsgraph_get()


def cutter(surface, text, shift=(0.0, 0.0), tolerance=0.0002, size=SIZE):
    shapes = text_shapes(Context, text, size, 1.0, None, "centre", "middle", 0.0)[0]
    data = add_solid(MeshData(), shapes, surface, shift, DEPTH, 0.0008, 0, min_edge(size), tolerance)
    mesh = bpy.data.meshes.new("cutter")
    data.to_mesh(mesh)
    holder = bpy.data.objects.new("Cutter", mesh)
    bpy.context.scene.collection.objects.link(holder)
    return holder


def shapes_of(holder):
    mesh = holder.data
    mesh.calc_loop_triangles()
    vertices = numpy.zeros(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", vertices)
    positions = numpy.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", positions)
    positions = positions.reshape(-1, 3)
    a, b, c = (positions[vertices.reshape(-1, 3)[:, index]] for index in range(3))
    area = numpy.linalg.norm(numpy.cross(b - a, c - a), axis=1) / 2.0
    longest = numpy.maximum.reduce([numpy.linalg.norm(b - a, axis=1), numpy.linalg.norm(c - b, axis=1), numpy.linalg.norm(a - c, axis=1)])
    return area, longest ** 2 / numpy.maximum(2.0 * area, 1e-300)


def test_cutters_of_glyphs_and_symbols_have_no_slivers_on_any_surface(bridge):
    loop = [[0.1735 * math.cos(-math.tau * index / 360), 0.1735 * math.sin(-math.tau * index / 360), 0.0] for index in range(360)]
    surfaces = {
        "plane": (PlaneSurface((0, 0, 0), (0, 0, 1), None), (0.0, 0.0)),
        "ring": (RingSurface({"centre": [0, 0, 0], "axis": [0, 0, 1], "radius": 0.16, "angle": 30.0, "up": "outward"}), (0.0, 0.0)),
        "curve across its start": (curve_surface({"waypoints": loop, "closed": True, "normal": [0, 0, 1]}), (0.1735 * math.radians(359.25), 0.0)),
    }
    for label, (surface, shift) in surfaces.items():
        for text in TEXTS:
            holder = cutter(surface, text, shift)
            area, aspect = shapes_of(holder)
            assert is_closed_manifold("Cutter"), (label, text)
            assert int((area <= ZERO_AREA).sum()) == 0 and float(aspect.max()) < SLIVER_ASPECT, (label, text, float(aspect.max()))
            bpy.data.objects.remove(holder)


def test_a_cutter_on_a_cylinder_follows_it_within_the_tolerance(bridge):
    radius, tolerance = 0.03, 0.00005
    surface = CylinderSurface({"centre": [0, 0, 0], "axis": [0, 0, 1], "radius": radius, "side": "outer", "angle": 0.0})
    holder = cutter(surface, "ANNO -=- 1824", tolerance=tolerance, size=0.02)
    assert is_closed_manifold("Cutter")
    mesh = holder.data
    worst = 0.0
    floor = radius - DEPTH
    for edge in mesh.edges:
        first, second = (mesh.vertices[index].co for index in edge.vertices)
        if max(math.hypot(first.x, first.y), math.hypot(second.x, second.y)) > floor + 1e-9:
            continue
        middle = (first + second) / 2.0
        worst = max(worst, floor - math.hypot(middle.x, middle.y))
    assert 0.0 < worst <= tolerance, worst


def test_a_cutter_folded_over_a_path_corner_stays_closed_and_unfolded(bridge):
    corner = [[-0.05, 0.0, 0.0], [0.0, 0.0, 0.0], [0.05 * math.cos(math.radians(20)), 0.05 * math.sin(math.radians(20)), 0.0]]
    surface = curve_surface({"waypoints": corner, "normal": [0, 0, 1]})
    holder = cutter(surface, "8888", (0.05, 0.0))
    assert is_closed_manifold("Cutter")
    bm = bmesh.new()
    bm.from_mesh(holder.data)
    try:
        bm.normal_update()
        caps = [face for face in bm.faces if len(face.verts) == 3]
        top = [face for face in caps if face.calc_center_median().z > 0.0]
        assert top and all(face.normal.z > 0.99 for face in top), min(face.normal.z for face in top)
        assert bm.calc_volume(signed=True) > 0
    finally:
        bm.free()


run(globals())
