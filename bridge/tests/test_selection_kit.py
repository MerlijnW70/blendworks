import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import extent, mesh_bm, settled_snapshot, vertices, volume


def subdivided_cube(bridge, name="Box"):
    bridge.ok("add_primitive", type="cube", name=name, size=2.0)
    bridge.ok("subdivide", name=name, cuts=1)


def indices_of(result):
    return sorted(face["index"] for face in result["faces"])


def test_mesh_query_pages_through_faces_with_world_data(bridge):
    subdivided_cube(bridge)
    first = bridge.ok("mesh_query", name="Box", facing="up", limit=3)
    assert first["total"] == 4 and len(first["faces"]) == 3 and first["next_offset"] == 3 and first["islands"] == 1
    last = bridge.ok("mesh_query", name="Box", facing="up", limit=3, offset=3)
    assert len(last["faces"]) == 1 and last["next_offset"] is None
    seen = first["faces"] + last["faces"]
    for face in seen:
        close(face["normal"], [0.0, 0.0, 1.0], 1e-6)
        close(face["area"], 1.0, 1e-6)
        assert face["centre"][2] == 1.0 and face["vertices"] == 4 and face["material"] is None
    assert sorted((face["centre"][0], face["centre"][1]) for face in seen) == [(-0.5, -0.5), (-0.5, 0.5), (0.5, -0.5), (0.5, 0.5)]
    everything = bridge.ok("mesh_query", name="Box")
    assert everything["total"] == 24 and everything["next_offset"] is None


def test_mesh_query_reports_world_space_for_a_moved_object(bridge):
    subdivided_cube(bridge)
    bridge.ok("transform", name="Box", location=[10.0, 0.0, 0.0], scale=[2.0, 1.0, 1.0])
    result = bridge.ok("mesh_query", name="Box", facing="right", limit=1)
    face = result["faces"][0]
    assert face["centre"][0] == 12.0
    close(face["area"], 1.0, 1e-6)
    close(face["normal"], [1.0, 0.0, 0.0], 1e-6)


def test_select_faces_by_bounding_box(bridge):
    subdivided_cube(bridge)
    top = bridge.ok("mesh_query", name="Box", box={"min": [-2, -2, 0.9], "max": [2, 2, 1.5]})
    assert top["total"] == 4
    corner = bridge.ok("mesh_query", name="Box", box={"min": [0, 0, 0.9], "max": [2, 2, 1.5]})
    assert corner["total"] == 1 and corner["faces"][0]["centre"] == [0.5, 0.5, 1.0]
    assert bridge.ok("mesh_query", name="Box", box={"min": [5, 5, 5], "max": [6, 6, 6]})["total"] == 0
    bridge.ok("extrude", name="Box", distance=0.5, box={"min": [-2, -2, 0.9], "max": [2, 2, 1.5]})
    close(extent("Box")[2], 2.5, 1e-6)


def test_select_faces_by_material(bridge):
    subdivided_cube(bridge)
    bridge.ok("add_material", name="Red")
    bridge.ok("add_material", name="Grey")
    bridge.ok("add_material", name="Unused")
    bridge.ok("assign_material", name="Box", material="Grey")
    bridge.ok("assign_material", name="Box", material="Red", facing="up")
    red = bridge.ok("mesh_query", name="Box", with_material="Red")
    assert red["total"] == 4 and all(face["material"] == "Red" for face in red["faces"])
    assert bridge.ok("mesh_query", name="Box", with_material="Unused")["total"] == 0
    bridge.refuse("mesh_query", "not_found", name="Box", with_material="Ghost")
    bridge.refuse("extrude", "bad_args", name="Box", distance=0.1, with_material="Unused")


def test_select_faces_by_normal_cone(bridge):
    subdivided_cube(bridge)
    both = bridge.ok("mesh_query", name="Box", normal=[1, 1, 0], normal_angle=50.0)
    assert both["total"] == 8
    assert bridge.ok("mesh_query", name="Box", normal=[1, 1, 0], normal_angle=30.0)["total"] == 0
    assert bridge.ok("mesh_query", name="Box", normal=[0, 0, -1], normal_angle=1.0)["total"] == 4
    bridge.refuse("mesh_query", "bad_args", name="Box", normal=[0, 0, 0])


def test_select_faces_by_island(bridge):
    bridge.ok("add_primitive", type="cube", name="A", size=1.0)
    bridge.ok("add_primitive", type="cube", name="B", size=1.0, location=[5.0, 0.0, 0.0])
    bridge.ok("join", names=["A", "B"])
    result = bridge.ok("mesh_query", name="A", island=1)
    assert result["total"] == 6 and result["islands"] == 2
    assert all(face["centre"][0] > 4 for face in result["faces"])
    assert bridge.ok("mesh_query", name="A", island=2)["total"] == 0


