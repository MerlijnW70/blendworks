"""Tests of the meadow fields: flow, height, water, shade, paths, patches and seeds."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from meadow_helpers import fields_of, grid_mesh, paths_of, slope_along, vertices_of

SIZE = 120.0
COUNT = 61


def flat(x, y):
    return 0.0 * x


def test_moisture_rises_along_the_flow_of_a_valley(bridge):
    """Same ground plan and seed, so the noise cancels: the valley floor is wetter than the flat, and more so downstream,
    where more ground drains through it, than upstream."""
    grid_mesh(bridge, "Flat", SIZE, COUNT, flat)
    grid_mesh(bridge, "Valley", SIZE, COUNT, lambda x, y: 0.15 * numpy.abs(x) + 0.04 * y)
    bridge.ok("meadow_fields", targets=["Flat"], seed=3, paths="none")
    bridge.ok("meadow_fields", targets=["Valley"], seed=3, paths="none")
    points = vertices_of("Flat")
    gain = fields_of("Valley")["moisture"] - fields_of("Flat")["moisture"]
    floor = numpy.abs(points[:, 0]) < 2.5
    flanks = numpy.abs(points[:, 0]) > 30.0
    downstream = floor & (points[:, 1] < -25.0) & (points[:, 1] > -55.0)
    upstream = floor & (points[:, 1] > 25.0) & (points[:, 1] < 55.0)
    assert gain[floor].mean() > gain[flanks].mean() + 0.15, (gain[floor].mean(), gain[flanks].mean())
    assert gain[downstream].mean() > gain[upstream].mean() + 0.03, (gain[downstream].mean(), gain[upstream].mean())


def test_moisture_is_higher_in_a_hollow_than_on_a_hump(bridge):
    bump = lambda x, y: 2.5 * numpy.exp(-(x * x + y * y) / (2.0 * 12.0 ** 2))
    grid_mesh(bridge, "Hollow", SIZE, COUNT, lambda x, y: -bump(x, y))
    grid_mesh(bridge, "Hump", SIZE, COUNT, bump)
    bridge.ok("meadow_fields", targets=["Hollow"], seed=3, paths="none")
    bridge.ok("meadow_fields", targets=["Hump"], seed=3, paths="none")
    points = vertices_of("Hollow")
    centre = numpy.hypot(points[:, 0], points[:, 1]) < 6.0
    hollow, hump = fields_of("Hollow"), fields_of("Hump")
    assert hollow["moisture"][centre].mean() > hump["moisture"][centre].mean() + 0.2
    assert hollow["soil"][centre].mean() > hump["soil"][centre].mean() + 0.1


def bowl(x, y):
    return 0.0015 * (x * x + y * y) - 3.0


def test_moisture_falls_with_distance_from_the_water(bridge):
    grid_mesh(bridge, "Bowl", SIZE, COUNT, bowl)
    bridge.ok("meadow_fields", targets=["Bowl"], seed=3, paths="none")
    dry = fields_of("Bowl")["moisture"]
    bridge.ok("liquid_body", kind="lake", name="Lake", ground=["Bowl"], point=[0.0, 0.0, 0.0], level=-1.5, seed=1)
    bridge.ok("meadow_fields", targets=["Bowl"], seed=3, paths="none")
    wet = fields_of("Bowl")["moisture"]
    points = vertices_of("Bowl")
    radius = numpy.hypot(points[:, 0], points[:, 1])
    shore = math.sqrt(1.5 / 0.0015)
    gain = wet - dry
    bands = [gain[(radius > shore + low) & (radius < shore + high)].mean() for low, high in ((1.0, 5.0), (10.0, 15.0), (25.0, 30.0))]
    assert bands[0] > bands[1] > bands[2], bands
    assert bands[0] > 0.2 and bands[2] < 0.1, bands
    assert wet[radius < shore - 2.0].min() == 1.0


def test_shade_and_moisture_follow_a_caster_along_the_sun(bridge):
    grid_mesh(bridge, "Field", 60.0, 61, flat)
    bridge.ok("meadow_fields", targets=["Field"], seed=3, paths="none")
    open_sky = fields_of("Field")
    bridge.ok("add_light", type="sun", name="Sun", rotation=[45.0, 0.0, 0.0])
    bridge.ok("add_primitive", type="cylinder", name="Crown", radius=3.0, depth=4.0, location=[0.0, 0.0, 6.0])
    bridge.ok("meadow_fields", targets=["Field"], seed=3, shade=["Crown"], paths="none")
    shaded = fields_of("Field")
    points = vertices_of("Field")
    sun = numpy.array(bpy.data.objects["Sun"].matrix_world.to_3x3().col[2])
    shadow_centre = -sun[:2] / sun[2] * 6.0
    in_shadow = numpy.hypot(points[:, 0] - shadow_centre[0], points[:, 1] - shadow_centre[1]) < 2.0
    sunny_side = numpy.hypot(points[:, 0] + shadow_centre[0], points[:, 1] + shadow_centre[1]) < 2.0
    assert shaded["shade"][in_shadow].mean() > 0.6
    assert shaded["shade"][sunny_side].mean() < 0.1
    assert (shaded["moisture"] - open_sky["moisture"])[in_shadow].mean() > 0.05
    assert abs((shaded["moisture"] - open_sky["moisture"])[sunny_side].mean()) < 0.01


def test_a_canopy_attribute_written_on_the_ground_shades_it(bridge):
    vertices = grid_mesh(bridge, "Field", 40.0, 41, flat)
    canopy = (vertices[:, 0] > 0.0).astype(numpy.float32)
    attribute = bpy.data.objects["Field"].data.attributes.new("meadow_canopy", "FLOAT", "POINT")
    attribute.data.foreach_set("value", canopy)
    bridge.ok("meadow_fields", targets=["Field"], seed=1, paths="none")
    shade = fields_of("Field")["shade"]
    assert shade[vertices[:, 0] > 2.0].min() > 0.99
    assert shade[vertices[:, 0] < -2.0].max() < 0.05


def hill(x, y):
    return 14.0 * numpy.exp(-(x * x + y * y) / (2.0 * 22.0 ** 2))


def hill_gradient(x, y):
    common = -hill(x, y) / 22.0 ** 2
    return common * x, common * y


def test_paths_take_gentler_slopes_than_straight_lines(bridge):
    grid_mesh(bridge, "Hill", 160.0, 81, hill)
    ends = [[-70.0, 5.0, 0.0], [70.0, -5.0, 0.0]]
    bridge.ok("meadow_fields", targets=["Hill"], seed=2, path_points=ends)
    lines = paths_of("Hill")
    assert len(lines) == 1
    path = lines[0]
    assert numpy.linalg.norm(path[0, :2] - numpy.array(ends[0][:2])) < 4.0
    assert numpy.linalg.norm(path[-1, :2] - numpy.array(ends[1][:2])) < 4.0
    straight = numpy.linspace(path[0], path[-1], 200)
    assert slope_along(path, hill_gradient) < 0.5 * slope_along(straight, hill_gradient)
    rng = numpy.random.default_rng(7)
    random_lines = []
    for _ in range(40):
        start, end = rng.uniform(-75.0, 75.0, 2), rng.uniform(-75.0, 75.0, 2)
        random_lines.append(slope_along(numpy.linspace(start, end, 100), hill_gradient))
    assert slope_along(path, hill_gradient) < 0.6 * float(numpy.mean(random_lines))


def test_paths_reach_the_water_and_tread_is_bare(bridge):
    grid_mesh(bridge, "Bowl", 160.0, 81, lambda x, y: 0.0015 * ((x - 20.0) ** 2 + y * y) - 3.0)
    bridge.ok("liquid_body", kind="lake", name="Lake", ground=["Bowl"], point=[20.0, 0.0, 0.0], level=-1.5, seed=1)
    result = bridge.ok("meadow_fields", targets=["Bowl"], seed=4)
    assert result["paths"] >= 2
    lines = paths_of("Bowl")
    shore = math.sqrt(1.5 / 0.0015)
    ends = numpy.array([point for line in lines for point in (line[0], line[-1])])
    gaps = numpy.abs(numpy.hypot(ends[:, 0] - 20.0, ends[:, 1]) - shore)
    assert gaps.min() < 4.0
    points = vertices_of("Bowl")
    disturbance = fields_of("Bowl")["disturbance"]
    from blendworks_bridge.meadow_paths import path_distance

    tread = path_distance(lines, points, 50.0)
    assert disturbance[tread < 0.25].min() > 0.9
    assert numpy.median(disturbance[tread > 20.0]) < 0.05


def test_trodden_patches_come_at_their_stated_density(bridge):
    grid_mesh(bridge, "Plain", 400.0, 101, flat)
    from blendworks_bridge.meadow_fields import TRAMPLED_AREA

    result = bridge.ok("meadow_fields", targets=["Plain"], seed=9, paths="none")
    expected = 401.0 * 401.0 / TRAMPLED_AREA
    assert abs(result["trodden_patches"] - expected) < 4.0 * math.sqrt(expected), result["trodden_patches"]
    trodden = fields_of("Plain")["disturbance"] > 0.5
    assert 0.003 < trodden.mean() < 0.15, trodden.mean()


def test_meadow_fields_refuses_missing_targets_and_unknown_path_modes(bridge):
    grid_mesh(bridge, "Field", 20.0, 11, flat)
    bridge.refuse("meadow_fields", "bad_args", targets=["Field"], paths="everywhere")
    bridge.refuse("meadow_fields", "bad_args", targets=["Field"], path_points=[[0.0, 0.0, 0.0]])
    bridge.refuse("meadow_fields", "not_found", targets=["Nothing"])


def test_the_same_seed_gives_the_same_fields(bridge):
    for name in ("First", "Second", "Third"):
        grid_mesh(bridge, name, 80.0, 41, lambda x, y: 2.0 * numpy.sin(x / 9.0) * numpy.cos(y / 13.0))
    bridge.ok("meadow_fields", targets=["First"], seed=6)
    bridge.ok("meadow_fields", targets=["Second"], seed=6)
    bridge.ok("meadow_fields", targets=["Third"], seed=7)
    first, second, third = fields_of("First"), fields_of("Second"), fields_of("Third")
    for name in first:
        assert numpy.array_equal(first[name], second[name]), name
    assert not numpy.allclose(first["grazing"], third["grazing"])
    assert bpy.data.objects["First"].data["meadow_paths"] == bpy.data.objects["Second"].data["meadow_paths"]


run(globals())
