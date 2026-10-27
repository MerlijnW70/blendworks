import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "judge"))

from harness import close, run

import bpy
import numpy
from judge_shells import mesh_topology

from blendworks_bridge.noise_stack import stack_field
from noise_helpers import grid_plane, world_points

FIELD = {"seed": 7, "scale": 40.0, "octaves": 5, "hurst": 0.7, "mode": "ridged", "ridge_offset": 0.9, "warp": 6.0, "warp_octaves": 2}
TILE = {"size": [50.0, 30.0], "resolution": 41, "height": 12.0, **FIELD}


def edge(name, along_x, at_far_side):
    points = world_points(name)
    column = 0 if along_x else 1
    wanted = points[:, column].max() if at_far_side else points[:, column].min()
    kept = points[numpy.isclose(points[:, column], wanted, atol=1e-6)]
    return kept[numpy.argsort(kept[:, 1 - column])]


def tile_uvs(name):
    mesh = bpy.data.objects[name].data
    flat = numpy.empty(len(mesh.uv_layers[0].uv) * 2)
    mesh.uv_layers[0].uv.foreach_get("vector", flat)
    return flat.reshape(-1, 2)


def test_neighbouring_tiles_share_their_edge_heights_exactly(bridge):
    for index, tile in enumerate(([0, 0], [1, 0], [0, 1], [1, 1])):
        bridge.ok("heightfield", name=f"T{tile[0]}{tile[1]}", tile=tile, **TILE)
    right, left = edge("T00", True, True), edge("T10", True, False)
    assert len(right) == len(left) == 41
    assert numpy.max(numpy.abs(right[:, 2] - left[:, 2])) < 1e-9 and numpy.max(numpy.abs(right[:, :2] - left[:, :2])) < 1e-5
    assert numpy.ptp(right[:, 2]) > 1.0
    top, bottom = edge("T00", False, True), edge("T01", False, False)
    assert numpy.max(numpy.abs(top[:, 2] - bottom[:, 2])) < 1e-9
    assert numpy.max(numpy.abs(edge("T10", False, True)[:, 2] - edge("T11", False, False)[:, 2])) < 1e-9
    assert numpy.max(numpy.abs(edge("T01", True, True)[:, 2] - edge("T11", True, False)[:, 2])) < 1e-9


def test_a_tile_is_the_world_field_sampled_at_its_place_and_stays_inside_its_height(bridge):
    result = bridge.ok("heightfield", name="Tile", tile=[-2, 3], base_height=5.0, **TILE)
    points = world_points("Tile")
    assert numpy.allclose(points[:, 0].min(), -100.0) and numpy.allclose(points[:, 0].max(), -50.0)
    assert numpy.allclose(points[:, 1].min(), 90.0) and numpy.allclose(points[:, 1].max(), 120.0)
    stack = {**FIELD, "basis": "perlin", "lacunarity": 2.0}
    expected = 5.0 + 12.0 * stack_field(numpy.column_stack([points[:, :2], numpy.zeros(len(points))]), stack)
    assert numpy.max(numpy.abs(points[:, 2] - expected)) < 1e-4
    assert points[:, 2].max() <= 5.0 + 12.0 * 0.9 + 1e-4 and points[:, 2].min() >= 5.0 - 12.0 * 0.1 - 1e-4
    close(result["height_range"], [float(points[:, 2].min()), float(points[:, 2].max())], 1e-4)
    assert result["mesh"]["vertices"] == 41 * 41 and result["mesh"]["faces"] == 40 * 40
    assert result["tile"] == [-2, 3] and result["spacing"] > 0


def test_the_detail_does_not_depend_on_the_resolution(bridge):
    bridge.ok("heightfield", name="Coarse", tile=[1, 1], **{**TILE, "resolution": 11})
    bridge.ok("heightfield", name="Fine", tile=[1, 1], **{**TILE, "resolution": 41})
    coarse, fine = world_points("Coarse"), world_points("Fine")
    for point in coarse:
        match = fine[numpy.isclose(fine[:, 0], point[0], atol=1e-6) & numpy.isclose(fine[:, 1], point[1], atol=1e-6)]
        assert len(match) == 1 and abs(match[0][2] - point[2]) < 1e-4


def test_a_zero_amplitude_noise_on_a_tilted_plane_gives_the_tilt_as_the_slope(bridge):
    for tilt in (12.0, 33.0):
        name = f"Ramp{int(tilt)}"
        plane = grid_plane(name, 6.0, 12)
        plane.rotation_euler = (math.radians(tilt), 0.0, 0.0)
        bpy.context.view_layer.update()
        before = world_points(name)
        result = bridge.ok("noise_displace", name=name, amplitude=0.0, seed=1, scale=2.0, attributes=["slope", "height"])
        assert numpy.max(numpy.abs(world_points(name) - before)) < 1e-6
        values = numpy.array([item.value for item in bpy.data.objects[name].data.attributes["slope"].data])
        assert numpy.max(numpy.abs(values - tilt)) < 1e-4
        close(result["attributes"]["slope"], [tilt, tilt], 1e-4)
        heights = numpy.array([item.value for item in bpy.data.objects[name].data.attributes["height"].data])
        assert numpy.max(numpy.abs(heights - before[:, 2])) < 1e-5
    flat = bridge.ok("heightfield", name="Flat", height=0.0, size=[10.0, 10.0], resolution=9, attributes=["slope", "height", "curvature"])
    assert flat["attributes"]["slope"] == [0.0, 0.0] and flat["attributes"]["curvature"] == [0.0, 0.0]


