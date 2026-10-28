import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "judge"))

from harness import close, run

import bpy
import numpy
from drainage import drainage
from erode_helpers import TILE, attribute_values, interior_max_slope, make_tile, surface_heights
from judge_shells import mesh_topology

from blendworks_bridge.erosion_droplets import Droplets

RES = TILE["resolution"]
SPACING = TILE["size"][0] / (RES - 1)
CELL = SPACING * SPACING
DROPLETS = {"inertia": 0.0, "capacity": 4.0, "min_capacity": 0.01, "erode_rate": 0.3, "deposit_rate": 0.3, "evaporation": 0.0, "gravity": 0.0, "radius": 3.0, "max_lifetime": 60, "step": 1.0}


def two_slope_ramp(rows=41, columns=70):
    along = numpy.arange(columns, dtype=float)
    profile = numpy.where(along <= 30.0, 30.0 - along, -0.05 * (along - 30.0))
    return numpy.tile(profile, (rows, 1))


def free_interior(heights):
    free = numpy.ones(heights.shape)
    free[0, :] = free[-1, :] = free[:, 0] = free[:, -1] = 0.0
    return free


def test_thermal_erosion_keeps_the_sum_of_heights(bridge):
    make_tile(bridge, "T")
    before = surface_heights("T", RES)
    result = bridge.ok("erode", name="T", mode="thermal", talus_angle=30.0, iterations=300)
    after = surface_heights("T", RES)
    assert abs(before.sum() - after.sum()) < 1e-6 * before.sum()
    assert numpy.abs(after - before).max() > 0.5
    assert result["carried_off_volume"] == 0.0
    assert abs(result["eroded_volume"] - result["deposited_volume"]) < 1e-5 * result["eroded_volume"]


def test_thermal_erosion_to_convergence_leaves_no_slope_past_the_talus_angle(bridge):
    make_tile(bridge, "T")
    assert interior_max_slope(surface_heights("T", RES), SPACING) > 50.0
    result = bridge.ok("erode", name="T", mode="thermal", talus_angle=30.0, iterations=20000)
    assert result["thermal"]["settled"]
    steepest = interior_max_slope(surface_heights("T", RES), SPACING)
    assert 29.0 < steepest <= 30.5
    close(result["max_slope"], steepest, 0.01)


def test_hydraulic_erosion_balances_eroded_deposited_and_carried_off(bridge):
    make_tile(bridge, "T")
    before = surface_heights("T", RES)
    result = bridge.ok("erode", name="T", mode="hydraulic", droplets=3000, seed=2)
    after = surface_heights("T", RES)
    assert result["eroded_volume"] > 50.0 and result["deposited_volume"] > 10.0 and result["carried_off_volume"] > 1.0
    assert abs(result["eroded_volume"] - result["deposited_volume"] - result["carried_off_volume"]) < 1e-6 * result["eroded_volume"]
    assert abs((before - after).sum() * CELL - result["carried_off_volume"]) < 1e-3 * result["eroded_volume"]


def test_a_droplet_first_step_erodes_the_capacity_fraction_worked_out_by_hand(bridge):
    heights = two_slope_ramp()
    before = heights.copy()
    settings = {**DROPLETS, "max_lifetime": 1, "step": 10.0}
    engine = Droplets(heights, free_interior(heights), (1.0, 1.0), settings)
    engine.run(numpy.array([[6.5, 20.0]]))
    change = heights - before
    expected = 0.3 * 4.0 * math.sin(math.atan(1.0)) * 100.0
    assert abs(-change[change < 0].sum() - expected) < 1e-9
    assert abs(change[change > 0].sum() - expected) < 1e-9
    assert engine.carried == 0.0
    assert numpy.flatnonzero((change < 0).any(axis=0)).max() <= 9 and numpy.flatnonzero((change > 0).any(axis=0)).min() >= 16


def test_a_droplet_on_a_two_slope_ramp_erodes_the_steep_part_and_deposits_on_the_flat_part(bridge):
    heights = two_slope_ramp()
    before = heights.copy()
    engine = Droplets(heights, free_interior(heights), (1.0, 1.0), DROPLETS)
    engine.run(numpy.array([[5.5, 20.0]]))
    change = heights - before
    columns = numpy.arange(heights.shape[1])
    assert change[:, columns <= 27].max() <= 1e-12 and change[:, columns <= 27].min() < -0.1
    assert change[:, columns >= 33].min() >= -1e-12 and change[:, columns >= 33].max() > 0.1
    assert abs(change.sum()) < 1e-9 and engine.carried == 0.0
    steep_capacity = 4.0 * math.sin(math.atan(1.0))
    flat_capacity = 4.0 * math.sin(math.atan(0.05))
    dropped_at_the_bend = steep_capacity - flat_capacity
    per_column = change.sum(axis=0)
    assert abs(per_column[29:44].sum() - dropped_at_the_bend) < 0.05 * dropped_at_the_bend
    assert abs(per_column[41] / per_column[37] - (1.0 - 0.3) ** 4) < 0.03


