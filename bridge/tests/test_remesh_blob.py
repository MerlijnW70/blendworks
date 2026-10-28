import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run

import bpy
import numpy
from rock_helpers import report, mesh_of
from blendworks_bridge.commands.remesh import shell_count


def cube_with_hole(bridge):
    bridge.ok("add_primitive", type="cube", name="Plate", size=1.0)
    bridge.ok("add_primitive", type="cylinder", name="Drill", radius=0.2, depth=2.0, segments=64)
    bridge.ok("boolean", name="Plate", cutter="Drill", operation="difference", cutter_action="delete")
    return report("Plate")["volume"]


def test_remesh_of_a_cube_with_a_hole_is_one_closed_shell_of_the_same_volume(bridge):
    expected = cube_with_hole(bridge)
    result = bridge.ok("remesh", name="Plate", voxel_size=0.02)
    state = report("Plate")
    assert result["manifold"] and state["closed"] and result["shells"] == 1 and shell_count(mesh_of("Plate").data) == 1
    assert abs(state["volume"] - expected) / expected < 0.02
    assert len(mesh_of("Plate").modifiers) == 0 and result["modifiers"] == 0
    assert numpy.linalg.norm(numpy.array([v.co[:2] for v in mesh_of("Plate").data.vertices]), axis=1).min() < 0.21


def test_remesh_smooth_shading_and_refusals(bridge):
    bridge.ok("add_primitive", type="cube", name="Block", size=1.0)
    bridge.ok("remesh", name="Block", voxel_size=0.1, smooth_shading=True)
    assert all(polygon.use_smooth for polygon in mesh_of("Block").data.polygons)
    message = bridge.refuse("remesh", "bad_args", name="Block", voxel_size=0.0002)
    assert "vertices" in message and len(mesh_of("Block").modifiers) == 0
    bridge.refuse("remesh", "bad_args", name="Block", voxel_size=0.0)
    bridge.refuse("remesh", "not_found", name="Ghost", voxel_size=0.1)
    bridge.ok("transform", name="Block", scale=[1.0, 2.0, 1.0])
    assert "non-uniform" in bridge.refuse("remesh", "bad_args", name="Block", voxel_size=0.1)


def test_remesh_voxel_size_is_in_metres_whatever_the_scale(bridge):
    bridge.ok("add_primitive", type="cube", name="Block", size=1.0)
    bridge.ok("transform", name="Block", scale=[4.0, 4.0, 4.0])
    result = bridge.ok("remesh", name="Block", voxel_size=0.4)
    assert 400 < result["mesh"]["faces"] < 900
    assert abs(report("Block")["volume"] - 1.0) / 1.0 < 0.05


def test_overlapping_blobs_give_one_shell_and_far_apart_ones_give_two(bridge):
    near = bridge.ok("blob", name="Near", points=[{"position": [0, 0, 0], "radius": 0.5}, {"position": [0.7, 0, 0], "radius": 0.4}], voxel_size=0.03)
    far = bridge.ok("blob", name="Far", points=[{"position": [0, 0, 0], "radius": 0.5}, {"position": [3.0, 0, 0], "radius": 0.4}], voxel_size=0.03)
    assert near["shells"] == 1 and far["shells"] == 2
    for name in ("Near", "Far"):
        assert report(name)["closed"] and len(mesh_of(name).modifiers) == 0


def test_an_isolated_blob_sphere_keeps_its_radius_and_blending_adds_volume(bridge):
    single = bridge.ok("blob", name="One", points=[{"position": [0, 0, 0], "radius": 0.5}], voxel_size=0.02, threshold=0.5)
    sphere = 4.0 / 3.0 * numpy.pi * 0.5**3
    close(single["volume"] / sphere, 1.0, 0.03)
    norms = numpy.linalg.norm(numpy.array([tuple(v.co) for v in mesh_of("One").data.vertices]), axis=1)
    close(float(norms.mean()), 0.5, 0.01)
    union = bridge.ok("blob", name="Two", points=[{"position": [0, 0, 0], "radius": 0.5}, {"position": [0.8, 0, 0], "radius": 0.5}], voxel_size=0.03)
    assert union["volume"] > 2 * sphere * 0.97 - 0.0


def test_blob_refuses_what_it_cannot_build(bridge):
    point = {"position": [0, 0, 0], "radius": 0.5}
    bridge.refuse("blob", "bad_args", name="Tiny", points=[point], voxel_size=0.0002)
    bridge.refuse("blob", "bad_args", name="Thin", points=[{"position": [0, 0, 0], "radius": 0.05}], voxel_size=0.04)
    bridge.refuse("blob", "bad_args", name="Empty", points=[], voxel_size=0.05)
    bridge.ok("blob", name="Taken", points=[point], voxel_size=0.05)
    bridge.refuse("blob", "bad_args", name="Taken", points=[point], voxel_size=0.05)


run(globals())
