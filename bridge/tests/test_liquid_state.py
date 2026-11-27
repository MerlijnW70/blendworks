import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
import numpy as np

from harness import run
from liquid_helpers import attribute, dimple, mesh_points

from blendworks_bridge import liquid_world

SHORE_BAND = 0.3
WIDE_BAND = 2.0
STRIP_WIDTH = 6.0
REACH = 3.0
QUERY_SHARE = 0.12
FIRST_CALL_SECONDS = 20.0
CACHED_CALL_SECONDS = 1.0


def hollows(name, size, cells, centres, radius, curvature):
    """A flat square with paraboloid hollows z = (r^2 - radius^2) / (2 curvature) at each centre."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=cells, y_segments=cells, size=size / 2.0)
    for vertex in bm.verts:
        depth = [min((((vertex.co.x - x) ** 2 + (vertex.co.y - y) ** 2) - radius * radius) / (2.0 * curvature), 0.0) for x, y in centres]
        vertex.co.z = min(depth)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def rock(bridge):
    bridge.ok("add_primitive", type="ico_sphere", name="Rock", radius=0.05, subdivisions=1)


def depth_reach(name):
    return float(bpy.data.objects[name].data[liquid_world.REACH_PROPERTY])


def test_deformed_ground_updates_liquid_depth_whatever_changed_it(bridge):
    """A ground raised in place keeps its vertex count; a ground moved keeps its mesh. Both made liquid_depth stale; now a
    mask measures the ground as it is."""
    dimple("Ground", 14.0, 140, 3.0, 3.0)
    bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[0.0, 0.0, 0.0], name="Pond")
    rock(bridge)
    first = attribute("Ground", liquid_world.DEPTH_ATTRIBUTE)
    assert first.max() > 0.3
    mesh = bpy.data.objects["Ground"].data
    raised = np.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", raised)
    raised[2::3] += 0.4
    mesh.vertices.foreach_set("co", raised)
    mesh.update()
    assert len(mesh.vertices) * 3 == len(raised)
    bridge.ok("scatter", target="Ground", source="Rock", min_distance=0.5, density_mask=["liquid"], name="Rocks")
    second = attribute("Ground", liquid_world.DEPTH_ATTRIBUTE)
    deep = first > 0.6
    assert deep.sum() > 100
    assert np.allclose(second[deep], first[deep] - 0.4, atol=2e-3), (second[deep][:3], first[deep][:3])
    bridge.ok("transform", name="Ground", location=[0.0, 0.0, 0.5])
    bridge.ok("scatter", target="Ground", source="Rock", min_distance=0.5, density_mask=["liquid"], name="MoreRocks")
    third = attribute("Ground", liquid_world.DEPTH_ATTRIBUTE)
    assert np.allclose(third[deep], first[deep] - 0.9, atol=2e-3), (third[deep][:3], first[deep][:3])


def test_unchanged_ground_keeps_its_measured_depth(bridge):
    """The digest changes only with the geometry: a second mask on the same ground does not measure again."""
    dimple("Ground", 12.0, 120, 1.5, 3.0)
    bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[0.0, 0.0, 0.0], name="Pond")
    rock(bridge)
    bridge.ok("scatter", target="Ground", source="Rock", min_distance=0.5, density_mask=["liquid"], name="Rocks")
    before = liquid_world.Water.total_queries
    bridge.ok("scatter", target="Ground", source="Rock", min_distance=0.5, density_mask=["liquid"], name="MoreRocks")
    assert liquid_world.Water.total_queries == before


def test_each_water_body_keeps_its_own_wet_band(bridge):
    """The last body's shore_width used to overwrite the earlier body's band: both ponds now wet by their own width."""
    hollows("Ground", 30.0, 300, [(-8.0, 0.0), (8.0, 0.0)], 2.0, 4.0)
    first = bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[-8.0, 0.0, 0.0], name="NarrowPond", shore_width=SHORE_BAND)
    second = bridge.ok("liquid_body", kind="pond", ground=["Ground"], point=[8.0, 0.0, 0.0], name="WidePond", shore_width=WIDE_BAND)
    assert first["shore"]["width"] == SHORE_BAND and second["shore"]["width"] == WIDE_BAND
    points = mesh_points("Ground")
    wet = attribute("Ground", liquid_world.WET_ATTRIBUTE)
    for pond, centre in ((first, -8.0), (second, 8.0)):
        pond["edge"] = float(np.sqrt(pond["area"] / np.pi))
        pond["from_edge"] = np.hypot(points[:, 0] - centre, points[:, 1]) - pond["edge"]
    near_narrow = (first["from_edge"] > 0.7) & (first["from_edge"] < 1.2)
    near_wide = (second["from_edge"] > 0.4) & (second["from_edge"] < 0.8)
    assert near_narrow.sum() > 50 and near_wide.sum() > 50
    assert wet[near_narrow].max() == 0.0, "the narrow pond's ground beyond its own band is dry"
    assert wet[near_wide].min() > 0.05, "the wide pond's band reaches past the narrow one's"
    assert wet[(first["from_edge"] < -0.1)].min() == 1.0


def long_strip(name, level, width, length, pieces=200):
    """A thin diagonal sheet of water at a level, flagged as a liquid, made of many short quads as a river's sheet is."""
    mesh = bpy.data.meshes.new(name)
    half = width / 2.0
    direction = np.array([1.0, 1.0]) / np.sqrt(2.0)
    across = np.array([-direction[1], direction[0]])
    points, faces = [], []
    for step in range(pieces + 1):
        centre = (step / pieces - 0.5) * length * direction
        for sign in (-1.0, 1.0):
            points.append((*(centre + sign * half * across), level))
    for step in range(pieces):
        faces.append((2 * step, 2 * step + 1, 2 * step + 3, 2 * step + 2))
    mesh.from_pydata(points, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj[liquid_world.LIQUID_PROPERTY] = "river"
    bpy.context.scene.collection.objects.link(obj)
    return direction, across


def test_the_depth_measure_stays_bounded_on_a_big_terrain(bridge):
    """A ground cover or scatter on a terrain of a quarter million vertices crossed by a narrow river measures only the points near
    the water, once: the first measure asks the surface about a small share of the vertices and the next ones read the result."""
    size, cells, level = 500.0, 500, 0.2
    ground = bpy.data.meshes.new("Big")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=cells, y_segments=cells, size=size / 2.0)
    bm.to_mesh(ground)
    bm.free()
    obj = bpy.data.objects.new("Big", ground)
    bpy.context.scene.collection.objects.link(obj)
    direction, across = long_strip("River", level, STRIP_WIDTH, 2.0 * size)
    bpy.context.view_layer.update()
    vertices = len(ground.vertices)
    assert vertices > 250_000
    depsgraph = bpy.context.evaluated_depsgraph_get()
    queries = liquid_world.Water.total_queries
    started = time.perf_counter()
    measured = liquid_world.target_depth(obj, depsgraph, REACH)
    first = time.perf_counter() - started
    asked = liquid_world.Water.total_queries - queries
    assert first < FIRST_CALL_SECONDS, first
    assert asked < QUERY_SHARE * vertices, (asked, vertices)
    points = mesh_points("Big")
    sideways = np.abs(points[:, :2] @ across)
    inside = sideways < STRIP_WIDTH / 2.0
    assert np.allclose(measured[inside], level, atol=1e-4), "points under the river read its depth"
    dry = sideways - STRIP_WIDTH / 2.0
    expected = -np.minimum(np.hypot(dry, level), REACH)
    sample = (~inside) & (dry < 40.0)
    assert np.allclose(measured[sample], expected[sample], atol=2e-3), "dry points read minus their distance to the water"
    assert (measured[dry > REACH + 1.0] == -REACH).all(), "points further than the reach read minus the reach"
    queries = liquid_world.Water.total_queries
    started = time.perf_counter()
    again = liquid_world.target_depth(obj, depsgraph, REACH)
    cached = time.perf_counter() - started
    assert liquid_world.Water.total_queries == queries and cached < CACHED_CALL_SECONDS, (cached, liquid_world.Water.total_queries - queries)
    assert np.array_equal(again, measured)


run(globals())