def test_select_faces_by_area_range_and_combinations(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("inset", name="Box", thickness=0.5, facing="up")
    assert bridge.ok("mesh_query", name="Box", area_min=0.9)["total"] == 6
    assert bridge.ok("mesh_query", name="Box", area_max=1.0)["total"] == 5
    assert bridge.ok("mesh_query", name="Box", area_min=0.9, area_max=1.1)["total"] == 1
    trapezoids = bridge.ok("mesh_query", name="Box", facing="up", area_max=0.8)
    assert trapezoids["total"] == 4
    close([face["area"] for face in trapezoids["faces"]], [0.75] * 4, 1e-6)


def test_transform_selection_moves_rotates_and_scales_about_a_pivot(bridge):
    subdivided_cube(bridge)
    result = bridge.ok("transform_selection", name="Box", facing="up", move=[0, 0, 1])
    assert result["transformed_vertices"] == 9 and result["bounds"]["max"][2] == 2.0
    bridge.ok("new_scene")
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("transform_selection", name="Box", facing="up", scale=[2.0, 2.0, 1.0])
    top = sorted((round(v.x, 6), round(v.y, 6), round(v.z, 6)) for v in vertices("Box") if v.z > 0)
    assert top == [(-2.0, -2.0, 1.0), (-2.0, 2.0, 1.0), (2.0, -2.0, 1.0), (2.0, 2.0, 1.0)]
    bridge.ok("new_scene")
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("transform_selection", name="Box", facing="up", rotate=[0, 0, 45.0])
    top = sorted((round(v.x, 5), round(v.y, 5)) for v in vertices("Box") if v.z > 0)
    root = round(math.sqrt(2.0), 5)
    assert top == sorted([(-root, 0.0), (root, 0.0), (0.0, -root), (0.0, root)])
    bridge.ok("new_scene")
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("transform_selection", name="Box", facing="up", scale=[2.0, 2.0, 1.0], pivot=[1, 1, 1])
    assert min(v.x for v in vertices("Box") if v.z > 0) == -3.0


def test_transform_selection_pushes_along_normals_and_takes_vertices(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("transform_selection", name="Box", facing="up", push=0.5)
    close(extent("Box")[2], 2.5, 1e-6)
    bridge.ok("transform_selection", name="Box", vertices=[0], move=[-1.0, 0.0, 0.0])
    close(min(vertex.x for vertex in vertices("Box")), -2.0, 1e-6)
    bridge.refuse("transform_selection", "bad_args", name="Box", vertices=[0], facing="up")
    bridge.refuse("transform_selection", "bad_args", name="Box", vertices=[99])
    bridge.refuse("transform_selection", "bad_args", name="Box", vertices=[0], push=1.0)
    bridge.refuse("transform_selection", "bad_args", name="Box", facing="up", scale=[1.0, 0.0, 1.0])
    bridge.refuse("transform_selection", "bad_args", name="Box", facing="up", box={"min": [5, 5, 5], "max": [6, 6, 6]})
    up = bridge.ok("mesh_query", name="Box", facing="up")["faces"][0]["index"]
    down = bridge.ok("mesh_query", name="Box", facing="down")["faces"][0]["index"]
    bridge.refuse("transform_selection", "bad_args", name="Box", faces=[up, down], push=1.0)


def top_edges(name):
    bm = mesh_bm(name)
    try:
        bm.faces.ensure_lookup_table()
        top = max(bm.faces, key=lambda face: face.calc_center_median().z)
        return sorted(edge.index for edge in top.edges)
    finally:
        bm.free()


def test_bevel_on_selected_edges_removes_the_hand_worked_volume(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    edges = top_edges("Box")
    result = bridge.ok("bevel", name="Box", width=0.1, edges=edges)
    assert result["bevelled_edges"] == 4
    inner = (2 - 0.2) ** 2
    removed = 0.4 - 0.1 / 3.0 * (inner + math.sqrt(inner * 4.0) + 4.0)
    close(volume("Box"), 8.0 - removed, 1e-5)
    assert not bpy.data.objects["Box"].data.has_custom_normals


def test_bevel_with_hardened_normals_keeps_flat_faces_flat(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.ok("bevel", name="Box", width=0.1, segments=2, edges=top_edges("Box"), harden_normals=True)
    mesh = bpy.data.objects["Box"].data
    assert mesh.has_custom_normals
    normals = [list(normal.vector) for normal in mesh.corner_normals]
    flat = 0
    for polygon in mesh.polygons:
        face = list(polygon.normal)
        if abs(sum(abs(c) for c in face) - 1.0) < 1e-4:
            flat += 1
            for loop in polygon.loop_indices:
                close(normals[loop], face, 1e-3)
    assert flat == 6
    rim = [loop for polygon in mesh.polygons if 0.05 < polygon.normal.z < 0.95 for loop in polygon.loop_indices]
    assert rim and all(normals[loop][2] > -1e-3 for loop in rim)
    assert any(abs(normals[loop][2] - 1.0) < 1e-3 for loop in rim)


def test_bevel_edges_refuse_bad_selections(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    bridge.refuse("bevel", "bad_args", name="Box", width=0.1, edges=[99])
    bridge.refuse("bevel", "bad_args", name="Box", width=0.1, edges=[0], facing="up")
    bridge.ok("add_primitive", type="plane", name="Sheet")
    bridge.refuse("bevel", "bad_args", name="Sheet", width=0.1, edges=[0])
    before = settled_snapshot()
    bridge.refuse("bevel", "bad_args", name="Box", width=0.1, edges=[99], harden_normals=True)
    assert settled_snapshot() == before


run(globals())
