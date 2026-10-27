import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run

FILLET = 0.1
STEPS = 6


def rounded_can(radius, height):
    bottom = [[radius - FILLET + FILLET * math.sin(math.pi / 2 * i / STEPS), FILLET - FILLET * math.cos(math.pi / 2 * i / STEPS)] for i in range(STEPS + 1)]
    top = [[radius - FILLET + FILLET * math.cos(math.pi / 2 * i / STEPS), height - FILLET + FILLET * math.sin(math.pi / 2 * i / STEPS)] for i in range(STEPS + 1)]
    return [[0.0, 0.0], [radius - FILLET, 0.0], *bottom[1:], *top, [radius - FILLET, height], [0.0, height]]


def corner_normals(name):
    mesh = bpy.data.objects[name].data
    return mesh, [normal.vector.copy() for normal in mesh.corner_normals]


def worst_flat_deviation(name, wanted):
    mesh, normals = corner_normals(name)
    worst = 0.0
    for polygon in mesh.polygons:
        if wanted(polygon):
            worst = max(worst, max(polygon.normal.angle(normals[loop]) for loop in polygon.loop_indices))
    return math.degrees(worst)


def vertex_spread(name, vertex):
    mesh, normals = corner_normals(name)
    around = [normals[loop] for loop in range(len(mesh.loops)) if mesh.loops[loop].vertex_index == vertex]
    return math.degrees(max(a.angle(b) for a in around for b in around))


def test_lathe_flat_faces_shade_flat_next_to_a_fillet(bridge):
    bridge.ok("lathe", name="Can", profile=rounded_can(1.0, 0.4), segments=64)
    assert worst_flat_deviation("Can", lambda polygon: abs(polygon.normal.z) > 0.999999) < 0.01


def test_lathe_fillet_stays_smooth(bridge):
    bridge.ok("lathe", name="Can", profile=rounded_can(1.0, 0.4), segments=64)
    mesh = bpy.data.objects["Can"].data
    inside = [vertex.index for vertex in mesh.vertices if abs(math.hypot(vertex.co.x, vertex.co.y) - 1.0 + FILLET - FILLET * math.sin(math.pi / 2 * 2 / STEPS)) < 1e-6 and abs(vertex.co.z - (FILLET - FILLET * math.cos(math.pi / 2 * 2 / STEPS))) < 1e-6]
    assert inside
    assert all(vertex_spread("Can", vertex) < 0.01 for vertex in inside)


def test_lathe_square_corner_stays_hard(bridge):
    bridge.ok("lathe", name="Block", profile=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], segments=32)
    mesh = bpy.data.objects["Block"].data
    corner = next(vertex.index for vertex in mesh.vertices if abs(vertex.co.z - 1.0) < 1e-9 and abs(math.hypot(vertex.co.x, vertex.co.y) - 1.0) < 1e-9)
    assert vertex_spread("Block", corner) > 85.0


def test_sweep_flat_sides_shade_flat_next_to_rounded_corners(bridge):
    bridge.ok("sweep", name="Ring", preset="rounded_rectangle", width=0.2, height=0.02, corner_radius=0.004, segments=4, circle={"centre": [0, 0, 0], "radius": 1.0, "tolerance": 0.0005})
    assert worst_flat_deviation("Ring", lambda polygon: abs(polygon.normal.z) > 0.999999) < 0.01


def test_sweep_rounded_corner_stays_smooth(bridge):
    bridge.ok("sweep", name="Ring", preset="rounded_rectangle", width=0.2, height=0.02, corner_radius=0.004, segments=4, circle={"centre": [0, 0, 0], "radius": 1.0, "tolerance": 0.0005})
    mesh = bpy.data.objects["Ring"].data
    heights = [0.006 + 0.004 * math.sin(math.pi / 2 * step / 4) for step in (1, 2, 3)]
    inside = [vertex.index for vertex in mesh.vertices if any(abs(abs(vertex.co.z) - height) < 1e-7 for height in heights)]
    assert inside
    assert all(vertex_spread("Ring", vertex) < 0.01 for vertex in inside)


run(globals())
