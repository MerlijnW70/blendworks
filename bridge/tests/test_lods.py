import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "package"))

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from harness import close, run
from judge_geometry import DEGENERATE_AREA, triangle_areas, world_coordinates
from judge_uv import UvGrid
from package_locks import feature_vertices
from package_surface import triangle_soup

SPHERE_RADIUS = 1.0
SPHERE_SEGMENTS = 128
SPHERE_RINGS = 64
SPHERE_TRIANGLES = 2 * SPHERE_SEGMENTS * (SPHERE_RINGS - 1)


def sphere(bridge, name="Ball"):
    bridge.ok("add_primitive", type="sphere", name=name, radius=SPHERE_RADIUS, segments=SPHERE_SEGMENTS, rings=SPHERE_RINGS)
    bridge.ok("shade_smooth", name=name)
    return bpy.data.objects[name]


def triangles(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def seamed_cube(name="Seamed"):
    mesh = bpy.data.meshes.new(name)
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=2.0)
    bmesh.ops.subdivide_edges(builder, edges=builder.edges[:], cuts=15, use_grid_fill=True)
    builder.faces.ensure_lookup_table()
    layer = builder.loops.layers.uv.new("UVMap")
    for face in builder.faces:
        axis = max(range(3), key=lambda index: abs(face.normal[index]))
        sign = 1 if face.normal[axis] > 0 else -1
        u, v = [index for index in range(3) if index != axis]
        offset = (axis * 2 + (1 if sign > 0 else 0)) % 3
        for loop in face.loops:
            co = loop.vert.co
            loop[layer].uv = ((co[u] + 1) / 6 + (offset % 3) / 3, (co[v] + 1) / 4 + (0.5 if sign > 0 else 0.0))
    builder.to_mesh(mesh)
    builder.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def overlap(obj):
    grid = UvGrid()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    mesh.calc_loop_triangles()
    grid.add_mesh(mesh, triangle_areas(mesh, world_coordinates(mesh, evaluated.matrix_world)), DEGENERATE_AREA)
    evaluated.to_mesh_clear()
    return grid.overlap()


def seam_points(obj):
    mesh = obj.data
    flags = feature_vertices(mesh)["seam"]
    return {tuple(round(value, 5) for value in mesh.vertices[index].co) for index in np.flatnonzero(flags)}


def test_sphere_levels_follow_the_ratios_with_bounded_error(bridge):
    sphere(bridge)
    result = bridge.ok("generate_lods", count=2, ratios=[0.5, 0.25])
    levels = result["levels"]
    assert [level["level"] for level in levels] == [0, 1, 2]
    assert levels[0]["triangles"] == SPHERE_TRIANGLES
    for level, target in ((levels[1], 0.5), (levels[2], 0.25)):
        assert abs(level["triangles"] - target * SPHERE_TRIANGLES) <= 0.03 * SPHERE_TRIANGLES, level
        edge = math.sqrt(16 * math.pi * SPHERE_RADIUS**2 / (math.sqrt(3) * level["triangles"]))
        sagitta = edge**2 / 8
        assert level["hausdorff"] <= 8 * sagitta, (level["hausdorff"], sagitta)
        assert level["hausdorff_fraction"] == round(level["hausdorff"] / result["bounds_diagonal"], 6) or abs(level["hausdorff_fraction"] - level["hausdorff"] / result["bounds_diagonal"]) < 1e-5


def test_levels_are_named_and_keep_the_hierarchy(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=2.0)
    group = bpy.data.objects.new("Group", None)
    bpy.context.scene.collection.objects.link(group)
    group.location = (1.0, 2.0, 0.0)
    bridge.ok("parent", name="Box", parent="Group")
    bridge.ok("subdivide", name="Box", cuts=6)
    result = bridge.ok("generate_lods", count=2, ratios=[0.5, 0.2])
    assert result["levels"][0]["names"] == ["Box_LOD0"]
    assert result["levels"][2]["names"] == ["Box_LOD2"]
    for name in ("Box_LOD0", "Box_LOD1", "Box_LOD2"):
        assert bpy.data.objects[name].parent.name == "Group"
    assert "Box" not in bpy.data.objects
    close(list(bpy.data.objects["Box_LOD1"].matrix_world.translation), list(bpy.data.objects["Box_LOD0"].matrix_world.translation))


def test_uv_seams_and_overlap_are_kept(bridge):
    source = seamed_cube()
    seams = seam_points(source)
    before = overlap(source)
    assert len(seams) > 20
    result = bridge.ok("generate_lods", names=["Seamed"], count=1, ratios=[0.5])
    level = result["levels"][1]
    assert level["decimation"] == {"strict": 1}
    made = bpy.data.objects["Seamed_LOD1"]
    assert triangles(made) < triangles(bpy.data.objects["Seamed_LOD0"])
    assert seam_points(made) == seams
    assert overlap(made) <= before + 1e-6


