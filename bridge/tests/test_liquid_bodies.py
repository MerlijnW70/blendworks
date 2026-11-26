import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
from mathutils import Vector

from harness import run
from liquid_helpers import attribute, dimple, mesh_points

from blendworks_bridge import liquid_spectrum

GRAVITY = 9.81


def sheet_heights(name, level):
    points = mesh_points(name)
    return points[: len(points) // 2, 2] - level


def ocean(bridge, name, wind, fetch, seed=0, cells=256):
    return bridge.ok("liquid_body", kind="ocean", name=name, wind={"speed": wind, "direction": 90.0}, fetch=fetch, size=400.0, cells=cells, horizon=False, centre=[0.0, 0.0], seed=seed, wet_shore=False)


def test_ocean_wave_height_follows_the_wind_by_the_spectrum(bridge):
    for wind in (6.0, 9.0):
        result = ocean(bridge, f"Open{int(wind)}", wind, 1_000_000.0)
        u = 1.026 * wind
        wanted = 0.21 * u * u / GRAVITY
        measured = 4.0 * sheet_heights(f"Open{int(wind)}", 0.0).std()
        assert result["waves"]["regime"] == "fully_developed"
        assert abs(measured - wanted) < 0.1 * wanted, (wind, measured, wanted)
    result = ocean(bridge, "Bay", 10.0, 20_000.0)
    chi = GRAVITY * 20_000.0 / 100.0
    wanted = 1.6e-3 * math.sqrt(chi) * 100.0 / GRAVITY
    measured = 4.0 * sheet_heights("Bay", 0.0).std()
    assert result["waves"]["regime"] == "fetch_limited"
    assert abs(measured - wanted) < 0.1 * wanted, (measured, wanted)


def test_whitecaps_cover_the_share_of_the_sea_the_wind_gives(bridge):
    ocean(bridge, "Storm", 14.0, 1_000_000.0, cells=128)
    foam = attribute("Storm", "lq_foam")
    share = float((foam[: len(foam) // 2] > 0.5).mean())
    wanted = liquid_spectrum.whitecap_fraction(14.0)
    assert 0.5 * wanted < share < 2.0 * wanted, (share, wanted)
    ocean(bridge, "Calm", 4.0, 1_000_000.0, cells=128)
    assert float((attribute("Calm", "lq_foam") > 0.5).mean()) < share


def test_the_same_seed_repeats_and_another_seed_does_not(bridge):
    ocean(bridge, "A", 8.0, 50_000.0, seed=3, cells=64)
    ocean(bridge, "B", 8.0, 50_000.0, seed=3, cells=64)
    ocean(bridge, "C", 8.0, 50_000.0, seed=4, cells=64)
    a, b, c = mesh_points("A"), mesh_points("B"), mesh_points("C")
    assert np.array_equal(a, b)
    assert not np.allclose(a, c)
    image_a = np.array(bpy.data.images["A_ripples"].pixels[:])
    image_b = np.array(bpy.data.images["B_ripples"].pixels[:])
    assert np.array_equal(image_a, image_b)


def test_a_puddle_stays_in_its_hollow_and_its_area_matches(bridge):
    radius, curvature, depth = 0.3, 1.0, 0.02
    dimple("Hollow", 1.0, 200, radius, curvature)
    result = bridge.ok("liquid_body", kind="puddle", ground=["Hollow"], point=[0.05, 0.0, 0.0], level=-depth, radius=0.45, name="Puddle", overlap=0.0)
    wet_radius = math.sqrt(radius * radius - 2.0 * curvature * depth)
    wanted = math.pi * wet_radius * wet_radius
    assert abs(result["area"] - wanted) < 0.015 * wanted, (result["area"], wanted)
    points = mesh_points("Puddle")
    top = points[: len(points) // 2]
    assert np.all(np.hypot(top[:, 0], top[:, 1]) <= wet_radius + 2.0 * result["cell"])
    assert np.allclose(top[:, 2], -depth)
    wanted_volume = math.pi * (radius * radius - 2.0 * curvature * depth) ** 2 / (4.0 * curvature)
    assert abs(result["volume"] - wanted_volume) < 0.03 * wanted_volume, (result["volume"], wanted_volume)
    message = bridge.refuse("liquid_body", "bad_args", kind="puddle", ground=["Hollow"], point=[0.0, 0.0, 0.0], level=0.01, radius=0.45, name="Flood")
    assert "spills" in message


def slope_variances(name, direction):
    image = bpy.data.images[f"{name}_ripples"]
    n = image.size[0]
    heights = np.array(image.pixels[:]).reshape(n, n, 4)[:, :, 0]
    gy, gx = np.gradient(heights)
    heading = math.radians(direction)
    along = gx * math.sin(heading) + gy * math.cos(heading)
    across = gx * math.cos(heading) - gy * math.sin(heading)
    return float((along * along).mean()), float((across * across).mean())


def test_lake_ripples_follow_the_wind_of_the_weather(bridge):
    dimple("Basin", 80.0, 160, 30.0, 300.0)
    bridge.ok("add_camera", name="Eye", location=[0.0, -35.0, 2.0], target=[0.0, 0.0, 0.0])
    weather = bridge.ok("weather", preset="broken", form="sheet", haze=False, exposure="keep")
    lowest = min(weather["layers"], key=lambda layer: layer["base"])
    lake = bridge.ok("liquid_body", kind="lake", ground=["Basin"], point=[0.0, 0.0, 0.0], name="Lake")
    assert lake["wind"]["direction"] == lowest["wind_direction"] and "weather" in lake["wind"]["source"]
    assert lake["wind"]["speed"] > 5.0
    along, across = slope_variances("Lake", lake["wind"]["direction"])
    assert along > 1.3 * across, (along, across)
    turned = bridge.ok("liquid_body", kind="lake", ground=["Basin"], point=[0.0, 0.0, 0.0], name="Turned", wind={"direction": 0.0})
    assert turned["wind"]["direction"] == 0.0 and turned["wind"]["speed"] == lake["wind"]["speed"]
    along, across = slope_variances("Turned", 0.0)
    assert along > 1.3 * across, (along, across)
    still = bridge.ok("liquid_body", kind="lake", ground=["Basin"], point=[0.0, 0.0, 0.0], name="Still", wind={"speed": 0.0})
    assert still["waves"]["hs"] == 0.0 and bpy.data.images.get("Still_ripples") is None


def valley(name, length=120.0, cells=120):
    """A valley falling towards -y at 5 %, winding as x = 6 sin(y / 15), with sides of slope 0.35."""
    import bmesh

    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=cells, y_segments=cells, size=length / 2.0)
    for vertex in bm.verts:
        floor = 6.0 * math.sin(vertex.co.y / 15.0)
        vertex.co.z = 0.05 * vertex.co.y + 0.35 * abs(vertex.co.x - floor)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)


def test_a_river_follows_the_lowest_line_and_flows_downhill(bridge):
    valley("Valley")
    result = bridge.ok("liquid_body", kind="river", ground=["Valley"], point=[8.0, 50.0, 0.0], width=3.0, depth=0.5, name="River", carve=False)
    path = np.array(result["path"])
    floor = 6.0 * np.sin(path[:, 1] / 15.0)
    assert np.abs(path[5:, 0] - floor[5:]).max() < 2.5 * result["cell"], np.abs(path[:, 0] - floor).max()
    assert path[-1, 1] < -40.0
    profile = np.array(result["profile"])
    assert np.all(np.diff(profile[:, 1]) <= 1e-9) and profile[0, 1] - profile[-1, 1] > 3.0
    points = mesh_points("River")
    flow = np.zeros(len(points) * 3)
    bpy.data.objects["River"].data.attributes["lq_flow"].data.foreach_get("vector", flow)
    flow = flow.reshape(-1, 3)[: len(points) // 2]
    moving = np.linalg.norm(flow, axis=1) > 0
    assert moving.mean() > 0.99 and np.mean(flow[moving, 1] < 0.0) > 0.95
    assert 0.3 < result["mean_speed"] < 5.0
    bridge.ok("delete", names=["River"])
    carved = bridge.ok("liquid_body", kind="river", ground=["Valley"], point=[8.0, 50.0, 0.0], width=3.0, depth=0.5, name="Carved")
    assert carved["carved_vertices"] > 50



def valley_into_pond(name, length=120.0, cells=160):
    """The winding valley of valley(), ending at y = -40 in a round hollow centred at (0, -48)."""
    import bmesh

    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=cells, y_segments=cells, size=length / 2.0)
    for vertex in bm.verts:
        x, y = vertex.co.x, vertex.co.y
        floor = 6.0 * math.sin(y / 15.0)
        down = 0.05 * (y + 40.0) if y > -40.0 else -0.15 * (y + 40.0)
        vertex.co.z = min(down - 2.0 + 0.35 * abs(x - floor), -4.0 + (x * x + (y + 48.0) ** 2) / 60.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)


def top_hits(name, points):
    """World z of the named liquid's top surface straight above each point, NaN where it has none."""
    from blendworks_bridge import liquid_world

    water = liquid_world.Water([bpy.data.objects[name]])
    found = np.full(len(points), np.nan)
    for row, (x, y) in enumerate(points.tolist()):
        hit = water.tree.ray_cast(Vector((x, y, -100.0)), Vector((0.0, 0.0, 1.0)))
        if hit[0] is not None:
            found[row] = hit[0].z
    return found


def test_a_river_runs_on_without_a_gap_into_the_lake_and_tucks_under_its_surface(bridge):
    """Along the river's centreline there is water all the way into the lake (sampled every 2 cm over the last 10 m), and
    where the river reaches under the lake's edge its surface stays a few millimetres below the lake's, so the two never
    coincide (no z-fighting) and no bed shows between them."""
    valley_into_pond("Land")
    pond = bridge.ok("liquid_body", kind="lake", ground=["Land"], point=[0.0, -48.0, 0.0], depth=1.5, name="Pond", wet_shore=False, wind={"speed": 8.0, "direction": 0.0})
    assert pond["waves"]["hs"] > 0.01, pond["waves"]
    flow = bridge.ok("liquid_body", kind="river", ground=["Land"], point=[6.0 * math.sin(50.0 / 15.0), 50.0, 0.0], width=3.0, depth=0.5, name="Stream")
    assert flow["joins"] == "water"
    path = np.array(flow["path"])[:, :2]
    steps = np.linalg.norm(np.diff(path, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(steps)])
    s = np.concatenate([np.arange(0.0, arc[-1] - 10.0, 0.2), np.arange(max(arc[-1] - 10.0, 0.0), arc[-1] + 6.0, 0.02)])
    heading = (path[-1] - path[-2]) / np.linalg.norm(path[-1] - path[-2])
    line = np.column_stack([np.interp(s, arc, path[:, 0]), np.interp(s, arc, path[:, 1])])
    beyond = s > arc[-1]
    line[beyond] = path[-1] + np.outer(s[beyond] - arc[-1], heading)
    river = top_hits("Stream", line)
    lake = top_hits("Pond", line)
    covered = ~np.isnan(river) | ~np.isnan(lake)
    start = int(np.argmax(covered))
    assert covered[start:].all(), ("a dry gap along the river", line[start:][~covered[start:]][:5])
    assert not np.isnan(lake[-1])
    both = ~np.isnan(river) & ~np.isnan(lake)
    if both.any():
        below = lake[both] - river[both]
        assert below.min() >= 0.001 and below.max() <= 0.05, ("where both cover the bed the river lies just under the lake", below.min(), below.max())
    assert -0.03 < flow["profile"][-1][1] - pond["level"] < 0.0



def test_a_river_into_a_part_filled_hollow_ends_in_its_lake(bridge):
    """A lake below the spill level of its hollow is an outlet of its own: water running into the hollow reaches the lake
    instead of wandering across the filled flat towards the hollow's spill point."""
    from blendworks_bridge import liquid_grid, liquid_river

    grid = liquid_grid.Grid.covering((-60.0, -60.0), (60.0, 60.0), 1.0)
    x, y = grid.node_points()
    radius = np.hypot(x, y)
    heights = np.minimum(radius ** 2 / 200.0, 4.0 + 0.02 * np.abs(x)) + np.where((y > 0.0) & (np.abs(x) < 3.0), -3.0 * np.clip((radius - 40.0) / 20.0, 0.0, 1.0), 0.0)
    lake = radius < 6.0
    line, reached = liquid_river.lowest_line(grid, heights, (-50.0, -20.0, 0.0), lake)
    assert reached, line[-5:]
    assert np.hypot(line[-1, 0], line[-1, 1]) < 7.0



def test_a_carved_river_runs_in_its_channel_below_its_banks(bridge):
    """On a flat floodplain falling 1 % a carved river keeps to its channel: its water is no wider than the channel and
    the banks beside it stand above the water, instead of the river spreading over the plain as a flat sheet."""
    import bmesh

    mesh = bpy.data.meshes.new("Plain")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=120, y_segments=120, size=30.0)
    for vertex in bm.verts:
        vertex.co.z = 0.01 * vertex.co.y
    bm.to_mesh(mesh)
    bm.free()
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("Plain", mesh))
    flow = bridge.ok("liquid_body", kind="river", ground=["Plain"], path=[[0.0, 25.0, 0.0], [0.0, -25.0, 0.0]], width=3.0, depth=0.5, name="Brook", resolution=0.25)
    top = mesh_points("Brook")[: len(mesh_points("Brook")) // 2]
    middle = np.abs(top[:, 1]) < 15.0
    assert np.abs(top[middle, 0]).max() <= 1.5 + 2.0 * flow["cell"], np.abs(top[middle, 0]).max()
    profile = np.array(flow["profile"])
    plain = 0.01 * np.interp(profile[:, 0], [0.0, 50.0], [25.0, -25.0])
    inner = (profile[:, 0] > 10.0) & (profile[:, 0] < 40.0)
    assert np.all(profile[inner, 1] < plain[inner] - 0.05), "the water stands below the banks"


run(globals())
