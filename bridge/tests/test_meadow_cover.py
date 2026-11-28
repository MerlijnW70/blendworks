"""Tests of ground cover on the meadow fields: variation, drifts, moss, paths and molehills."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from blendworks_bridge.limits_meadow import MOST_RESPONSES
from cover_helpers import attribute_of
from meadow_helpers import fields_of, grid_mesh, instance_matrices, instance_positions, nearest_vertex_values, paths_of, vertices_of

HEIGHT_FACTOR = 1.5
DENSITY_FACTOR = 1.4
SQUARE = 20.0
CELL = 2.0


def preset_population(name, **changes):
    from blendworks_bridge.cover_presets import MEADOW

    entry = dict(next(item for item in MEADOW if item["name"] == name))
    entry.update(changes)
    return entry


def rolling(x, y):
    return 1.2 * numpy.sin(x / 11.0) * numpy.cos(y / 17.0) + 0.02 * x


def element_heights(prefix):
    found = []
    index = 0
    while f"{prefix}_e{index:03d}" in bpy.data.objects:
        found.append(bpy.data.objects[f"{prefix}_e{index:03d}"].dimensions.z)
        index += 1
    return numpy.array(found)


def spread(values):
    return float(numpy.percentile(values, 90) / max(numpy.percentile(values, 10), 1e-9))


def test_grass_height_and_density_vary_within_every_20_m_square(bridge):
    grid_mesh(bridge, "Meadow", 60.0, 121, rolling)
    bridge.ok("ground_cover", target="Meadow", seed=4, density_scale=0.25, paths="none", populations=[preset_population("short_grass", form="cards", variants=4)])
    positions = instance_positions("GroundCover_short_grass")
    matrices = instance_matrices("GroundCover_short_grass")
    pick = attribute_of("GroundCover_short_grass", "gc_pick")
    heights = numpy.linalg.norm(matrices[:, :3, 2], axis=1) * element_heights("GroundCover_short_grass")[pick]
    cells_per_side = int(SQUARE / CELL)
    found = []
    for first in range(3):
        for second in range(3):
            low = numpy.array([-30.0 + first * SQUARE, -30.0 + second * SQUARE])
            inside = numpy.all((positions[:, :2] >= low) & (positions[:, :2] < low + SQUARE), axis=1)
            cell = numpy.floor((positions[inside, :2] - low) / CELL).astype(int).clip(0, cells_per_side - 1)
            flat = cell[:, 0] * cells_per_side + cell[:, 1]
            counts = numpy.bincount(flat, minlength=cells_per_side ** 2)
            means = numpy.bincount(flat, weights=heights[inside], minlength=cells_per_side ** 2) / numpy.maximum(counts, 1)
            found.append((round(spread(means[counts > 0]), 3), round(spread(counts), 3)))
    print("spreads", found)
    assert min(item[0] for item in found) >= HEIGHT_FACTOR, found
    assert min(item[1] for item in found) >= DENSITY_FACTOR, found


def test_riper_grass_with_seed_heads_grows_where_grazing_is_light(bridge):
    vertices = grid_mesh(bridge, "Meadow", 60.0, 61, rolling)
    bridge.ok("ground_cover", target="Meadow", seed=4, density_scale=0.1, paths="none", populations=[preset_population("short_grass", form="geometry", variants=4)])
    grazing = fields_of("Meadow")["grazing"]
    positions = instance_positions("GroundCover_short_grass")
    pick = attribute_of("GroundCover_short_grass", "gc_pick")
    at = nearest_vertex_values(positions, vertices, grazing)
    assert pick[at < 0.3].mean() > pick[at > 0.7].mean() + 1.0, (pick[at < 0.3].mean(), pick[at > 0.7].mean())


def test_flowers_grow_in_single_species_drifts_that_follow_moisture(bridge):
    vertices = grid_mesh(bridge, "Bowl", 100.0, 101, lambda x, y: 0.0012 * (x * x + y * y) - 2.0)
    bridge.ok("liquid_body", kind="lake", name="Lake", ground=["Bowl"], point=[0.0, 0.0, 0.0], level=-1.0, seed=1)
    flowers = [preset_population(name, form="cards", variants=1) for name in ("daisies", "buttercups")]
    for flower in flowers:
        flower.pop("responses")
    bridge.ok("ground_cover", target="Bowl", seed=8, paths="none", populations=flowers)
    moisture = fields_of("Bowl")["moisture"]
    daisies = instance_positions("GroundCover_daisies")
    buttercups = instance_positions("GroundCover_buttercups")
    from blendworks_bridge.meadow_drifts import clark_evans

    area = 100.0 * 100.0
    assert len(daisies) > 200 and len(buttercups) > 200, (len(daisies), len(buttercups))
    for points in (daisies, buttercups):
        assert clark_evans(points, area) < 0.6, clark_evans(points, area)
    rng = numpy.random.default_rng(1)
    assert clark_evans(rng.uniform(-50.0, 50.0, (len(daisies), 2)), area) > 0.9, "random points"
    both = numpy.concatenate([daisies[:, :2], buttercups[:, :2]])
    species = numpy.concatenate([numpy.zeros(len(daisies)), numpy.ones(len(buttercups))])
    gaps = numpy.hypot(both[:, None, 0] - both[None, :, 0], both[:, None, 1] - both[None, :, 1])
    numpy.fill_diagonal(gaps, numpy.inf)
    nearest = numpy.argmin(gaps, axis=1)
    labelled_at_random = species.mean() ** 2 + (1.0 - species.mean()) ** 2
    assert (species[nearest] == species).mean() > max(0.8, labelled_at_random + 0.25), ((species[nearest] == species).mean(), labelled_at_random)
    wet_daisy = nearest_vertex_values(daisies, vertices, moisture).mean()
    wet_buttercup = nearest_vertex_values(buttercups, vertices, moisture).mean()
    assert wet_buttercup > wet_daisy + 0.15, (wet_buttercup, wet_daisy)


def shade_half(name, vertices):
    canopy = ((vertices[:, 1] > 0.0)).astype(numpy.float32)
    attribute = bpy.data.objects[name].data.attributes.new("meadow_canopy", "FLOAT", "POINT")
    attribute.data.foreach_set("value", canopy)


def test_moss_and_denser_darker_cover_grow_in_damp_shade(bridge):
    vertices = grid_mesh(bridge, "Bowl", 100.0, 101, lambda x, y: 0.0012 * (x * x + y * y) - 2.0)
    bridge.ok("liquid_body", kind="lake", name="Lake", ground=["Bowl"], point=[0.0, 0.0, 0.0], level=-1.0, seed=1)
    shade_half("Bowl", vertices)
    names = ("short_grass", "moss")
    bridge.ok("ground_cover", target="Bowl", seed=2, density_scale=0.1, paths="none", populations=[preset_population(name, form="cards", variants=2) for name in names])
    fields = fields_of("Bowl")
    damp_shade = (fields["moisture"] > 0.6) & (fields["moisture"] < 0.99) & (fields["shade"] > 0.9)
    dry_sun = (fields["moisture"] < 0.4) & (fields["shade"] < 0.1)
    assert damp_shade.sum() > 50 and dry_sun.sum() > 50
    cell_area = 1.0

    def density(name, region):
        points = instance_positions(f"GroundCover_{name}")
        owner = nearest_vertex_values(points, vertices, numpy.arange(len(vertices)))
        return numpy.isin(owner, numpy.nonzero(region)[0]).sum() / (region.sum() * cell_area)

    assert density("moss", damp_shade) > 5.0 * max(density("moss", dry_sun), 0.01)
    total_damp = sum(density(name, damp_shade) for name in names)
    total_dry = sum(density(name, dry_sun) for name in names)
    assert total_damp > 1.5 * total_dry, (total_damp, total_dry)
    grass = instance_positions("GroundCover_short_grass")
    straw = attribute_of("GroundCover_short_grass", "gc_straw")
    owner = nearest_vertex_values(grass, vertices, numpy.arange(len(vertices)))
    assert straw[dry_sun[owner]].mean() > straw[damp_shade[owner]].mean() + 0.25


def test_paths_are_bare_and_molehills_keep_to_deep_soil_in_clusters(bridge):
    vertices = grid_mesh(bridge, "Plain", 160.0, 161, lambda x, y: 0.6 * numpy.sin(x / 23.0) + 0.5 * numpy.cos(y / 19.0))
    ends = [[-75.0, -10.0, 0.0], [75.0, 10.0, 0.0]]
    result = bridge.ok("ground_cover", target="Plain", seed=3, path_points=ends,
                       populations=[preset_population("short_grass", form="cards", variants=2, density=5.5), preset_population("molehills")])
    lines = paths_of("Plain")
    from blendworks_bridge.meadow_drifts import clark_evans
    from blendworks_bridge.meadow_paths import path_distance

    grass = instance_positions("GroundCover_short_grass")
    tread = path_distance(lines, grass, 50.0)
    on_tread = (tread < 0.25).sum() / max(1e-9, 2.0 * 0.25 * float(sum(numpy.linalg.norm(numpy.diff(line[:, :2], axis=0), axis=1).sum() for line in lines)))
    away = len(grass) / (160.0 * 160.0)
    assert on_tread < 0.2 * away, (on_tread, away)
    hills = instance_positions("GroundCover_molehills")
    soil = nearest_vertex_values(hills, vertices, fields_of("Plain")["soil"])
    assert len(hills) >= 20
    assert soil.min() >= 0.25
    assert clark_evans(hills, 160.0 * 160.0) < 0.7
    report = next(entry for entry in result["populations"] if entry["name"] == "molehills")
    fields = fields_of("Plain")
    from blendworks_bridge.meadow_rules import effect

    expected = 0.012 * float(numpy.clip(effect(preset_population("molehills"), fields, "density"), 0.0, 1.0).sum())
    assert abs(report["count"] - expected) < 0.35 * expected + 3.0 * math.sqrt(expected), (report["count"], expected)


def test_ground_cover_refuses_responses_past_their_limits(bridge):
    grid_mesh(bridge, "Plot", 10.0, 11, rolling)
    response = {"field": "moisture", "affects": "density", "range": [0.2, 0.6], "values": [1.0, 0.5]}
    grass = {"name": "grass", "element": "grass", "density": 2.0, "form": "cards", "variants": 1}
    bridge.refuse("ground_cover", "bad_args", target="Plot", populations=[dict(grass, responses=[response] * (int(MOST_RESPONSES) + 1))])
    bridge.refuse("ground_cover", "bad_args", target="Plot", populations=[dict(grass, responses=[dict(response, values=[1.0, 1.5])])])
    bridge.refuse("ground_cover", "bad_args", target="Plot", populations=[dict(grass, responses=[dict(response, range=[0.4, 0.4])])])


def test_the_same_seed_gives_the_same_meadow(bridge):
    grid_mesh(bridge, "First", 40.0, 41, rolling)
    grid_mesh(bridge, "Second", 40.0, 41, rolling)
    for name in ("First", "Second"):
        bridge.ok("ground_cover", target=name, name=f"{name}Cover", preset="meadow", seed=5, density_scale=0.05)
    for population in ("short_grass", "daisies", "moss"):
        first = f"FirstCover_{population}"
        second = f"SecondCover_{population}"
        if first not in bpy.data.objects:
            assert second not in bpy.data.objects
            continue
        assert numpy.array_equal(instance_positions(first), instance_positions(second))
        assert numpy.array_equal(attribute_of(first, "gc_straw"), attribute_of(second, "gc_straw"))


run(globals())
