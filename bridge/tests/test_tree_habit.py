import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

from blendworks_bridge.tree_habit import CONIFER

BROADLEAVES = ("oak", "birch", "maple", "olive", "willow")


def habit(bridge, name, **args):
    bridge.ok("new_scene")
    return bridge.ok("grow_tree", name=name, limit=0, **args)["growth"]["habit"]


def test_the_pine_grows_whorls_of_level_branches_above_a_clear_bole(bridge):
    for seed in (1, 2, 3):
        found = habit(bridge, "Pine", preset="pine", seed=seed)
        assert found["conifer"], found
        assert found["whorled_share"] >= 0.8 and found["whorls"] >= 5, found
        assert found["level_share"] >= 0.65 and 70.0 <= found["branch_angle"] <= 100.0, found
        assert found["clear_bole"] >= 0.45, found
        assert 0.5 <= found["whorl_spacing"] <= 1.6 and found["whorl_spacing_cv"] > 0.1, found


def test_the_broadleaf_presets_have_no_conifer_habit(bridge):
    for species in BROADLEAVES:
        found = habit(bridge, species, preset=species, seed=1)
        assert not found["conifer"] and found["whorled_share"] < 0.2, (species, found)
        assert found["clear_bole"] < CONIFER["clear_bole"], (species, found)


def test_a_pine_that_falls_back_to_a_broadleaf_form_is_not_a_conifer(bridge):
    fallbacks = {
        "no whorls": {"whorl": [1]},
        "branches down to the ground": {"trunk_height": 3.2},
        "rising branches": {"down_angle": [45.0, 55.0, 50.0], "down_angle_top": [35.0, 55.0, 50.0]},
    }
    for name, change in fallbacks.items():
        found = habit(bridge, "Pine", preset="pine", seed=1, **change)
        assert not found["conifer"], (name, found)


run(globals())
