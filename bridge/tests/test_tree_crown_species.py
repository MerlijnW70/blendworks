import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

from tree_crown_helpers import check_species, check_thinning


def test_the_willow_maple_and_olive_presets_fill_their_crowns_like_scanned_trees_and_thinning_them_drops_below_the_floor(bridge):
    for species in ("willow", "maple", "olive"):
        check_thinning(bridge, species, check_species(bridge, species))


run(globals())