def test_hydraulic_erosion_integrates_the_drainage_into_a_branching_network(bridge):
    shape = {"seed": 11, "mode": "fbm", "size": [96.0, 96.0], "resolution": 97, "height": 18.0, "scale": 60.0, "octaves": 5, "hurst": 0.9, "warp": 15.0, "warp_octaves": 2}
    for name in ("Both", "Dry"):
        make_tile(bridge, name, **shape)
    before = drainage(surface_heights("Both", 97), 100)
    rain = {"droplets": 50000, "capacity": 3.0, "erode_rate": 0.02, "deposit_rate": 0.1, "inertia": 0.1, "evaporation": 0.015, "max_lifetime": 100}
    bridge.ok("erode", name="Both", mode="both", iterations=100, talus_angle=40.0, seed=1, **rain)
    bridge.ok("erode", name="Dry", mode="thermal", iterations=100, talus_angle=40.0)
    after = drainage(surface_heights("Both", 97), 100)
    thermal_only = drainage(surface_heights("Dry", 97), 100)
    assert before["sink_volume"] > 1000.0 and after["sink_volume"] < 0.02 * before["sink_volume"]
    assert after["confluences"] >= 1.25 * before["confluences"] and after["channel_share"] >= before["channel_share"]
    assert thermal_only["sink_volume"] > 0.9 * before["sink_volume"] and thermal_only["confluences"] <= 1.1 * before["confluences"]


def test_the_same_seed_gives_identical_heights_and_another_seed_differs(bridge):
    for name in ("A", "B", "C"):
        make_tile(bridge, name)
    bridge.ok("erode", name="A", droplets=1500, iterations=30, seed=7)
    bridge.ok("erode", name="B", droplets=1500, iterations=30, seed=7)
    bridge.ok("erode", name="C", droplets=1500, iterations=30, seed=8)
    a, b, c = (surface_heights(name, RES) for name in "ABC")
    assert numpy.array_equal(a, b)
    assert numpy.abs(a - c).max() > 1e-3


def test_the_eroded_volume_of_a_fixed_terrain_survives_halving_the_grid_spacing(bridge):
    volumes = {}
    for resolution in (33, 65):
        make_tile(bridge, f"R{resolution}", resolution=resolution)
        volumes[resolution] = bridge.ok("erode", name=f"R{resolution}", mode="hydraulic", droplets=4000, seed=3)
    coarse, fine = volumes[33]["eroded_volume"], volumes[65]["eroded_volume"]
    assert coarse > 100.0
    assert abs(coarse - fine) < 0.10 * coarse
    assert abs(volumes[33]["deposited_volume"] - volumes[65]["deposited_volume"]) < 0.10 * coarse
    for resolution in (33, 65):
        make_tile(bridge, f"S{resolution}", resolution=resolution)
        volumes[resolution] = bridge.ok("erode", name=f"S{resolution}", mode="thermal", talus_angle=30.0, iterations=400)
    assert abs(volumes[33]["eroded_volume"] - volumes[65]["eroded_volume"]) < 0.12 * volumes[33]["eroded_volume"]


def test_a_single_tile_keeps_its_edge_heights(bridge):
    make_tile(bridge, "T", skirt=True, skirt_depth=10.0)
    before = surface_heights("T", RES)
    bridge.ok("erode", name="T", droplets=3000, iterations=100)
    after = surface_heights("T", RES)
    for edge in (lambda a: a[0], lambda a: a[-1], lambda a: a[:, 0], lambda a: a[:, -1]):
        assert numpy.array_equal(edge(before), edge(after))
    assert numpy.abs(after - before).max() > 0.5
    topology, shells = mesh_topology(bpy.data.objects["T"].data, 1e-6)
    assert all(value == 0 for key, value in topology.items() if key != "looseParts") and shells["closed"] == 1


def test_tiles_eroded_together_share_their_edge_heights_and_change_there(bridge):
    for tile in ((0, 0), (1, 0), (0, 1), (1, 1)):
        make_tile(bridge, f"T{tile[0]}{tile[1]}", tile=tile)
    before = {name: surface_heights(name, RES) for name in ("T00", "T10", "T01", "T11")}
    result = bridge.ok("erode", name="T00", names=["T10", "T01", "T11"], droplets=6000, iterations=60, seed=4)
    after = {name: surface_heights(name, RES) for name in before}
    assert result["grid"] == [2 * (RES - 1) + 1] * 2 and result["edge_change"] == 0.0
    assert numpy.abs(after["T00"][:, -1] - after["T10"][:, 0]).max() < 1e-9
    assert numpy.abs(after["T00"][-1, :] - after["T01"][0, :]).max() < 1e-9
    assert numpy.abs(after["T10"][-1, :] - after["T11"][0, :]).max() < 1e-9
    assert numpy.abs(after["T01"][:, -1] - after["T11"][:, 0]).max() < 1e-9
    assert numpy.abs(after["T00"][:, -1] - before["T00"][:, -1]).max() > 0.05
    assert numpy.array_equal(after["T00"][0], before["T00"][0]) and numpy.array_equal(after["T11"][:, -1], before["T11"][:, -1])


