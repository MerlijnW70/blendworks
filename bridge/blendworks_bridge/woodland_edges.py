"""Graded edge profiles.

The graded profile of a woodland edge as functions of the signed distance d to the stand's rim (positive inside):
open ground, a fringe of tall herbs (the Saum) out to fringe metres beyond the rim, a mantle of shrubs (the Mantel) from
the rim to mantle metres in, a transition of saplings and young trees over the next transition metres, then the canopy of
mature trees with ferns and sparse shrubs under it (Dierschke 1974; widths after the edge structures in
docs/research/woodland.md). Each layer's density is its peak density times its profile, 0 to 1, so the edge thins out
towards the open ground instead of stopping at a line of trunks."""
import numpy

from .land_field import smoothstep

EDGE_DEFAULTS = {"fringe": 4.0, "mantle": 6.0, "transition": 10.0}
UNDERSTOREY_SHRUBS = 0.12
HERBS_UNDER_CANOPY = 0.08
SAPLINGS_UNDER_CANOPY = 0.3
YOUNG_UNDER_CANOPY = 0.5

KINDS = {
    "forest": {"spacing": 0.72, "mature_from": (0.2, 0.9), "shrubs": 1.0, "herbs": 1.0, "ferns": 1.0, "young": 1.0, "saplings": 1.0},
    "copse": {"spacing": 0.75, "mature_from": (0.15, 0.8), "shrubs": 1.0, "herbs": 1.0, "ferns": 0.8, "young": 1.0, "saplings": 1.0},
    "grove": {"spacing": 1.05, "mature_from": (-0.1, 0.25), "shrubs": 0.3, "herbs": 0.6, "ferns": 0.4, "young": 0.4, "saplings": 0.3},
    "hedgerow": {"spacing": 2.4, "mature_from": (-0.15, 0.1), "shrubs": 2.0, "herbs": 1.0, "ferns": 0.0, "young": 0.4, "saplings": 0.5},
}
YOUNG_SPACING = 0.5
SAPLING_SPACING = 0.35
SHRUB_SPACING = 0.6
HEDGEROW_SHRUB_SPACING = 0.45
STEM_CLEARANCE = 0.5
LIGHT_DEPTH = 12.0


def shrub_profile(d, edge):
    """Shrubs rise from the outer fringe to the rim, fill the mantle and fall to an understorey under the canopy."""
    rise = smoothstep(-0.75 * edge["fringe"], 0.5, d)
    fall = 1.0 - (1.0 - UNDERSTOREY_SHRUBS) * smoothstep(edge["mantle"], edge["mantle"] + edge["transition"], d)
    return rise * fall


def herb_profile(d, edge):
    """Tall herbs fill the fringe outside the rim and thin out under the shrubs and trees."""
    rise = smoothstep(-edge["fringe"] - 2.0, -0.5 * edge["fringe"], d)
    fall = 1.0 - (1.0 - HERBS_UNDER_CANOPY) * smoothstep(-0.5, 0.6 * edge["mantle"], d)
    return rise * fall


def fern_profile(d, edge):
    """Ferns grow in the shade inside the mantle and under the canopy."""
    return smoothstep(0.3 * edge["mantle"], edge["mantle"] + 0.5 * edge["transition"], d)


def sapling_profile(d, edge):
    """Saplings crowd the light at the rim and in the transition, fewer under the closed canopy."""
    rise = smoothstep(-1.0, 1.5, d)
    return rise * (1.0 - (1.0 - SAPLINGS_UNDER_CANOPY) * smoothstep(edge["mantle"], edge["mantle"] + edge["transition"], d))


def young_profile(d, edge):
    rise = smoothstep(0.0, 0.5 * edge["mantle"], d)
    return rise * (1.0 - (1.0 - YOUNG_UNDER_CANOPY) * smoothstep(edge["mantle"] + edge["transition"], edge["mantle"] + 2.0 * edge["transition"], d))


def mature_profile(d, edge, kind):
    low, high = KINDS[kind]["mature_from"]
    return smoothstep(low * edge["mantle"], high * edge["mantle"], d)


def edge_light(d):
    """Light at the rim is that of the open ground; it falls into the stand over LIGHT_DEPTH metres."""
    return numpy.exp(-numpy.maximum(d, 0.0) / LIGHT_DEPTH)


def profile_table(edge, depths):
    """Each layer's profile at the given depths, for the reply and the docs."""
    depths = numpy.asarray(depths, dtype=numpy.float64)
    return {
        "depth": [round(float(value), 2) for value in depths],
        "herbs": [round(float(value), 3) for value in herb_profile(depths, edge)],
        "shrubs": [round(float(value), 3) for value in shrub_profile(depths, edge)],
        "saplings": [round(float(value), 3) for value in sapling_profile(depths, edge)],
        "young": [round(float(value), 3) for value in young_profile(depths, edge)],
        "mature": [round(float(value), 3) for value in mature_profile(depths, edge, "forest")],
        "ferns": [round(float(value), 3) for value in fern_profile(depths, edge)],
    }
