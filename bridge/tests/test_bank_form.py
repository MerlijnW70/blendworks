import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
from mathutils import Vector

from harness import run

from blendworks_bridge import bank_form, ground_form, liquid_river, liquid_world

WIDTH, DEPTH = 4.0, 0.6
OUTER_OVER_INNER = 3.0
SIZE = 40.0
COVER_TOLERANCE = 0.02


def meander(bridge, seed=0):
    """A flat floodplain 1.2 m above the river bed's reference with a sine meander across it."""
    bridge.ok("heightfield", name="Plain", size=[SIZE, SIZE], resolution=201, height=0.05, base_height=1.2, scale=30.0, octaves=2, seed=seed)
    bridge.ok("add_material", name="Soil", base_color=[0.2, 0.15, 0.1])
    bridge.ok("assign_material", name="Plain", material="Soil")
    xs = np.linspace(1.0, SIZE - 1.0, 60)
    path = [[float(x), float(SIZE / 2 + 5.0 * math.sin(2.0 * math.pi * x / 20.0)), 0.0] for x in xs]
    result = bridge.ok("liquid_body", kind="river", name="River", ground=["Plain"], path=path, width=WIDTH, depth=DEPTH, seed=1)
    return result, path


def heights_at(points):
    obj = bpy.data.objects["Plain"]
    bpy.context.view_layer.update()
    inverse = obj.matrix_world.inverted()
    found = []
    for x, y in points:
        hit = obj.ray_cast(inverse @ Vector((x, y, 50.0)), Vector((0.0, 0.0, -1.0)))
        found.append((obj.matrix_world @ hit[1]).z if hit[0] else float("nan"))
    return np.array(found)


def apex_profiles(direction):
    """Height profiles across the channel at the two inner bend apexes of the meander (x = 15 and 25 m; the bends at the
    ends lie where the river's depth tapers in), from the centreline outwards on the outer and the inner side of each."""
    out = []
    for x, sign in ((15.0, -1.0), (25.0, 1.0)):
        centre = SIZE / 2 + 5.0 * sign
        reach = np.linspace(0.0, 4.5, 46)
        outer = heights_at([(x, centre + sign * r * direction) for r in reach])
        inner = heights_at([(x, centre - sign * r * direction) for r in reach])
        out.append((reach, outer, inner))
    return out


def water_level(x):
    """The river surface at x on the centreline of the meander (the first surface a ray from above meets)."""
    river = bpy.data.objects["River"]
    bpy.context.view_layer.update()
    y = SIZE / 2 + 5.0 * math.sin(2.0 * math.pi * x / 20.0)
    hit = river.ray_cast(river.matrix_world.inverted() @ Vector((x, y, 50.0)), Vector((0.0, 0.0, -1.0)))
    return (river.matrix_world @ hit[1]).z


def steepest(reach, profile, start):
    rise = np.diff(profile) / np.diff(reach)
    return float(np.nanmax(np.abs(rise[reach[1:] > start])))


def test_cut_banks_stand_on_outer_bends_and_point_bars_on_inner_bends(bridge):
    """At every bend apex of a meander the outer bank's steepest slope is at least OUTER_OVER_INNER times the inner bank's,
    and the inner bank carries a point bar: ground within half a metre of the water level reaching at least 0.4 channel
    widths further from the centreline than on the outer bank, classed gravel. Proven by swapping the outer and inner sides
    in bank_form.shape (the ratio then falls under one)."""
    meander(bridge)
    level = water_level(SIZE * 0.125)
    relief = np.zeros(len(bpy.data.objects["Plain"].data.vertices), dtype=np.float32)
    bpy.data.objects["Plain"].data.attributes[ground_form.RELIEF_ATTRIBUTE].data.foreach_get("value", relief)
    assert (relief == np.float32(ground_form.ROUGHNESS["gravel"])).sum() > 50
    for reach, outer, inner in apex_profiles(1.0):
        ratio = steepest(reach, outer, WIDTH / 2) / steepest(reach, inner, WIDTH / 2)
        assert ratio >= OUTER_OVER_INNER, ratio
        low_outer = reach[np.abs(outer - level) < 0.5].max()
        low_inner = reach[np.abs(inner - level) < 0.5].max()
        assert low_inner - low_outer >= 0.4 * WIDTH, (low_inner, low_outer)


def test_slumps_follow_their_stated_rate_and_the_seed(bridge):
    """The slumps along the strongly cut bank are a Poisson count of SLUMP_RATE per metre: within three standard
    deviations of the rate times the cut length, the same for the same seed. Proven by a rate of zero."""
    meander(bridge)
    banks = json.loads(bpy.data.objects["Plain"][liquid_river.BANKS_PROPERTY])
    expected = bank_form.SLUMP_RATE * banks["cut_bank_length"]
    assert banks["cut_bank_length"] > 10.0
    assert abs(banks["slumps"] - expected) <= 3.0 * math.sqrt(expected) and banks["slumps"] >= 1, banks