def test_the_erosion_and_deposition_attributes_add_up_to_the_reported_volumes(bridge):
    make_tile(bridge, "T", skirt=True, skirt_depth=10.0)
    result = bridge.ok("erode", name="T", droplets=3000, iterations=100, seed=1)
    erosion, deposition = attribute_values("T", "erosion"), attribute_values("T", "deposition")
    assert len(erosion) == len(bpy.data.objects["T"].data.vertices)
    assert erosion.min() >= 0 and deposition.min() >= 0 and erosion.max() > 0.05 and deposition.max() > 0.05
    assert abs(erosion.sum() * CELL - result["eroded_volume"]) < 1e-4 * result["eroded_volume"]
    assert abs(deposition.sum() * CELL - result["deposited_volume"]) < 1e-4 * result["deposited_volume"]
    assert not (erosion * deposition).any()
    close(result["eroded_volume"] - result["deposited_volume"], result["carried_off_volume"], 1e-4 * result["eroded_volume"])


def test_slope_height_and_curvature_attributes_follow_the_eroded_surface(bridge):
    make_tile(bridge, "T", attributes=["slope", "height", "curvature"])
    slope = attribute_values("T", "slope").copy()
    bridge.ok("erode", name="T", droplets=2000, iterations=50)
    assert numpy.abs(attribute_values("T", "slope") - slope).max() > 1.0
    assert numpy.abs(attribute_values("T", "height") - surface_heights("T", RES).ravel()).max() < 1e-4
    plain = make_tile(bridge, "P")
    bridge.ok("erode", name="P", droplets=100, iterations=2)
    assert "slope" not in bpy.data.objects["P"].data.attributes and "erosion" in bpy.data.objects["P"].data.attributes
    assert plain["mesh"]["vertices"] == RES * RES


def test_a_mask_protects_vertices_and_a_moved_scaled_tile_erodes_in_world_metres(bridge):
    make_tile(bridge, "T", tile=[3, -2])
    obj = bpy.data.objects["T"]
    group = obj.vertex_groups.new(name="open")
    group.add([row * RES + column for row in range(RES) for column in range(RES // 2, RES)], 1.0, "REPLACE")
    before = surface_heights("T", RES)
    bridge.ok("erode", name="T", mode="thermal", talus_angle=25.0, iterations=200, mask="open")
    change = numpy.abs(surface_heights("T", RES) - before)
    assert change[:, : RES // 2 - 1].max() == 0.0 and change[:, RES // 2 + 1 :].max() > 0.1
    bridge.ok("transform", name="T", scale=[1.0, 1.0, 2.0])
    scaled = surface_heights("T", RES)
    bridge.ok("erode", name="T", mode="thermal", talus_angle=25.0, iterations=50)
    assert numpy.abs(surface_heights("T", RES) - scaled).max() > 0.1
    bridge.refuse("erode", "not_found", name="T", mask="nothing")


def test_erode_refuses_meshes_that_are_not_heightfield_grids(bridge):
    bridge.ok("add_primitive", type="cube", name="Cube")
    bridge.ok("add_primitive", type="ico_sphere", name="Ball", radius=2.0)
    make_tile(bridge, "Good")
    make_tile(bridge, "Rotated", tile=[1, 0])
    bridge.ok("transform", name="Rotated", rotation=[0.0, 0.0, 30.0])
    make_tile(bridge, "Other", tile=[0, 1], resolution=17)
    make_tile(bridge, "Far", tile=[5, 5])
    for name in ("Cube", "Ball"):
        assert "heightfield" in bridge.refuse("erode", "bad_args", name=name)
    assert "rotated or flipped" in bridge.refuse("erode", "bad_args", name="Rotated")
    make_tile(bridge, "Flipped", tile=[2, 0])
    bridge.ok("transform", name="Flipped", scale=[-1.0, 1.0, 1.0])
    assert "rotated or flipped" in bridge.refuse("erode", "bad_args", name="Flipped")
    make_tile(bridge, "Bent", tile=[0, 2])
    mesh = bpy.data.objects["Bent"].data
    mesh.vertices[40].co.x += 1.0
    assert "regular grid" in bridge.refuse("erode", "bad_args", name="Bent")
    assert "resolution" in bridge.refuse("erode", "bad_args", name="Good", names=["Other"])
    assert "rectangle" in bridge.refuse("erode", "bad_args", name="Good", names=["Far"])
    bridge.refuse("erode", "bad_args", name="Good", names=["Other", "Other"])
    for bad in ({"mode": "wind"}, {"iterations": 0}, {"talus_angle": 90.0}, {"droplets": 0}, {"rate": 0.0}, {"inertia": 1.0}):
        bridge.refuse("erode", "bad_args", name="Good", **bad)
    bridge.refuse("erode", "not_found", name="Missing")


run(globals())
