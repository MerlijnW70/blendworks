import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from harness import run

import bpy
import numpy
from blendworks_bridge.limits_fluvial import MAX_FLUVIAL_SIDE

SMALL = {"size": 15.36, "cell": 120.0, "tiles": 2}


def test_a_small_range_builds_tiles_with_drainage_attributes(bridge):
    result = bridge.ok("fluvial_terrain", name="Range", path="range.npz", **SMALL)
    assert result["side"] == 129 and len(result["tiles"]) == 4
    assert result["measures"]["undrained_pits"] == 0
    for name in result["tiles"]:
        mesh = bpy.data.objects[name].data
        for attribute in ("height", "drainage_area", "channel", "strahler", "lake_depth", "erosion"):
            assert attribute in mesh.attributes, (name, attribute)
    saved = numpy.load(os.path.join(bridge.workspace, "range.npz"))
    assert saved["height"].shape == (129, 129) and float(saved["cell"]) == 120.0


def test_a_grid_past_the_limit_is_refused(bridge):
    message = bridge.refuse("fluvial_terrain", "bad_args", name="Huge", size=(MAX_FLUVIAL_SIDE + 2) * 0.03, cell=30.0)
    assert "fluvial_side" in message or str(MAX_FLUVIAL_SIDE) in message, message


def test_scatter_masks_liquids_lods_and_the_horizon_read_the_result(bridge):
    from scatter_helpers import locations

    result = bridge.ok("fluvial_terrain", name="Basin", lods=1, horizon=80_000.0, **SMALL)
    assert result["lods"] and result["horizon"]["name"] == "Basin_horizon"
    tile = result["tiles"][0]
    assert tile == "Basin_0_0_LOD0" and "Basin_0_0_LOD1" in bpy.data.objects
    bridge.ok("add_primitive", type="cube", size=10.0, name="Boulder")
    placed = bridge.ok("scatter", target=tile, source="Boulder", min_distance=60.0, seed=2, name="OnChannels",
                       density_mask=["attribute"], attribute="channel", attribute_range=[0.5, 0.5])
    assert placed["count"] > 5
    mesh = bpy.data.objects[tile].data
    channel = numpy.empty(len(mesh.vertices))
    mesh.attributes["channel"].data.foreach_get("value", channel)
    corners = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", corners)
    corners = corners.reshape(-1, 3) + numpy.array(bpy.data.objects[tile].location)
    for point in locations("OnChannels"):
        nearest = numpy.argsort(numpy.hypot(*(corners[:, :2] - point[:2]).T))[:4]
        assert channel[nearest].max() == 1.0, point
    river = result["rivers"][0]["points"]
    assert len(river) >= 2 and river[-1][2] <= river[0][2]
    bridge.ok("liquid_body", kind="river", ground=result["tiles"], path=river, width=12.0, depth=1.5, name="Trunk", carve=False)
    assert "Trunk" in bpy.data.objects

def world_vertices_and_normals(name):
    obj = bpy.data.objects[name]
    mesh = obj.data
    points = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    corners = numpy.empty(len(mesh.loops) * 3)
    mesh.corner_normals.foreach_get("vector", corners)
    loops = numpy.empty(len(mesh.loops), dtype=numpy.int64)
    mesh.loops.foreach_get("vertex_index", loops)
    normals = numpy.zeros((len(mesh.vertices), 3))
    normals[loops] = corners.reshape(-1, 3)
    return points.reshape(-1, 3) + numpy.array(obj.location), normals


def test_tiles_share_their_edge_normals_so_no_seam_shows(bridge):
    result = bridge.ok("fluvial_terrain", name="Seam", **SMALL)
    left, left_normals = world_vertices_and_normals("Seam_0_0")
    right, right_normals = world_vertices_and_normals("Seam_1_0")
    edge = left[:, 0].max()
    on_left = numpy.isclose(left[:, 0], edge)
    on_right = numpy.isclose(right[:, 0], edge)
    order_left = numpy.argsort(left[on_left, 1])
    order_right = numpy.argsort(right[on_right, 1])
    assert on_left.sum() == on_right.sum() > 10, (on_left.sum(), on_right.sum())
    assert numpy.allclose(left[on_left][order_left], right[on_right][order_right], atol=1e-3)
    assert numpy.allclose(left_normals[on_left][order_left], right_normals[on_right][order_right], atol=1e-3), numpy.abs(left_normals[on_left][order_left] - right_normals[on_right][order_right]).max()


run(globals())