def test_slope_height_and_curvature_are_named_float_attributes_of_the_tile(bridge):
    bridge.ok("heightfield", name="Rough", attributes=["slope", "height", "curvature"], **TILE)
    mesh = bpy.data.objects["Rough"].data
    for name in ("slope", "height", "curvature"):
        assert mesh.attributes[name].data_type == "FLOAT" and mesh.attributes[name].domain == "POINT"
    points = world_points("Rough")
    slope, height, curvature = (numpy.array([item.value for item in mesh.attributes[name].data]) for name in ("slope", "height", "curvature"))
    assert numpy.max(numpy.abs(height - points[:, 2])) < 1e-4
    assert slope.min() >= 0.0 and slope.max() > 20.0 and slope.max() < 90.0
    assert curvature.min() < 0 < curvature.max()
    bridge.ok("add_primitive", type="ico_sphere", name="Ball", radius=2.0, subdivisions=4)
    bridge.ok("noise_displace", name="Ball", amplitude=0.0, seed=1, scale=2.0, attributes=["curvature"])
    ball = numpy.array([item.value for item in bpy.data.objects["Ball"].data.attributes["curvature"].data])
    assert abs(numpy.median(ball) - 0.5) < 0.05


def test_the_skirt_closes_the_tile_into_a_manifold_solid(bridge):
    bridge.ok("heightfield", name="Open", resolution=17, size=[20.0, 20.0], height=4.0, scale=15.0, octaves=3)
    open_topology, _ = mesh_topology(bpy.data.objects["Open"].data, 1e-6)
    assert open_topology["boundaryEdges"] == 64
    result = bridge.ok("heightfield", name="Solid", resolution=17, size=[20.0, 20.0], height=4.0, scale=15.0, octaves=3, skirt=True, skirt_depth=3.0, mode="ridged", ridge_offset=0.8, base_height=2.0, tile=[2, -1])
    topology, shells = mesh_topology(bpy.data.objects["Solid"].data, 1e-6)
    assert all(value == 0 for key, value in topology.items() if key != "looseParts"), topology
    assert topology["looseParts"] == 1
    assert shells == {"count": 1, "closed": 1, "inverted": 0}
    points = world_points("Solid")
    assert numpy.isclose(points[:, 2].min(), 2.0 + 4.0 * (0.8 - 1.0) - 3.0)
    assert result["mesh"]["vertices"] == 17 * 17 + 64


def test_uvs_cover_the_tile_in_world_units_and_continue_across_tiles(bridge):
    for tile in ([0, 0], [1, 0], [1, 1]):
        bridge.ok("heightfield", name=f"U{tile[0]}{tile[1]}", tile=tile, size=[20.0, 10.0], resolution=11, height=0.0)
    for name, tile in (("U00", (0, 0)), ("U10", (1, 0)), ("U11", (1, 1))):
        uvs = tile_uvs(name)
        points = world_points(name)
        mesh = bpy.data.objects[name].data
        corners = numpy.array([loop.vertex_index for loop in mesh.loops])
        expected = numpy.column_stack([points[corners, 0] / 20.0, points[corners, 1] / 10.0])
        assert numpy.max(numpy.abs(uvs - expected)) < 1e-6
        assert numpy.isclose(uvs[:, 0].min(), tile[0]) and numpy.isclose(uvs[:, 0].max(), tile[0] + 1)
    bridge.ok("heightfield", name="Ridge", size=[20.0, 20.0], resolution=21, height=6.0, scale=14.0, octaves=3, skirt=True)
    mesh = bpy.data.objects["Ridge"].data
    uvs = tile_uvs("Ridge")
    top_loops = uvs[: 4 * 400]
    assert numpy.isclose(top_loops[:, 0].min(), 0.0) and numpy.isclose(top_loops[:, 0].max(), 1.0)
    assert numpy.isclose(top_loops[:, 1].min(), 0.0) and numpy.isclose(top_loops[:, 1].max(), 1.0)
    bottom = uvs[-len(mesh.polygons[len(mesh.polygons) - 1].loop_indices):]
    assert bottom[:, 0].min() > 1.0
    walls = uvs[4 * 400 : -len(bottom)]
    rim_top = {tuple(numpy.round(uv, 9)) for uv in top_loops}
    assert sum(tuple(numpy.round(uv, 9)) in rim_top for uv in walls) >= 2 * 80


def test_a_stretch_free_uv_matches_the_world_size_of_the_faces(bridge):
    bridge.ok("heightfield", name="Square", size=[40.0, 40.0], resolution=9, height=0.0)
    mesh = bpy.data.objects["Square"].data
    uvs = tile_uvs("Square")
    points = world_points("Square")
    for polygon in mesh.polygons:
        loops = list(polygon.loop_indices)
        uv_edge = numpy.linalg.norm(uvs[loops[1]] - uvs[loops[0]])
        world_edge = numpy.linalg.norm(points[mesh.loops[loops[1]].vertex_index] - points[mesh.loops[loops[0]].vertex_index])
        assert abs(uv_edge * 40.0 - world_edge) < 1e-6


def test_heightfield_refuses_bad_arguments(bridge):
    bridge.ok("heightfield", name="Taken", height=1.0)
    for bad in ({"name": "Taken"}, {"resolution": 1}, {"resolution": 5000}, {"size": [0.0, 10.0]}, {"size": [10.0]}, {"tile": [0]}, {"tile": [0.5, 0]}, {"height": -1.0}, {"attributes": ["colour"]}, {"octaves": 13}, {"basis": "simplex"}, {"skirt_depth": 0.0}):
        bridge.refuse("heightfield", "bad_args", **{"name": "Other", "height": 1.0, **bad})
    bridge.refuse("heightfield", "bad_args", name="NoHeight")


run(globals())