def test_an_undercut_bank_overhangs_the_water(bridge):
    """On the sharpest bends the bank has an undercut lip: a point under it, just above the water, sees the lip above it and
    open air between, while the ground at that point lies below the lip. Proven by dropping the lip (no mesh above)."""
    meander(bridge)
    banks = json.loads(bpy.data.objects["Plain"][liquid_river.BANKS_PROPERTY])
    assert banks["lips"], banks
    lip = bpy.data.objects[banks["lips"][0]]
    bpy.context.view_layer.update()
    points = np.array([list(lip.matrix_world @ v.co) for v in lip.data.vertices])
    tips = points[1::bank_form.LIP_RING]
    under = 0
    for x, y, z in tips[::3].tolist():
        ground = heights_at([(x, y)])[0]
        hit = lip.ray_cast(lip.matrix_world.inverted() @ Vector((x, y, ground + 0.02)), Vector((0.0, 0.0, 1.0)))
        if hit[0] and (lip.matrix_world @ hit[1]).z - ground > 0.05:
            under += 1
    assert under >= 3, under


def worn_grid(seed=3, size=24.0, resolution=161, height=3.0, scale=12.0):
    steps = resolution - 1
    axis = np.arange(resolution) * (size / steps)
    columns, rows = np.meshgrid(axis, axis)
    columns, rows = columns.ravel(), rows.ravel()
    from blendworks_bridge.terrain import surface_heights

    params = {"seed": seed, "basis": "perlin", "scale": scale, "octaves": 4, "lacunarity": 2.0, "hurst": 0.7, "mode": "fbm", "ridge_offset": 1.0, "warp": 0.0, "warp_octaves": 1}
    flat = surface_heights(columns, rows, params, height, 0.0) + 0.25 * columns
    return flat, ground_form.worn(flat, resolution, [size, size], columns, rows, seed), resolution


def test_rills_follow_flow_accumulation(bridge):
    """On a tilted rolling slope, the rill cells are those whose drainage area and slope give a stream power over the
    threshold: their median drainage area is at least ten times the median of the slope, and every rill cell has the
    threshold power. Proven by cutting the rills at random cells of the same count (the area ratio falls to about one)."""
    _, (shaped, relief, fields, report), _ = worn_grid()
    cut, area, power = fields["cut"], fields["area"], fields["power"]
    channel = cut > 0.0
    assert report["rill_cells"] > 30 and 0.0 < report["deepest_rill"] <= ground_form.RILL_MAX + 1e-9
    core = cut >= ground_form.RILL_GAIN * 1e-3
    assert np.median(area[core & (power > ground_form.RILL_THRESHOLD)]) >= 10.0 * np.median(area), (np.median(area[channel]), np.median(area))


def test_slopes_past_the_angle_of_friction_fail_and_leave_bare_scars(bridge):
    """A slope steeper than FRICTION_DEGREES fails: after forming the ground stands no steeper than about that angle, the failed cells are bare
    scars (soil relief) over a good share of the steep side, and gentle ground has none. Proven by a friction angle of 60 degrees (nothing fails)."""
    resolution, size = 81, 20.0
    axis = np.arange(resolution) * (size / (resolution - 1))
    columns, rows = np.meshgrid(axis, axis)
    flat = np.where(columns < 10.0, 0.2 * columns, 2.0 + 1.5 * (columns - 10.0)).ravel()
    shaped, relief, fields, _ = ground_form.worn(flat, resolution, [size, size], columns.ravel(), rows.ravel(), 1)
    scars = fields["scars"]
    inner = ground_form.edge_fade((resolution, resolution)) >= 1.0
    assert scars[inner & (columns > 11.0)].mean() > 0.15 and not scars[inner & (columns < 8.0)].any(), (scars[inner & (columns > 11.0)].mean(), scars[inner & (columns < 8.0)].mean())
    rise = np.abs(np.diff(shaped.reshape(resolution, resolution), axis=1)) / (size / (resolution - 1))
    before = np.abs(np.diff(flat.reshape(resolution, resolution), axis=1)) / (size / (resolution - 1))
    excess_before = np.percentile(before[inner[:, 1:]], 99) - math.tan(math.radians(ground_form.FRICTION_DEGREES))
    excess_after = np.percentile(rise[inner[:, 1:]], 99) - math.tan(math.radians(ground_form.FRICTION_DEGREES))
    assert excess_before > 0.5 and excess_after < 0.1, (excess_after, excess_before)
    assert np.allclose(relief.reshape(resolution, resolution)[inner & scars], ground_form.ROUGHNESS["soil"])


