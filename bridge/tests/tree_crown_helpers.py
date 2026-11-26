from blendworks_bridge.tree_crown import FILL_BAND, FOLIAGE_BAND
from blendworks_bridge.tree_species import FILL_FLOOR

LEAF_AREA_DENSITY = (0.3, 3.0)
LEAF_AREA_INDEX = (2.0, 8.0)
THINNED = {
    "oak": {"leaves": [3, 4], "spacing": 0.26},
    "birch": {"leaves": [2, 3], "spacing": 0.26},
    "pine": {"leaves": [2, 3], "spacing": 0.21},
    "willow": {"leaves": [3, 4], "spacing": 0.26},
    "maple": {"leaves": [1, 3], "spacing": 0.36},
    "olive": {"leaves": [4, 7], "spacing": 0.16},
}


def crown_of(bridge, species, seed=1, **leaves):
    bridge.ok("new_scene")
    bridge.ok("grow_tree", name="Tree", preset=species, seed=seed, limit=0)
    return bridge.ok("tree_leaves", name="Tree", seed=seed, measure=True, **leaves)


def check_species(bridge, species):
    reply = crown_of(bridge, species)
    crown = reply["crown"]
    low, high = crown["band"]
    assert (low, high) == FILL_BAND and crown["within_band"], (species, crown)
    assert crown["foliage_within_band"] and FOLIAGE_BAND[0] <= crown["foliage_fill"] <= FOLIAGE_BAND[1], (species, crown)
    assert crown["foliage_fill"] >= FILL_FLOOR[species], (species, crown)
    for view in ("front", "back", "left", "right"):
        assert FOLIAGE_BAND[0] - 0.05 <= crown["views"][view]["foliage_fill"] <= FOLIAGE_BAND[1] + 0.05, (species, view, crown)
    foliage = reply["foliage"]
    assert LEAF_AREA_DENSITY[0] <= foliage["leaf_area_density"] <= LEAF_AREA_DENSITY[1], (species, foliage)
    assert LEAF_AREA_INDEX[0] <= foliage["leaf_area_index"] <= LEAF_AREA_INDEX[1], (species, foliage)
    return reply


def check_thinning(bridge, species, full):
    """Thinning the preset's clusters drops its foliage fill below the species floor; full is the preset's own reply."""
    whole = full["crown"]["foliage_fill"]
    sparse = crown_of(bridge, species, clusters=THINNED[species])["crown"]["foliage_fill"]
    assert sparse < FILL_FLOOR[species] and whole - sparse > 0.12, (species, whole, sparse)
