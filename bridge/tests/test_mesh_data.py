import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import settled_snapshot

QUAD = {"vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], "faces": [[0, 1, 2, 3]]}
STRIP = {"vertices": [[0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 1, 0], [1, 1, 0], [2, 1, 0]], "faces": [[0, 1, 4, 3], [1, 2, 5, 4]]}
CUBE = {
    "vertices": [[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)],
    "faces": [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]],
}


def write_json(bridge, name, content):
    path = os.path.join(bridge.workspace, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content if isinstance(content, str) else json.dumps(content))
    return name


def test_material_indices_fill_the_slots(bridge):
    bridge.ok("add_material", name="Red", base_color=[1.0, 0.0, 0.0])
    bridge.ok("add_material", name="Blue", base_color=[0.0, 0.0, 1.0])
    result = bridge.ok("mesh_from_data", name="Strip", **STRIP, material_indices=[0, 1], materials=["Red", "Blue"])
    mesh = bpy.data.objects["Strip"].data
    assert [polygon.material_index for polygon in mesh.polygons] == [0, 1]
    assert [material.name for material in mesh.materials] == ["Red", "Blue"]
    assert result["corrected"] is False
    bridge.ok("mesh_from_data", name="Loose", **STRIP, material_indices=[3, 5])
    assert [polygon.material_index for polygon in bpy.data.objects["Loose"].data.polygons] == [3, 5]


def test_uvs_per_corner_and_per_vertex(bridge):
    corners = [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]]
    bridge.ok("mesh_from_data", name="Corners", **QUAD, uvs=corners)
    layer = bpy.data.objects["Corners"].data.uv_layers.active.data
    close([list(item.uv) for item in layer], corners, 1e-6)
    per_vertex = [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0], [0.0, 1.0], [0.5, 1.0], [1.0, 1.0]]
    bridge.ok("mesh_from_data", name="Shared", **STRIP, vertex_uvs=per_vertex)
    mesh = bpy.data.objects["Shared"].data
    layer = mesh.uv_layers.active.data
    for polygon in mesh.polygons:
        for loop, vertex in zip(polygon.loop_indices, polygon.vertices):
            close(list(layer[loop].uv), per_vertex[vertex], 1e-6)
    bridge.ok("mesh_from_data", name="Plain", **QUAD)
    assert len(bpy.data.objects["Plain"].data.uv_layers) == 0


def test_smooth_flags_sharp_edges_and_creases(bridge):
    bridge.ok("mesh_from_data", name="Flat", **STRIP)
    assert [polygon.use_smooth for polygon in bpy.data.objects["Flat"].data.polygons] == [False, False]
    bridge.ok("mesh_from_data", name="Round", **STRIP, smooth=True)
    assert all(polygon.use_smooth for polygon in bpy.data.objects["Round"].data.polygons)
    bridge.ok("mesh_from_data", name="Half", **STRIP, smooth_faces=[1])
    assert [polygon.use_smooth for polygon in bpy.data.objects["Half"].data.polygons] == [False, True]
    bridge.ok("mesh_from_data", name="Hard", **CUBE, sharp_edges=[[0, 1], [2, 3]], creases=[{"edge": [0, 1], "value": 0.5}, {"edge": [4, 5], "value": 1.0}])
    mesh = bpy.data.objects["Hard"].data
    sharp = {tuple(sorted(edge.vertices)) for edge in mesh.edges if edge.use_edge_sharp}
    assert sharp == {(0, 1), (2, 3)}
    values = {tuple(sorted(edge.vertices)): value.value for edge, value in zip(mesh.edges, mesh.attributes["crease_edge"].data)}
    close([values[(0, 1)], values[(4, 5)], values[(0, 2)]], [0.5, 1.0, 0.0], 1e-6)


def test_mesh_is_read_from_a_json_file_in_the_workspace(bridge):
    document = {**CUBE, "material_indices": [0, 0, 1, 1, 2, 2], "smooth": True, "creases": [{"edge": [0, 1], "value": 0.25}]}
    name = write_json(bridge, "meshes/cube.json", document)
    result = bridge.ok("mesh_from_data", name="FromFile", path=name, location=[1, 2, 3])
    assert result["mesh"]["vertices"] == 8 and result["mesh"]["faces"] == 6
    mesh = bpy.data.objects["FromFile"].data
    assert [polygon.material_index for polygon in mesh.polygons] == [0, 0, 1, 1, 2, 2]
    assert list(bpy.data.objects["FromFile"].location) == [1.0, 2.0, 3.0]


