BLENDWORKS_FRESH_PROCESS = "spins up a 61 km range and times nothing, but holds about a gigabyte of grids"

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from harness import run

from blendworks_bridge import fluvial_presets, fluvial_run

SIDE = 1024
CELL = 61410.0 / (SIDE - 1)
STATE = {}


def range_with_one_base_level():
    if "result" not in STATE:
        settings = fluvial_presets.preset("young_alpine")
        settings.update({"base_level": ["south"], "crest": 0.8, "behind": 0.6})
        STATE["result"] = fluvial_run.run(settings, SIDE, CELL)
    return STATE["result"]["summary"]


def test_routing_leaves_no_undrained_pit(bridge):
    assert range_with_one_base_level()["undrained_pits"] == 0


def test_hack_exponent_lies_in_the_natural_range_over_enough_decades(bridge):
    summary = range_with_one_base_level()
    assert 0.5 <= summary["hack_exponent"] <= 0.6 and summary["hack_decades"] >= 1.5, summary


def test_the_trunk_reaches_a_high_strahler_order(bridge):
    summary = range_with_one_base_level()
    assert summary["trunk_order"] >= 4, f"trunk order {summary['trunk_order']} at 61 km with one base level side"


def test_slopes_face_east_and_west_in_equal_shares(bridge):
    summary = range_with_one_base_level()
    assert abs(summary["aspect_east_share"] - 0.5) <= 0.05, summary


def test_the_surface_does_not_follow_the_grid(bridge):
    summary = range_with_one_base_level()
    assert summary["grid_bias"] <= 1.25, summary["grid_bias"]


def test_the_channel_mask_spaces_channels_like_alpine_terrain(bridge):
    summary = range_with_one_base_level()
    print("network:", {key: summary[key] for key in ("trunk_order", "hack_exponent", "hack_decades", "grid_bias", "local_relief", "drainage_density", "hillslope_length")})
    assert 2.0 <= summary["drainage_density"] <= 30.0 and 100.0 <= summary["hillslope_length"] <= 500.0, summary


def test_the_run_ends_on_the_requested_grid_after_a_coarser_one(bridge):
    levels = range_with_one_base_level()["levels"]
    assert [level["side"] for level in levels] == [512, SIDE] and levels[0]["steps"] > levels[1]["steps"], levels


run(globals())
