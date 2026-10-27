import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from noise_helpers import grid_plane
from scatter_helpers import axes, copies, face_data, locations, make_bolt, make_ground, make_terrain, scales, smallest_distance

SLACK = 1e-4


def add_point_attribute(name, attribute, values):
    mesh = bpy.data.objects[name].data
    mesh.attributes.new(attribute, "FLOAT", "POINT").data.foreach_set("value", values)


def polygon_slopes(name):
    mesh = bpy.data.objects[name].data
    normals = numpy.array([list(polygon.normal) for polygon in mesh.polygons])
    areas = numpy.array([polygon.area for polygon in mesh.polygons])
    return numpy.degrees(numpy.arccos(numpy.clip(normals[:, 2], -1.0, 1.0))), areas


def test_no_instance_sits_on_a_face_outside_the_slope_range(bridge):
    make_terrain(bridge)
    make_bolt(bridge)
    plain = bridge.ok("scatter", target="Terrain", source="Bolt", min_distance=1.0, seed=2, name="Plain")
    assert face_data("Terrain", locations("Plain"))[0].max() > 40.0
    result = bridge.ok("scatter", target="Terrain", source="Bolt", min_distance=1.0, seed=2, name="Flat", density_mask=["slope"], slope_range=[5.0, 30.0])
    slopes, _ = face_data("Terrain", locations("Flat"))
    assert result["count"] > 50
    assert slopes.min() >= 5.0 - SLACK and slopes.max() <= 30.0 + SLACK
    slopes_all, areas = polygon_slopes("Terrain")
    inside = areas[(slopes_all >= 5.0) & (slopes_all <= 30.0)].sum() / areas.sum()
    assert abs(result["masked_out"] - (1.0 - inside)) < 0.03
    assert plain["masked_out"] == 0.0 and result["count"] < plain["count"]


def test_no_instance_sits_where_a_named_attribute_is_below_its_threshold(bridge):
    make_ground(bridge)
    make_bolt(bridge)
    mesh = bpy.data.objects["Ground"].data
    add_point_attribute("Ground", "wet", [vertex.co.x / 10.0 for vertex in mesh.vertices])
    open_run = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.5, seed=4, name="Open", group=False)
    assert locations("Open")[:, 0].min() < 0.0
    result = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.5, seed=4, name="Wet", group=False, density_mask=["attribute"], attribute="wet", attribute_range=[0.2, 0.2])
    points = locations("Wet")
    assert len(points) > 50 and points[:, 0].min() / 10.0 >= 0.2 - SLACK
    assert abs(result["masked_out"] - 0.7) < 0.02 and open_run["masked_out"] == 0.0
    ramp = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.5, seed=4, name="Ramp", group=False, density_mask=["attribute"], attribute="wet", attribute_range=[-0.5, 0.5])
    assert locations("Ramp")[:, 0].mean() > 0.1 and abs(ramp["masked_out"] - 0.5) < 0.03


def test_the_heightfield_attributes_work_as_masks(bridge):
    make_terrain(bridge)
    make_bolt(bridge)
    bridge.ok("scatter", target="Terrain", source="Bolt", min_distance=1.0, seed=2, name="High", group=False, density_mask=["attribute"], attribute="height", attribute_range=[12.0, 12.0])
    assert len(locations("High")) > 20 and locations("High")[:, 2].min() >= 12.0 - 0.05
    bridge.ok("scatter", target="Terrain", source="Bolt", min_distance=1.0, seed=2, name="Band", group=False, density_mask=["height"], height_range=[11.0, 13.0])
    assert len(locations("Band")) > 20 and 11.0 - SLACK <= locations("Band")[:, 2].min() and locations("Band")[:, 2].max() <= 13.0 + SLACK


def test_masks_multiply_and_vertex_group_and_noise_masks_apply(bridge):
    grid_plane("Ground", 10.0, 20)
    make_bolt(bridge)
    ground = bpy.data.objects["Ground"]
    group = ground.vertex_groups.new(name="Moss")
    for vertex in ground.data.vertices:
        group.add([vertex.index], 1.0 if vertex.co.y > 0 else 0.0, "REPLACE")
    half = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.4, seed=1, name="Half", group=False, density_mask=["vertex_group"], vertex_group="Moss")
    assert locations("Half")[:, 1].min() >= -0.5 - SLACK
    assert abs(half["masked_out"] - 0.5) < 0.03
    add_point_attribute("Ground", "x", [vertex.co.x for vertex in ground.data.vertices])
    both = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.4, seed=1, name="Quarter", group=False, density_mask=["vertex_group", "attribute"], vertex_group="Moss", attribute="x", attribute_range=[0.0, 0.0])
    points = locations("Quarter")
    assert points[:, 1].min() >= -0.5 - SLACK and points[:, 0].min() >= -SLACK
    assert abs(both["masked_out"] - 0.75) < 0.03
    noisy = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.4, seed=1, name="Patches", group=False, density_mask=["noise"], noise={"scale": 4.0, "seed": 3, "threshold": 0.5, "softness": 0.05})
    assert 0.2 < noisy["masked_out"] < 0.8


