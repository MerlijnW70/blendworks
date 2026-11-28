import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy

from harness import run
from blendworks_bridge import woodland_pattern
from blendworks_bridge.woodland_edges import EDGE_DEFAULTS
from blendworks_bridge.woodland_measure import edge_profile, measured
from blendworks_bridge.woodland_plan import expected_class_shares, plan_woodland
from blendworks_bridge.woodland_shapes import Band, Disc, Polygon
from blendworks_bridge.woodland_species import niche_weights

TREES = ["oak", "birch", "maple", "willow"]
SHRUBS = ["hazel", "hawthorn", "elder", "sallow"]
SETTINGS = {"seed": 3, "q": 1.6, "edge": dict(EDGE_DEFAULTS), "shrubs": True, "understorey": True, "shrub_density": 1.0, "understorey_density": 1.0}
LEAST_REGULARITY = 1.15
SHARE_TOLERANCE = 0.05


def dry_to_wet(xy):
    """Wet in the south, dry in the north, everywhere plantable."""
    return {"ok": numpy.ones(len(xy), dtype=bool), "moisture": numpy.clip((60.0 - xy[:, 1]) / 240.0, 0.0, 1.0)}


def forest(seed=1):
    return [(Polygon("forest", [[-150.0, -60.0], [150.0, -55.0], [140.0, 60.0], [-150.0, 55.0]], seed, 3.0, 30.0), TREES, SHRUBS)]


def copses(seed=2):
    centres = [[-300.0, 200.0], [-220.0, 330.0], [-60.0, 260.0], [80.0, 380.0], [200.0, 220.0], [320.0, 330.0]]
    return [(Disc("copse", centre, 20.0, seed + index, 3.0, 30.0), TREES, SHRUBS) for index, centre in enumerate(centres)]


def test_stems_are_regular_inside_a_stand_and_clustered_at_the_stand_scale(bridge):
    footprints = forest() + copses()
    plants, _ = plan_woodland(footprints, dry_to_wet, SETTINGS)
    report = measured(plants, footprints, SETTINGS["edge"], 5)
    assert report["stands"][0]["regularity"] >= LEAST_REGULARITY, report["stands"][0]
    inner = plants["xy"][(plants["klass"] == 0) & (plants["stand"] == 0) & (plants["depth"] > 10.0)]
    assert woodland_pattern.besag_l(inner, inner.min(axis=0), inner.max(axis=0), [5.0])[0] < 0.0
    copse_stems = plants["xy"][(plants["layer"] == 0) & (plants["stand"] >= 1)]
    low, high = copse_stems.min(axis=0) - 20.0, copse_stems.max(axis=0) + 20.0
    assert woodland_pattern.besag_l(copse_stems, low, high, [40.0])[0] > 0.0
    assert woodland_pattern.quadrat_dispersion(copse_stems, low, high, 50.0) > 2.0


def test_age_classes_follow_de_liocourts_quotient(bridge):
    for q in (1.3, 1.6, 2.0):
        footprints = forest(seed=4)
        plants, _ = plan_woodland(footprints, dry_to_wet, {**SETTINGS, "q": q})
        shares = measured(plants, footprints, SETTINGS["edge"], 5)["class_shares"]
        expected = expected_class_shares(q)
        for klass in ("mature", "young", "sapling"):
            assert abs(shares[klass] - expected[klass]) <= SHARE_TOLERANCE, (q, shares, expected)
    trees = plants["layer"] == 0
    heights = plants["share"][trees]
    for klass, (low, high) in enumerate(((0.8, 1.1), (0.4, 0.65), (0.13, 0.3))):
        chosen = heights[plants["klass"][trees] == klass]
        assert len(chosen) and chosen.min() >= low and chosen.max() <= high, klass


