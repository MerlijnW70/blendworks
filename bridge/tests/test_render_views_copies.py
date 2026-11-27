import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run
from view_helpers import look_down, peak_memory_gib, render, white_world

COPIES = 600
MEMORY_BUDGET_GIB = 1.0


def test_linked_copies_stay_instances_in_a_wireframe_within_the_memory_budget(bridge):
    """600 linked copies of a 20 480 triangle rock are 12.3 million instanced triangles. Each copy evaluated on its own
    would take about 4 GiB; shared they take what the one rock takes."""
    bridge.ok("add_primitive", type="ico_sphere", name="Rock", radius=0.3, subdivisions=6)
    rock = bpy.data.objects["Rock"]
    side = int(COPIES ** 0.5) + 1
    for index in range(COPIES):
        copy = rock.copy()
        copy.location = ((index % side) - side / 2, (index // side) - side / 2, 0.0)
        copy.scale = (1.0, 1.0 + 0.5 * (index % 3), 1.0)
        bpy.context.scene.collection.objects.link(copy)
    triangles = len(rock.data.polygons) * (COPIES + 1)
    assert triangles > 12_000_000
    white_world(bridge)
    look_down("Top", 40.0, 128)
    _, result = render(bridge, "copies", shading="wireframe", width=128, height=128, samples=4, noise_threshold=0.0)
    assert result["wire_polygon_objects"] == COPIES + 1 and result["wire_edges_drawn"] == "polygon"
    assert all(obj.data == rock.data for obj in bpy.context.scene.objects if obj.type == "MESH")
    assert peak_memory_gib() < MEMORY_BUDGET_GIB, peak_memory_gib()


run(globals())
