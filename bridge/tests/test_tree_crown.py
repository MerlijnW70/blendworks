import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy

from blendworks_bridge.tree_crown import FILL_BAND, silhouette_fill
from tree_crown_helpers import check_species, check_thinning, crown_of

SIZE = 128


def disc(radius, centre=(64, 48)):
    rows, columns = numpy.mgrid[0:SIZE, 0:SIZE]
    return ((rows - centre[0]) ** 2 + (columns - centre[1]) ** 2 <= radius * radius).astype(float)


def test_the_fill_is_the_mean_cover_inside_the_crown_silhouette(bridge):
    solid = silhouette_fill(disc(30))
    assert solid["fill"] > 0.9 and solid["holes"] == 0
    half = silhouette_fill(0.5 * disc(30))
    assert abs(half["fill"] / solid["fill"] - 0.5) < 0.01
    holed = disc(30) * (1.0 - disc(12))
    found = silhouette_fill(holed)
    assert found["holes"] > 0 and found["fill"] < solid["fill"] - 0.1
    sieve = disc(30) * (numpy.indices((SIZE, SIZE)).sum(axis=0) % 2)
    assert abs(silhouette_fill(sieve)["fill"] / solid["fill"] - 0.5) < 0.05


def test_a_trunk_below_the_crown_does_not_count(bridge):
    crown = disc(30)
    with_trunk = crown.copy()
    with_trunk[60:127, 46:50] = 1.0
    assert abs(silhouette_fill(with_trunk)["fill"] - silhouette_fill(crown)["fill"]) < 0.02


def test_the_oak_birch_and_pine_presets_fill_their_crowns_like_scanned_trees_and_thinning_them_drops_below_the_floor(bridge):
    for species in ("oak", "birch", "pine"):
        check_thinning(bridge, species, check_species(bridge, species))


def test_the_foliage_fill_counts_only_the_foliage_inside_the_whole_silhouette(bridge):
    crown = disc(30)
    leafy = 0.4 * crown
    found = silhouette_fill(crown, leafy)
    assert abs(found["fill"] - silhouette_fill(crown)["fill"]) < 1e-6
    assert abs(found["foliage_fill"] / found["fill"] - 0.4) < 0.01
    assert silhouette_fill(crown, 0.2 * crown)["foliage_fill"] < found["foliage_fill"] - 0.15


def test_a_sparse_crown_of_few_leaves_falls_below_the_band(bridge):
    sparse = crown_of(bridge, "oak", clusters={"spacing": 1.5, "per_tip": 1, "forks": [0, 0], "leaves": [1, 2]})
    assert sparse["crown"]["fill"] < FILL_BAND[0], sparse["crown"]
    assert not sparse["crown"]["within_band"]


run(globals())