def test_species_follow_moisture_and_light(bridge):
    plants, _ = plan_woodland(forest(seed=6), dry_to_wet, SETTINGS)
    trees = plants["layer"] == 0
    wet, dry = plants["xy"][:, 1] < -20.0, plants["xy"][:, 1] > 20.0
    willow = plants["species"] == "willow"
    assert willow[trees & wet].mean() > 2.0 * willow[trees & dry].mean(), (willow[trees & wet].mean(), willow[trees & dry].mean())
    shrubs = plants["layer"] == 1
    sallow = plants["species"] == "sallow"
    assert sallow[shrubs & wet].mean() > 2.0 * sallow[shrubs & dry].mean()
    weights = niche_weights(["maple", "birch"], [0.1, 1.0], [0.5, 0.5])
    shade_share = weights[0, 0] / weights[0].sum()
    light_share = weights[1, 0] / weights[1].sum()
    assert shade_share > light_share
    deep, rim = trees & (plants["depth"] > 15.0), trees & (plants["depth"] < 6.0)
    maple = plants["species"] == "maple"
    assert maple[deep].mean() > maple[rim].mean(), (maple[deep].mean(), maple[rim].mean())


def bands(profile, layer, low, high):
    depth = numpy.array(profile["depth"])
    return float(numpy.array(profile[layer])[(depth >= low) & (depth < high)].mean())


def test_the_edge_is_graded_from_herbs_through_shrubs_and_saplings_to_the_canopy(bridge):
    footprints = forest(seed=8)
    plants, _ = plan_woodland(footprints, dry_to_wet, SETTINGS)
    profile = edge_profile(plants, footprints, SETTINGS["edge"], 3)
    shrubs_out, shrubs_rim, shrubs_mantle, shrubs_inside = bands(profile, "shrubs", -5.0, -2.0), bands(profile, "shrubs", -2.0, 0.0), bands(profile, "shrubs", 0.0, 6.0), bands(profile, "shrubs", 18.0, 30.0)
    assert shrubs_out < shrubs_rim < shrubs_mantle, (shrubs_out, shrubs_rim, shrubs_mantle)
    assert shrubs_inside < 0.5 * shrubs_mantle, (shrubs_inside, shrubs_mantle)
    assert bands(profile, "herbs", -4.0, 0.0) > 3.0 * bands(profile, "herbs", 6.0, 20.0)
    assert bands(profile, "ferns", 10.0, 30.0) > 3.0 * bands(profile, "ferns", -4.0, 2.0)
    assert bands(profile, "mature", 0.0, 2.0) < 0.5 * bands(profile, "mature", 10.0, 20.0)
    outer = plants["depth"][(plants["klass"] == 0)]
    assert numpy.percentile(outer, 10) > 0.0 and numpy.std(outer[outer < numpy.percentile(outer, 20)]) > 0.5
    woody = plants["layer"] <= 1
    tops = []
    for low, high in ((-3.0, 0.0), (0.0, 4.0), (6.0, 14.0), (20.0, 40.0)):
        chosen = woody & (plants["depth"] >= low) & (plants["depth"] < high)
        tops.append(float(numpy.percentile(plants["height"][chosen], 90)))
    assert tops == sorted(tops) and tops[-1] > 2.0 * tops[0], tops


def test_hedgerows_hold_dense_shrubs_along_their_line_with_few_standard_trees(bridge):
    footprints = [(Band("hedgerow", [[-200.0, 0.0], [0.0, 10.0], [200.0, -5.0]], 4.0, False, 3, 1.0, 30.0), TREES, SHRUBS)]
    plants, _ = plan_woodland(footprints, dry_to_wet, SETTINGS)
    shrubs = plants["xy"][plants["layer"] == 1]
    assert len(shrubs) > 100
    along = numpy.sort(shrubs[:, 0])
    assert numpy.diff(along).max() < 12.0
    mature = (plants["klass"] == 0).sum()
    assert 0 < mature < len(shrubs) / 6


def test_the_same_seed_repeats_and_another_differs(bridge):
    first, _ = plan_woodland(forest() + copses(), dry_to_wet, SETTINGS)
    again, _ = plan_woodland(forest() + copses(), dry_to_wet, SETTINGS)
    other, _ = plan_woodland(forest() + copses(), dry_to_wet, {**SETTINGS, "seed": 4})
    for field in ("xy", "klass", "share", "radius", "turn", "key"):
        assert numpy.array_equal(first[field], again[field]), field
    assert list(first["species"]) == list(again["species"])
    assert len(first["xy"]) != len(other["xy"]) or not numpy.array_equal(first["xy"], other["xy"])


run(globals())
