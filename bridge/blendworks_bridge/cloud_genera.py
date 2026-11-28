"""Cloud genus presets (cumulus to cumulonimbus) and their thresholds."""

from bisect import bisect_left

from .errors import bad_args

GENERA = {
    "cumulus": {
        "base": 1200.0, "thickness": 900.0, "cell": 800.0, "extinction": 0.035, "coverage": 0.25, "profile": "heap",
        "elongation": 1.2, "roundness": 0.9, "billow": 0.22, "billow_scale": 0.25, "edge": 0.03, "albedo": 0.995, "anisotropy": 0.7,
        "detail": 0.18, "flat_top": 0.0, "fibres": 0.0, "volume": True,
    },
    "stratocumulus": {
        "base": 900.0, "thickness": 450.0, "cell": 900.0, "extinction": 0.04, "coverage": 0.7, "profile": "layer",
        "elongation": 1.7, "roundness": 0.8, "billow": 0.35, "billow_scale": 0.35, "edge": 0.25, "albedo": 0.995, "anisotropy": 0.7,
        "detail": 0.16, "flat_top": 0.6, "fibres": 0.0, "volume": True,
    },
    "stratus": {
        "base": 450.0, "thickness": 500.0, "cell": 6000.0, "extinction": 0.04, "coverage": 1.0, "profile": "layer",
        "elongation": 1.6, "roundness": 1.0, "billow": 0.2, "billow_scale": 0.12, "edge": 0.3, "albedo": 0.995, "anisotropy": 0.7,
        "detail": 0.1, "flat_top": 1.0, "fibres": 0.0, "volume": False,
    },
    "nimbostratus": {
        "base": 600.0, "thickness": 2500.0, "cell": 6000.0, "extinction": 0.04, "coverage": 1.0, "profile": "layer",
        "elongation": 1.6, "roundness": 1.0, "billow": 0.2, "billow_scale": 0.12, "edge": 0.3, "albedo": 0.99, "anisotropy": 0.7,
        "detail": 0.1, "flat_top": 1.0, "fibres": 0.0, "volume": False,
    },
    "altocumulus": {
        "base": 3500.0, "thickness": 350.0, "cell": 380.0, "extinction": 0.03, "coverage": 0.55, "profile": "layer",
        "elongation": 1.4, "roundness": 0.7, "billow": 0.3, "billow_scale": 0.45, "edge": 0.07, "albedo": 0.995, "anisotropy": 0.7,
        "detail": 0.2, "flat_top": 0.4, "fibres": 0.0, "volume": True,
    },
    "altostratus": {
        "base": 3200.0, "thickness": 1200.0, "cell": 9000.0, "extinction": 0.004, "coverage": 1.0, "profile": "layer",
        "elongation": 2.0, "roundness": 1.0, "billow": 0.15, "billow_scale": 0.1, "edge": 0.35, "albedo": 0.995, "anisotropy": 0.7,
        "detail": 0.08, "flat_top": 1.0, "fibres": 0.0, "volume": False,
    },
    "cirrus": {
        "base": 8500.0, "thickness": 700.0, "cell": 3500.0, "extinction": 0.0008, "coverage": 0.3, "profile": "layer",
        "elongation": 3.5, "roundness": 1.0, "billow": 0.25, "billow_scale": 0.25, "edge": 0.12, "albedo": 0.999, "anisotropy": 0.7,
        "detail": 0.0, "flat_top": 0.8, "fibres": 0.85, "volume": False,
    },
    "cumulonimbus": {
        "base": 900.0, "thickness": 10500.0, "cell": 3800.0, "extinction": 0.06, "coverage": 0.12, "profile": "anvil",
        "elongation": 1.0, "roundness": 0.5, "billow": 0.025, "billow_scale": 0.12, "edge": 0.04, "albedo": 0.97, "anisotropy": 0.7,
        "detail": 0.08, "flat_top": 0.0, "fibres": 0.0, "volume": True,
    },
}
QUANTILES = (
    0.0976, 0.3207, 0.3477, 0.3656, 0.3796, 0.3915, 0.4018, 0.4112, 0.4199, 0.4279,
    0.4356, 0.4429, 0.4499, 0.4565, 0.4630, 0.4694, 0.4757, 0.4818, 0.4879, 0.4939,
    0.5000, 0.5060, 0.5120, 0.5181, 0.5243, 0.5306, 0.5369, 0.5435, 0.5501, 0.5571,
    0.5644, 0.5720, 0.5801, 0.5887, 0.5981, 0.6086, 0.6204, 0.6344, 0.6522, 0.6791,
    0.8870,
)
QUANTILE_LEVELS = tuple(index / 40.0 for index in range(41))


def threshold(coverage):
    """Footprint value above which a point is cloud, so that the share `coverage` of the layer is covered."""
    if coverage >= 1.0:
        return -1.0
    if coverage <= 0.0:
        return 2.0
    level = 1.0 - coverage
    index = bisect_left(QUANTILE_LEVELS, level)
    if index <= 0:
        return QUANTILES[0]
    if index >= len(QUANTILE_LEVELS):
        return QUANTILES[-1]
    low, high = QUANTILE_LEVELS[index - 1], QUANTILE_LEVELS[index]
    share = (level - low) / (high - low) if high > low else 0.0
    return QUANTILES[index - 1] + share * (QUANTILES[index] - QUANTILES[index - 1])


def genus(name):
    if name not in GENERA:
        raise bad_args(f"unknown cloud genus {name}; choose one of {', '.join(GENERA)}")
    return GENERA[name]