def test_material_boundaries_are_kept(bridge):
    obj = seamed_cube("Plated")
    for name in ("steel", "brass"):
        obj.data.materials.append(bpy.data.materials.new(name))
    for polygon in obj.data.polygons:
        polygon.material_index = 1 if polygon.center.x > 0 else 0
    mesh = obj.data
    edge_points = lambda made: {tuple(round(value, 5) for value in made.data.vertices[index].co) for index in np.flatnonzero(feature_vertices(made.data)["material"])}
    boundary = edge_points(obj)
    assert boundary
    bridge.ok("generate_lods", names=["Plated"], count=1, ratios=[0.5])
    made = bpy.data.objects["Plated_LOD1"]
    assert edge_points(made) == boundary
    used = {polygon.material_index for polygon in made.data.polygons}
    assert used == {0, 1}
    assert [slot.material.name for slot in made.material_slots] == ["steel", "brass"]


def test_normals_follow_the_surface_after_decimation(bridge):
    sphere(bridge)
    bridge.ok("generate_lods", count=1, ratios=[0.25])
    mesh = bpy.data.objects["Ball_LOD1"].data
    mesh.calc_loop_triangles()
    normals = np.array([corner.vector for corner in mesh.corner_normals])
    loops = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loops)
    coordinates = np.array([vertex.co for vertex in mesh.vertices])[loops]
    radial = coordinates / np.linalg.norm(coordinates, axis=1)[:, None]
    angles = np.degrees(np.arccos(np.clip((normals * radial).sum(axis=1), -1, 1)))
    assert angles.mean() < 4.0 and np.percentile(angles, 99) < 12.0, (angles.mean(), np.percentile(angles, 99))


def test_screen_error_levels_stay_within_the_pixels(bridge):
    sphere(bridge)
    result = bridge.ok("generate_lods", count=2, max_screen_error=2.0, distances=[10.0, 40.0])
    first, second = result["levels"][1], result["levels"][2]
    for level, distance in ((first, 10.0), (second, 40.0)):
        assert level["distance"] == distance
        assert level["screen_error_pixels"] <= 2.0 * 1.0001, level
    assert second["triangles"] < first["triangles"] < SPHERE_TRIANGLES


def test_refusals(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    bridge.refuse("generate_lods", "bad_args", count=2, ratios=[0.5])
    bridge.refuse("generate_lods", "bad_args", count=1)
    bridge.refuse("generate_lods", "bad_args", count=1, ratios=[0.5], max_screen_error=1.0, distances=[5.0])
    bridge.refuse("generate_lods", "bad_args", count=1, max_screen_error=1.0)
    bridge.refuse("generate_lods", "not_found", names=["Ghost"], count=1, ratios=[0.5])
    bpy.data.objects["Box"].shape_key_add(name="Basis")
    bridge.refuse("generate_lods", "bad_args", names=["Box"], count=1, ratios=[0.5])


def test_a_second_run_is_refused_for_renamed_sources(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    bridge.ok("subdivide", name="Box", cuts=4)
    bridge.ok("generate_lods", count=1, ratios=[0.5])
    bridge.refuse("generate_lods", "bad_args", count=1, ratios=[0.5])


def test_linked_copies_share_their_levels(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    bridge.ok("subdivide", name="Box", cuts=8)
    source = bpy.data.objects["Box"]
    twin = bpy.data.objects.new("Twin", source.data)
    bpy.context.scene.collection.objects.link(twin)
    twin.location = Vector((3.0, 0.0, 0.0))
    bridge.ok("generate_lods", count=1, ratios=[0.5])
    assert bpy.data.objects["Box_LOD1"].data is bpy.data.objects["Twin_LOD1"].data


def test_the_add_on_ships_the_level_core_beside_the_bridge(bridge):
    sys.path.insert(0, os.path.dirname(HERE))
    from build_addon import addon_files

    shipped = {name for name, _ in addon_files()}
    assert "blendworks_bridge/commands/lods.py" in shipped
    for module in ("package_levels", "package_decimate", "package_locks", "package_error", "package_surface", "package_plan"):
        assert f"package/{module}.py" in shipped, module


def test_soup_counts_every_level(bridge):
    sphere(bridge)
    bridge.ok("generate_lods", count=1, ratios=[0.5])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    assert len(triangle_soup([bpy.data.objects["Ball_LOD0"]], depsgraph).triangles) == SPHERE_TRIANGLES


run(globals())
