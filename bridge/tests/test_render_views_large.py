import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from view_helpers import look_down, peak_memory_gib, quad_grid, render, white_world

CELLS = 1582
TRIANGLES = 2 * CELLS * CELLS
MEMORY_BUDGET_GIB = 4.0
SIZE = 160
DENSE_LIGHTEST_SHARE = 0.9
SPARSE_DARKEST_SHARE = 0.9


def big_terrain(bridge, triangles):
    terrain = quad_grid("Terrain", CELLS, 10.0, wave=0.05, triangles=triangles)
    assert len(terrain.data.polygons) * (1 if triangles else 2) >= 5_000_000
    white_world(bridge)
    camera = look_down("Top", 12.0, SIZE)
    bridge.ok("add_light", type="sun", name="Sun", rotation=[30.0, 0.0, 20.0], energy=3.0)
    return camera


def wireframe_within_budget(bridge, triangles):
    camera = big_terrain(bridge, triangles)
    options = dict(width=SIZE, height=SIZE, samples=16, noise_threshold=0.0)
    far, result = render(bridge, "far", shading="wireframe", **options)
    far_clay, _ = render(bridge, "far_clay", shading="clay", **options)
    assert result["wire_polygon_objects"] == 1 and result["wire_edges"] > 2_000_000
    assert float(far.mean()) > DENSE_LIGHTEST_SHARE * float(far_clay.mean()), (float(far.mean()), float(far_clay.mean()))
    camera.location = (0.0, 0.0, 0.15)
    near, _ = render(bridge, "near", shading="wireframe", **options)
    near_clay, _ = render(bridge, "near_clay", shading="clay", **options)
    assert float(near.mean()) < SPARSE_DARKEST_SHARE * float(near_clay.mean()), (float(near.mean()), float(near_clay.mean()))
    preview = bridge.ok("render_preview", camera="Top", shading="wireframe", resolution=128, samples=1, device="cpu")
    assert preview["wire_edges"] == result["wire_edges"] and len(preview["images"]) == 1
    assert peak_memory_gib() < MEMORY_BUDGET_GIB, peak_memory_gib()


def test_a_five_million_triangle_quad_mesh_renders_as_a_wireframe_within_the_memory_budget(bridge):
    wireframe_within_budget(bridge, False)


def test_a_five_million_triangle_triangle_mesh_renders_as_a_wireframe_within_the_memory_budget(bridge):
    wireframe_within_budget(bridge, True)


run(globals())