def test_a_file_of_100000_vertices_is_accepted_and_one_more_is_refused(bridge):
    side = 316
    vertices = [[x * 0.01, y * 0.01, 0.0] for y in range(side) for x in range(side)]
    faces = [[y * side + x, y * side + x + 1, (y + 1) * side + x + 1, (y + 1) * side + x] for y in range(side - 1) for x in range(side - 1)]
    name = write_json(bridge, "big.json", {"vertices": vertices, "faces": faces})
    result = bridge.ok("mesh_from_data", name="Big", path=name)
    assert result["mesh"]["vertices"] == side * side and side * side <= 100_000
    exactly = vertices + [[0.0, 0.0, float(index)] for index in range(100_000 - len(vertices))]
    bridge.ok("mesh_from_data", name="Exact", path=write_json(bridge, "exact.json", {"vertices": exactly, "edges": [[0, 1]]}))
    over = vertices + [[0.0, 0.0, float(index)] for index in range(100_001 - len(vertices))]
    message = bridge.refuse("mesh_from_data", "bad_args", name="Over", path=write_json(bridge, "over.json", {"vertices": over, "edges": [[0, 1]]}))
    assert "100000" in message
    bridge.refuse("mesh_from_data", "bad_args", name="OverInline", vertices=over, edges=[[0, 1]])


def test_mesh_from_data_refuses_bad_files_and_paths(bridge):
    write_json(bridge, "broken.json", "{not json")
    write_json(bridge, "extra.json", {**QUAD, "colour": [1, 2, 3]})
    write_json(bridge, "empty.json", {"faces": [[0, 1, 2]]})
    write_json(bridge, "notes.txt", "{}")
    good = write_json(bridge, "quad.json", QUAD)
    bridge.refuse("mesh_from_data", "bad_args", name="A", path="broken.json")
    bridge.refuse("mesh_from_data", "bad_args", name="A", path="extra.json")
    bridge.refuse("mesh_from_data", "bad_args", name="A", path="empty.json")
    bridge.refuse("mesh_from_data", "forbidden", name="A", path="../outside.json")
    bridge.refuse("mesh_from_data", "forbidden", name="A", path="notes.txt")
    bridge.refuse("mesh_from_data", "not_found", name="A", path="missing.json")
    bridge.refuse("mesh_from_data", "bad_args", name="A", path=good, vertices=QUAD["vertices"])
    bridge.refuse("mesh_from_data", "bad_args", name="A", path=good, faces=QUAD["faces"])
    bridge.refuse("mesh_from_data", "bad_args", name="A")


def test_mesh_from_data_refuses_inconsistent_data(bridge):
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, uvs=[[0, 0], [1, 0], [1, 1]])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, vertex_uvs=[[0, 0]])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, uvs=[[0, 0]] * 4, vertex_uvs=[[0, 0]] * 4)
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, material_indices=[0, 1])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, smooth=True, smooth_faces=[0])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, smooth_faces=[3])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, sharp_edges=[[0, 2]])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, creases=[{"edge": [0, 2], "value": 0.5}])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, creases=[{"edge": [0, 1], "value": 1.5}])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, sharp_edges=[[0, 9]])
    bridge.refuse("mesh_from_data", "bad_args", name="A", vertices=QUAD["vertices"], faces=[[0, 1, 1]])
    bridge.refuse("mesh_from_data", "bad_args", name="A", vertices=QUAD["vertices"], faces=[[0, 1, 9]])
    bridge.refuse("mesh_from_data", "bad_args", name="A", vertices=QUAD["vertices"])
    bridge.refuse("mesh_from_data", "not_found", name="A", **QUAD, materials=["Ghost"])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **STRIP, material_indices=[40000, 0])


def test_duplicate_faces_are_corrected_unless_per_face_data_would_be_lost(bridge):
    twice = {"vertices": QUAD["vertices"], "faces": [[0, 1, 2, 3], [0, 1, 2, 3]]}
    result = bridge.ok("mesh_from_data", name="Twice", **twice)
    assert result["corrected"] is True and result["mesh"]["faces"] == 1
    bridge.refuse("mesh_from_data", "bad_args", name="Lossy", **twice, smooth=True)
    bridge.refuse("mesh_from_data", "bad_args", name="Lossy", **twice, material_indices=[0, 1])


def test_failed_mesh_from_data_leaves_the_scene_unchanged(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    before = settled_snapshot()
    bridge.refuse("mesh_from_data", "not_found", name="A", **QUAD, materials=["Ghost"])
    bridge.refuse("mesh_from_data", "bad_args", name="A", **QUAD, sharp_edges=[[0, 2]])
    assert settled_snapshot() == before
    assert "A" not in bpy.data.meshes


run(globals())