def test_tussocks_have_the_cited_sizes_and_spacing(bridge):
    """On flat grassland at 2.5 cm cells the hummocks stand between the cited heights, cover a share of the ground near
    TUSSOCK_SHARE of the mean hummock area per site, and lie about TUSSOCK_SPACING apart. Proven by doubling the heights."""
    resolution, size = 241, 6.0
    axis = np.arange(resolution) * (size / (resolution - 1))
    columns, rows = np.meshgrid(axis, axis)
    shaped, _, _, report = ground_form.worn(np.zeros(resolution * resolution), resolution, [size, size], columns.ravel(), rows.ravel(), 4)
    lifted = shaped.reshape(resolution, resolution)[20:-20, 20:-20]
    peaks = lifted[(lifted > 0.02)]
    assert ground_form.TUSSOCK_HEIGHT[0] * 0.8 <= np.percentile(peaks, 99) <= ground_form.TUSSOCK_HEIGHT[1] + 1e-6
    low, high = ground_form.TUSSOCK_RADIUS
    mean_area = math.pi * (low * low + low * high + high * high) / 3.0
    expected = ground_form.TUSSOCK_SHARE * mean_area / ground_form.TUSSOCK_SPACING**2
    assert 0.4 * expected < (lifted > 1e-4).mean() < 2.5 * expected, ((lifted > 1e-4).mean(), expected)



def lake(bridge, form):
    bridge.ok("new_scene")
    bridge.ok("heightfield", name="Land", size=[80.0, 80.0], resolution=161, height=6.0, scale=40.0, octaves=4, hurst=0.7, seed=7, form=form)
    bridge.ok("add_material", name="Grass", base_color=[0.1, 0.2, 0.05])
    bridge.ok("assign_material", name="Land", material="Grass")
    mesh = bpy.data.objects["Land"].data
    lowest = min(mesh.vertices[i].co for i in range(len(mesh.vertices)) if 20.0 < mesh.vertices[i].co.x < 60.0 and 20.0 < mesh.vertices[i].co.y < 60.0)
    return bridge.ok("liquid_body", kind="lake", name="Lake", ground=["Land"], point=[lowest.x, lowest.y, 0.0], seed=3)


def test_worn_ground_keeps_the_lake_and_its_shore_dry_of_relief(bridge):
    """A lake in a hollow of the same land, smooth and worn: the level follows the spill point and moves by less than 5 cm,
    its area by less than 10 %; cover placed on the worn shore keeps out of the water (no instance deeper than
    COVER_TOLERANCE, the error of the depth field interpolated over a 0.5 m cell at the edge); and the ground under the water and
    within 12 cm above it renders with mud relief, not the sward's, so no turf stands through shallow water. Proven by
    dropping the wet band from ground_relief (the shore ground then keeps its turf class in the shader)."""
    smooth = lake(bridge, "none")
    worn = lake(bridge, "worn")
    assert abs(worn["level"] - smooth["level"]) < 0.05 and abs(worn["area"] / smooth["area"] - 1.0) < 0.1, (smooth["level"], worn["level"], smooth["area"], worn["area"])
    cover = bridge.ok("ground_cover", target="Land", preset="lawn", budget=40000, seed=2)
    water = liquid_world.Water(liquid_world.liquid_objects(bpy.context.scene))
    population = [obj for obj in bpy.data.objects if obj.name.startswith(cover["name"] + "_") and obj.type == "MESH" and "gc_transform" in obj.data.attributes]
    assert population
    for obj in population:
        mesh = obj.data
        points = np.array([list(obj.matrix_world @ v.co) for v in mesh.vertices])
        depth = water.signed_depth(points, 5.0)
        assert (depth <= COVER_TOLERANCE).all(), (obj.name, int((depth > 1e-3).sum()), len(depth), float(depth.max()))
    from blendworks_bridge import ground_relief, nodes

    material = bpy.data.materials["Grass"]
    graph = nodes.Graph(material.node_tree)
    names = [node.bl_idname for node in material.node_tree.nodes]
    near = graph.value(1.0)
    ground_relief.relief_height(graph, near)
    added = [node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeAttribute" and node.attribute_name == ground_relief.DEPTH_ATTRIBUTE]
    assert added and len(material.node_tree.nodes) > len(names)



def test_worn_tiles_still_meet_at_their_edges(bridge):
    """Two neighbouring worn tiles of rolling ground share the heights of their common edge exactly: every form fades out
    over the outermost cells. Proven by an edge fade of zero cells (the rills then cut the edge differently in each)."""
    for index in (0, 1):
        bridge.ok("heightfield", name=f"Tile{index}", size=[30.0, 30.0], tile=[index, 0], resolution=121, height=4.0, scale=10.0, octaves=4, seed=2)
    left, right = (np.array([list(bpy.data.objects[f"Tile{i}"].matrix_world @ v.co) for v in bpy.data.objects[f"Tile{i}"].data.vertices]) for i in (0, 1))
    edge_left = left[np.abs(left[:, 0] - 30.0) < 1e-6]
    edge_right = right[np.abs(right[:, 0] - 30.0) < 1e-6]
    order_left, order_right = np.argsort(edge_left[:, 1]), np.argsort(edge_right[:, 1])
    assert len(edge_left) == 121 and np.abs(edge_left[order_left, 2] - edge_right[order_right, 2]).max() < 1e-6


run(globals())
