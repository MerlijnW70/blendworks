import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run

import bpy
import numpy
from rock_helpers import extents, mesh_of, report, roughness_p90, world_and_faces


def test_abrade_lowers_the_normal_deviation_and_keeps_the_axes_in_its_first_phase(bridge):
    bridge.ok("add_primitive", type="ico_sphere", name="Rock", radius=0.5, subdivisions=5)
    bridge.ok("transform", name="Rock", scale=[1.4, 1.0, 0.8])
    bridge.ok("apply_transform", name="Rock", scale=True)
    bridge.ok("noise_displace", name="Rock", amplitude=0.015, seed=3, scale=0.4, octaves=3, hurst=0.4)
    before_p90, before_box = roughness_p90("Rock"), extents("Rock")
    result = bridge.ok("abrade", name="Rock", amount=0.3, edge_length=0.03, seed=1)
    assert result["stopped"] in ("amount", "iterations")
    assert roughness_p90("Rock") < 0.5 * before_p90
    change = numpy.abs(extents("Rock") / before_box - 1.0)
    assert change.max() < 0.05, change
    assert report("Rock")["closed"]


def test_abrade_rounds_edges_while_large_faces_stay_and_stays_closed(bridge):
    bridge.ok("add_primitive", type="cube", name="Block", size=1.0)
    start = report("Block")["volume"]
    result = bridge.ok("abrade", name="Block", amount=1.0)
    world, _ = world_and_faces("Block")
    corner = numpy.abs(world).min(axis=0)
    assert report("Block")["closed"]
    assert numpy.abs(world).max(axis=0).tolist() == [0.5, 0.5, 0.5] or numpy.allclose(numpy.abs(world).max(axis=0), 0.5, atol=1e-5)
    assert numpy.max(numpy.linalg.norm(world, axis=1)) < 0.5 * 3 ** 0.5 - 0.03
    face_centre = world[(numpy.abs(world[:, 0] - 0.5) < 1e-6) & (numpy.abs(world[:, 1]) < 0.1) & (numpy.abs(world[:, 2]) < 0.1)]
    assert len(face_centre) > 4
    loss = 1.0 - report("Block")["volume"] / start
    close(loss, result["volume_loss"], 1e-3)
    assert 0.0 < loss <= result["max_volume_loss"] + 1e-6


def test_abrade_never_removes_more_than_its_stated_share_of_the_volume(bridge):
    bridge.ok("add_primitive", type="cube", name="Block", size=1.0)
    start = report("Block")["volume"]
    result = bridge.ok("abrade", name="Block", amount=1.0, iterations=500)
    assert result["stopped"] in ("volume_limit", "amount")
    assert 1.0 - report("Block")["volume"] / start <= 0.1 + 1e-6


def test_abrade_reaches_a_target_convexity_on_a_dented_shape(bridge):
    bridge.ok("add_primitive", type="ico_sphere", name="Rock", radius=0.5, subdivisions=4)
    bridge.ok("noise_displace", name="Rock", amplitude=0.05, seed=2, scale=1.0, octaves=2, hurst=0.5)
    first = bridge.ok("abrade", name="Rock", amount=0.01, iterations=1, edge_length=0.2)
    result = bridge.ok("abrade", name="Rock", target_convexity=min(first["convexity"] + 0.01, 0.999), iterations=200, edge_length=0.2)
    assert result["stopped"] in ("convexity", "volume_limit")


def rim_stone(bridge):
    bridge.ok("add_primitive", type="ico_sphere", name="Stone", radius=0.5, subdivisions=4, location=[0.0, 0.0, 0.55])
    bridge.ok("transform", name="Stone", scale=[1.9, 1.4, 1.1])
    bridge.ok("apply_transform", name="Stone", scale=True)
    pieces = bridge.ok("fracture", name="Stone", pieces=2, seed=7, min_size=0.44)
    keep = max(zip(pieces["pieces"], pieces["volumes"]), key=lambda entry: entry[1])[0]
    bridge.ok("delete", names=[name for name in pieces["pieces"] if name != keep])
    bridge.ok("chip", name=keep, count=6, depth=0.57, seed=7)
    return keep


def folded_triangles(name):
    obj = mesh_of(name)
    mesh = obj.data
    mesh.calc_loop_triangles()
    count = len(mesh.vertices)
    flat = numpy.empty(count * 3)
    mesh.vertices.foreach_get("co", flat)
    points = flat.reshape(count, 3)
    corners = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", corners)
    triangles = corners.reshape(-1, 3)
    cross = numpy.cross(points[triangles[:, 1]] - points[triangles[:, 0]], points[triangles[:, 2]] - points[triangles[:, 0]])
    face = cross / numpy.maximum(numpy.linalg.norm(cross, axis=1), 1e-300)[:, None]
    summed = numpy.zeros_like(points)
    for corner in range(3):
        numpy.add.at(summed, triangles[:, corner], face)
    vertex = summed / numpy.maximum(numpy.linalg.norm(summed, axis=1), 1e-300)[:, None]
    opposed = numpy.einsum("ij,ikj->ik", face, vertex[triangles]).min(axis=1) < 0.0
    return int(opposed.sum()), len(triangles)


def test_abrade_leaves_no_frill_along_the_rim_of_a_cut_stone(bridge):
    name = rim_stone(bridge)
    world, faces = world_and_faces(name)
    planes = []
    for face in faces:
        corners = world[face]
        normal = numpy.cross(corners[1] - corners[0], corners[2] - corners[0])
        planes.append((normal / numpy.linalg.norm(normal), corners[0]))
    bridge.ok("abrade", name=name, amount=0.8, seed=7)
    after, _ = world_and_faces(name)
    outside = max(float(numpy.max((after - origin) @ normal)) for normal, origin in planes)
    assert outside < 1e-5, outside
    folded, total = folded_triangles(name)
    assert folded / total < 0.005, (folded, total)
    assert report(name)["closed"]


def test_abrade_refuses_open_meshes_and_both_goals(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet")
    bridge.refuse("abrade", "bad_args", name="Sheet")
    bridge.ok("add_primitive", type="cube", name="Block")
    bridge.refuse("abrade", "bad_args", name="Block", amount=0.5, target_convexity=0.9)
    bridge.refuse("abrade", "bad_args", name="Block", amount=1.5)


run(globals())