def test_align_tilt_yaw_and_embed_place_the_pieces_on_the_surface(bridge):
    make_terrain(bridge)
    bridge.ok("add_primitive", type="cylinder", name="Rock", radius=0.2, depth=0.6, segments=8, location=[100.0, 100.0, 0.0])
    settings = dict(target="Terrain", source="Rock", min_distance=1.5, seed=6, group=False)
    bridge.ok("scatter", name="Normal", align="normal", **settings)
    bridge.ok("scatter", name="Up", align="up", **settings)
    bridge.ok("scatter", name="Blend", align="blend", align_factor=0.5, **settings)
    bridge.ok("scatter", name="Tilted", align="up", tilt=20.0, **settings)
    bridge.ok("scatter", name="Sunk", align="up", embed=0.5, **settings)
    up = numpy.array([0.0, 0.0, 1.0])
    assert numpy.allclose(axes("Up"), up, atol=1e-6)
    normal_tilt = numpy.degrees(numpy.arccos(np_clip(axes("Normal") @ up)))
    blend_tilt = numpy.degrees(numpy.arccos(np_clip(axes("Blend") @ up)))
    assert normal_tilt.max() > 25.0 and numpy.all(blend_tilt <= normal_tilt + 1.0) and blend_tilt.mean() < 0.75 * normal_tilt.mean()
    leaning = numpy.degrees(numpy.arccos(np_clip(axes("Tilted") @ up)))
    assert leaning.max() <= 20.0 + 1e-4 and leaning.max() > 15.0
    assert numpy.allclose(locations("Up")[:, :2], locations("Sunk")[:, :2], atol=1e-5)
    assert numpy.allclose(locations("Up")[:, 2] - locations("Sunk")[:, 2], 0.5 * 0.6, atol=1e-5)
    yaws = [math.atan2(obj.matrix_world[1][0], obj.matrix_world[0][0]) for obj in copies("Up")]
    assert numpy.std(yaws) > 1.5
    bridge.ok("scatter", name="Fixed", align="up", random_yaw=False, **settings)
    assert all(abs(obj.matrix_world[1][0]) < 1e-6 for obj in copies("Fixed"))


def np_clip(values):
    return numpy.clip(values, -1.0, 1.0)


def test_sources_follow_their_weights_and_realize_merges_each_source(bridge):
    make_ground(bridge, size=20.0)
    make_bolt(bridge, "Bolt")
    bridge.ok("add_primitive", type="cube", name="Block", size=0.1, location=[100.0, 100.0, 0.0])
    result = bridge.ok("scatter", target="Ground", sources=[{"name": "Bolt", "weight": 3.0}, {"name": "Block"}], min_distance=0.5, seed=3, name="Mixed")
    bolts, blocks = copies("Mixed_Bolt"), copies("Mixed_Block")
    assert len(bolts) + len(blocks) == result["count"] and 2.4 < len(bolts) / len(blocks) < 3.8
    assert all(obj.parent is not None and obj.parent.name == "Mixed" for obj in bolts + blocks)
    realized = bridge.ok("scatter", target="Ground", sources=[{"name": "Bolt"}, {"name": "Block"}], min_distance=0.5, seed=3, name="Merged", realize=True)
    assert realized["realized"] is True and len(realized["objects"]) == 2
    bolt_vertices, block_vertices = (len(bpy.data.objects[name].data.vertices) for name in realized["objects"])
    assert bolt_vertices % 16 == 0 and block_vertices % 8 == 0 and bolt_vertices // 16 + block_vertices // 8 == realized["count"]
    single = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=1.0, seed=3, name="One", realize=True)
    assert single["realized"] is True and single["mesh"]["vertices"] == single["count"] * 16


def test_density_and_max_count_cap_the_instances(bridge):
    make_ground(bridge)
    make_bolt(bridge)
    capped = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.2, density=0.5, seed=1, name="Few", group=False)
    assert capped["count"] <= 0.5 * 100.0 and capped["count"] > 30
    limited = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.5, max_count=40, seed=1, name="Cut", group=False)
    assert limited["count"] == 40 and len(copies("Cut")) == 40
    assert smallest_distance(locations("Cut")) >= 0.5 - 1e-6
    power = bridge.ok("scatter", target="Ground", source="Bolt", min_distance=0.2, scale_range=[1.0, 4.0], scale_distribution="power", max_count=25, seed=1, name="PowerCut", group=False)
    assert power["count"] == 25


def test_scatter_refuses_inconsistent_arguments(bridge):
    make_ground(bridge)
    make_bolt(bridge)
    bridge.refuse("scatter", "bad_args", target="Ground", min_distance=0.5)
    bridge.refuse("scatter", "bad_args", target="Ground", source="Bolt", sources=[{"name": "Bolt"}], min_distance=0.5)
    bridge.refuse("scatter", "bad_args", target="Ground", source="Ground", min_distance=0.5)
    bridge.refuse("scatter", "bad_args", target="Ground", source="Bolt", min_distance=0.5, slope_range=[0, 30])
    bridge.refuse("scatter", "bad_args", target="Ground", source="Bolt", min_distance=0.5, density_mask=["slope"])
    bridge.refuse("scatter", "not_found", target="Ground", source="Bolt", min_distance=0.5, density_mask=["attribute"], attribute="missing", attribute_range=[0, 1])
    bridge.refuse("scatter", "bad_args", target="Ground", source="Bolt", min_distance=0.5, scale_range=[2.0, 1.0])
    bridge.refuse("scatter", "bad_args", target="Ground", source="Bolt", min_distance=0.5, scale_range=[0.1, 10.0], scale_distribution="power")
    bridge.refuse("scatter", "bad_args", target="Ground", source="Bolt", min_distance=0.5, max_count=20_001)
    bridge.refuse("scatter", "bad_args", target="Ground", source="Bolt", min_distance=0.5, density_mask=["height"], height_range=[50.0, 60.0])
    bridge.refuse("scatter", "not_found", target="Nowhere", source="Bolt", min_distance=0.5)
    bridge.refuse("scatter", "bad_args", target="Bolt", source="Bolt", min_distance=0.5)


run(globals())
