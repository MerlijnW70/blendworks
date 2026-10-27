import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy

from harness import close, run
from kit_helpers import is_closed_manifold, volume

from blendworks_bridge.cleaning import repair_slivers, sliver_faces
from blendworks_bridge.topology import manifold_report

DEGENERATE_AREA = 1e-12
CUBE = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]


def degenerate_triangles(name, limit=DEGENERATE_AREA):
    mesh = bpy.data.objects[name].data
    mesh.calc_loop_triangles()
    count = 0
    for triangle in mesh.loop_triangles:
        a, b, c = (mesh.vertices[index].co for index in triangle.vertices)
        if (b - a).cross(c - a).length / 2.0 <= limit:
            count += 1
    return count


def tick_ring(bridge, boolean_arguments):
    radius = 0.186
    count = 256
    points = [[radius * math.cos(math.tau * i / count), radius * math.sin(math.tau * i / count), 0.0] for i in range(count)]
    bridge.ok("sweep", name="Ring", preset="rounded_rectangle", width=0.056, height=0.006, corner_radius=0.0009, segments=2, waypoints=points, closed=True)
    names = []
    for label, length, ticks in (("short", 0.0045, 360), ("long", 0.0085, 36)):
        source = f"{label}_source"
        bridge.ok("add_primitive", type="cube", name=source, size=1.0)
        bridge.ok("transform", name=source, scale=[length, 0.0007, 0.0009])
        bridge.ok("apply_transform", name=source, scale=True)
        circle = {"centre": [0, 0, 0.003], "normal": [0, 0, 1], "radius": radius + 0.028 - 0.0045 / 2, "count": ticks, "start_angle": 0.37}
        bridge.ok("instances", source=source, name=f"{label}_ticks", circle=circle, align="radial", realize=True, group=False)
        bridge.ok("delete", names=[source])
        names.append(f"{label}_ticks")
    return bridge.ok("boolean", name="Ring", cutters=names, operation="difference", cutter_action="delete", manifold=True, **boolean_arguments)


def sliver_cube(bridge, name="Sliver", lift=0.0):
    vertices = CUBE + [[0.5, 0, 1 + lift]]
    faces = [[0, 3, 2, 1], [0, 1, 5, 8, 4], [3, 7, 6, 2], [0, 4, 7, 3], [1, 2, 6, 5], [4, 8, 5], [4, 5, 6], [4, 6, 7]]
    return bridge.ok("mesh_from_data", name=name, vertices=vertices, faces=faces, vertex_uvs=[[x, y] for x, y, _ in vertices])


def test_coplanar_overlapping_cutters_leave_slivers_that_clean_mesh_removes(bridge):
    plain = tick_ring(bridge, {"clean": False})
    assert "cleaned" not in plain
    bridge.ok("merge_by_distance", name="Ring", distance=0.00001)
    before = degenerate_triangles("Ring")
    assert before > 0
    volume_before = volume("Ring")
    report = bridge.ok("clean_mesh", name="Ring")
    assert degenerate_triangles("Ring") == 0
    assert report["degenerate_triangles_after"] == 0 and report["faces_retriangulated"] > 0
    assert report["manifold"] is True and is_closed_manifold("Ring")
    close(volume("Ring"), volume_before, 1e-9)
    close(report["volume"], volume_before, 1e-9)


def test_boolean_cleans_by_default_and_reports_what_it_fixed(bridge):
    result = tick_ring(bridge, {})
    assert result["manifold"] is True and is_closed_manifold("Ring")
    assert degenerate_triangles("Ring") == 0
    assert result["cleaned"]["degenerate_triangles_before"] > 0
    assert result["cleaned"]["degenerate_triangles_after"] == 0 and result["cleaned"]["merged_vertices"] > 0


def test_a_boolean_does_not_add_an_empty_material_slot(bridge):
    bridge.ok("add_primitive", type="cube", name="Block", size=1.0)
    bridge.ok("add_material", name="Paint")
    bridge.ok("assign_material", name="Block", material="Paint")
    bridge.ok("add_primitive", type="cube", name="Bite", size=0.5, location=[0.5, 0.5, 0.5])
    bridge.ok("boolean", name="Block", cutter="Bite", operation="difference")
    assert [slot.material.name if slot.material else None for slot in bpy.data.objects["Block"].material_slots] == ["Paint"]


def test_clean_false_leaves_the_boolean_result_alone(bridge):
    tick_ring(bridge, {"clean": False})
    assert degenerate_triangles("Ring") > 0


def test_a_zero_area_face_is_dissolved_into_its_neighbour(bridge):
    sliver_cube(bridge)
    assert degenerate_triangles("Sliver") == 1
    report = bridge.ok("clean_mesh", name="Sliver")
    assert report["dissolved_faces"] == 1 and report["collinear_vertices_removed"] == 1
    assert report["mesh"]["vertices"] == 8 and degenerate_triangles("Sliver") == 0 and is_closed_manifold("Sliver")
    close(volume("Sliver"), 1.0, 1e-9)


