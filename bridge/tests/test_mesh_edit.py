import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run


def cube(bridge, name="Box", size=2.0):
    bridge.ok("add_primitive", type="cube", name=name, size=size)


def test_extrude_region_moves_faces_out(bridge):
    cube(bridge)
    result = bridge.ok("extrude", name="Box", facing="up", distance=1.0)
    assert result["extruded_faces"] == 1
    assert result["mesh"] == {"vertices": 12, "edges": 20, "faces": 10, "triangles": 20}
    close(bridge.info("Box")["bounds"]["max"], [1.0, 1.0, 2.0])


def test_extrude_inward_and_individual(bridge):
    cube(bridge)
    bridge.ok("extrude", name="Box", facing="up", distance=-0.5)
    close(bridge.info("Box")["bounds"]["max"], [1.0, 1.0, 1.0])
    cube(bridge, "Other")
    result = bridge.ok("extrude", name="Other", distance=0.5, individual=True)
    assert result["extruded_faces"] == 6
    assert result["mesh"]["faces"] == 30
    close(bridge.info("Other")["bounds"]["size"], [3.0, 3.0, 3.0])


def test_extrude_refuses_bad_selections(bridge):
    cube(bridge)
    bridge.refuse("extrude", "bad_args", name="Box", distance=0.0)
    bridge.refuse("extrude", "bad_args", name="Box", faces=[6], distance=1.0)
    bridge.ok("add_primitive", type="plane", name="Floor")
    bridge.refuse("extrude", "bad_args", name="Floor", facing="down", distance=1.0)
    bridge.ok("add_light", type="point", name="Lamp")
    bridge.refuse("extrude", "bad_args", name="Lamp", distance=1.0)
    bridge.refuse("extrude", "not_found", name="Ghost", distance=1.0)


def test_inset_adds_a_ring_of_faces(bridge):
    cube(bridge)
    result = bridge.ok("inset", name="Box", facing="up", thickness=0.25, depth=0.1)
    assert result["mesh"] == {"vertices": 12, "edges": 20, "faces": 10, "triangles": 20}
    close(bridge.info("Box")["bounds"]["max"], [1.0, 1.0, 1.1])
    mesh = bpy.data.objects["Box"].data
    top = [polygon for polygon in mesh.polygons if polygon.center.z > 1.05]
    assert len(top) == 1
    xs = [mesh.vertices[index].co.x for index in top[0].vertices]
    close([min(xs), max(xs)], [-0.75, 0.75])


def test_inset_refuses_bad_arguments(bridge):
    cube(bridge)
    bridge.refuse("inset", "bad_args", name="Box", thickness=0.0)
    bridge.refuse("inset", "bad_args", name="Box", thickness=0.1, facing="sideways")


def test_bevel_rounds_sharp_edges(bridge):
    cube(bridge)
    result = bridge.ok("bevel", name="Box", width=0.1)
    assert result["bevelled_edges"] == 12
    assert result["mesh"] == {"vertices": 24, "edges": 48, "faces": 26, "triangles": 44}
    close(bridge.info("Box")["bounds"]["size"], [2.0, 2.0, 2.0])


def test_bevel_only_edges_of_selected_faces(bridge):
    cube(bridge)
    result = bridge.ok("bevel", name="Box", width=0.1, facing="up", segments=2)
    assert result["bevelled_edges"] == 4


def test_bevel_refuses_when_nothing_is_sharp(bridge):
    cube(bridge)
    bridge.refuse("bevel", "bad_args", name="Box", width=0.1, angle=100.0)
    bridge.refuse("bevel", "bad_args", name="Box", width=0.1, segments=0)


def test_subdivide_splits_faces(bridge):
    cube(bridge)
    result = bridge.ok("subdivide", name="Box", cuts=1)
    assert result["mesh"] == {"vertices": 26, "edges": 48, "faces": 24, "triangles": 48}


def test_subdivide_refuses_over_the_vertex_cap(bridge):
    bridge.ok("add_primitive", type="ico_sphere", name="Ball", subdivisions=7)
    message = bridge.refuse("subdivide", "failed", name="Ball", cuts=10)
    assert "cap" in message
    assert len(bpy.data.objects["Ball"].data.vertices) == 40962
    bridge.refuse("subdivide", "bad_args", name="Ball", cuts=11)


def test_shade_smooth_and_flat(bridge):
    cube(bridge)
    bridge.ok("shade_smooth", name="Box")
    mesh = bpy.data.objects["Box"].data
    assert all(polygon.use_smooth for polygon in mesh.polygons)
    bridge.ok("shade_smooth", name="Box", angle=30.0)
    sharp = mesh.attributes.get("sharp_edge")
    assert sharp is not None and all(item.value for item in sharp.data)
    result = bridge.ok("shade_flat", name="Box", facing="up")
    assert result["flat_faces"] == 1
    assert sum(1 for polygon in mesh.polygons if not polygon.use_smooth) == 1


def test_shade_refuses_non_meshes(bridge):
    bridge.ok("add_light", type="point", name="Lamp")
    bridge.refuse("shade_smooth", "bad_args", name="Lamp")
    bridge.refuse("shade_flat", "bad_args", name="Lamp")
    cube(bridge)
    bridge.refuse("shade_smooth", "bad_args", name="Box", angle=200.0)


def outward(obj):
    mesh = obj.data
    return [polygon.normal.dot(polygon.center) > 0 for polygon in mesh.polygons]


def test_recalc_normals_points_out_or_in(bridge):
    cube(bridge)
    bridge.ok("recalc_normals", name="Box", inside=True)
    assert not any(outward(bpy.data.objects["Box"]))
    bridge.ok("recalc_normals", name="Box")
    assert all(outward(bpy.data.objects["Box"]))


def test_recalc_normals_refuses_unknown(bridge):
    bridge.refuse("recalc_normals", "not_found", name="Ghost")
    cube(bridge)
    bridge.refuse("recalc_normals", "bad_args", name="Box", inside="yes")


def test_merge_by_distance_welds_doubles(bridge):
    cube(bridge, "A")
    cube(bridge, "B")
    bridge.ok("join", names=["A", "B"])
    result = bridge.ok("merge_by_distance", name="A", distance=0.001)
    assert result["removed_vertices"] == 8
    assert result["mesh"]["vertices"] == 8


def test_merge_by_distance_refuses_zero(bridge):
    cube(bridge)
    bridge.refuse("merge_by_distance", "bad_args", name="Box", distance=0.0)


run(globals())