def test_a_sliver_triangle_is_flipped_into_its_neighbour_and_keeps_its_uvs(bridge):
    sliver_cube(bridge, lift=0.0000005)
    assert degenerate_triangles("Sliver", 1e-6) == 1
    graph = bmesh.new()
    graph.from_mesh(bpy.data.objects["Sliver"].data)
    try:
        retriangulated, flipped = repair_slivers(graph, 1e-6)
        assert (retriangulated, flipped) == (0, 1)
        assert sliver_faces(graph, 1e-6)[1] == 0
        assert manifold_report(graph)["manifold"] is True
        close(graph.calc_volume(signed=True), 1.0, 1e-6)
        layer = graph.loops.layers.uv.active
        for face in graph.faces:
            for loop in face.loops:
                close(list(loop[layer].uv), [loop.vert.co.x, loop.vert.co.y], 1e-6)
    finally:
        graph.free()


def test_a_collinear_vertex_between_two_large_faces_is_removed(bridge):
    vertices = CUBE + [[0, 0, 0.5]]
    faces = [[0, 3, 2, 1], [0, 1, 5, 4, 8], [3, 7, 6, 2], [0, 8, 4, 7, 3], [1, 2, 6, 5], [4, 5, 6, 7]]
    bridge.ok("mesh_from_data", name="Edge", vertices=vertices, faces=faces)
    report = bridge.ok("clean_mesh", name="Edge")
    assert report["collinear_vertices_removed"] == 1
    assert report["mesh"]["vertices"] == 8 and report["manifold"] is True
    close(volume("Edge"), 1.0, 1e-9)


def test_a_bent_vertex_stays(bridge):
    vertices = CUBE + [[0.05, 0, 0.5]]
    faces = [[0, 3, 2, 1], [0, 1, 5, 4, 8], [3, 7, 6, 2], [0, 8, 4, 7, 3], [1, 2, 6, 5], [4, 5, 6, 7]]
    bridge.ok("mesh_from_data", name="Bent", vertices=vertices, faces=faces)
    report = bridge.ok("clean_mesh", name="Bent")
    assert report["collinear_vertices_removed"] == 0 and report["mesh"]["vertices"] == 9


def test_loose_geometry_is_removed_and_counted(bridge):
    vertices = CUBE + [[3, 3, 3], [4, 4, 4], [5, 5, 5]]
    faces = [[0, 3, 2, 1], [0, 1, 5, 4], [3, 7, 6, 2], [0, 4, 7, 3], [1, 2, 6, 5], [4, 5, 6, 7]]
    bridge.ok("mesh_from_data", name="Loose", vertices=vertices, faces=faces, edges=[[8, 9]])
    report = bridge.ok("clean_mesh", name="Loose")
    assert report["loose_edges_removed"] == 1 and report["loose_vertices_removed"] == 3
    assert report["mesh"] == {"vertices": 8, "edges": 12, "faces": 6, "triangles": 12}


def test_inside_out_faces_are_turned_outward(bridge):
    faces = [[0, 1, 2, 3], [0, 4, 5, 1], [3, 2, 6, 7], [0, 3, 7, 4], [1, 5, 6, 2], [4, 7, 6, 5]]
    bridge.ok("mesh_from_data", name="Inverted", vertices=CUBE, faces=faces)
    assert volume("Inverted") < 0
    report = bridge.ok("clean_mesh", name="Inverted")
    assert report["normals_flipped"] == 6
    close(volume("Inverted"), 1.0, 1e-9)


def test_a_distance_below_merge_distance_joins_vertices(bridge):
    vertices = CUBE + [[0.000001, 0, 0]]
    faces = [[0, 3, 2, 1], [8, 1, 5, 4], [3, 7, 6, 2], [8, 4, 7, 3], [1, 2, 6, 5], [4, 5, 6, 7]]
    bridge.ok("mesh_from_data", name="Doubled", vertices=vertices, faces=faces)
    report = bridge.ok("clean_mesh", name="Doubled", merge_distance=0.00001)
    assert report["merged_vertices"] == 1 and report["mesh"]["vertices"] == 8
    again = bridge.ok("clean_mesh", name="Doubled", merge_distance=0)
    assert again["merged_vertices"] == 0


def test_clean_mesh_refuses_bad_input(bridge):
    bridge.refuse("clean_mesh", "not_found", name="Nothing")
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    bridge.refuse("clean_mesh", "bad_args", name="Box", tolerance=0)
    bridge.refuse("clean_mesh", "bad_args", name="Box", merge_distance=-1)
    bridge.ok("curve_from_points", name="Line", points=[[0, 0, 0], [1, 0, 0]])
    bridge.refuse("clean_mesh", "bad_args", name="Line")


run(globals())
