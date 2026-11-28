"""The weather continuum: presets and the state between them."""

from .errors import bad_args

TIMES = {
    "morning": {"elevation": 25.0, "azimuth": 110.0},
    "noon": {"elevation": 55.0, "azimuth": 180.0},
    "afternoon": {"elevation": 32.0, "azimuth": 235.0},
    "golden_hour": {"elevation": 6.0, "azimuth": 265.0},
    "sunset": {"elevation": 1.0, "azimuth": 275.0},
    "dusk": {"elevation": -3.5, "azimuth": 280.0},
}
CURVES = {
    "cirrus_coverage": ((0.0, 0.0), (0.1, 0.08), (0.3, 0.18), (0.46, 0.12), (0.58, 0.0)),
    "cumulus_coverage": ((0.0, 0.0), (0.1, 0.08), (0.18, 0.22), (0.32, 0.42), (0.46, 0.5), (0.56, 0.12), (0.6, 0.0)),
    "cumulus_thickness": ((0.0, 500.0), (0.18, 750.0), (0.32, 1300.0), (0.46, 2000.0), (0.6, 2200.0)),
    "cumulus_base": ((0.0, 1400.0), (0.18, 1300.0), (0.46, 1000.0), (0.68, 800.0)),
    "strato_coverage": ((0.0, 0.0), (0.34, 0.0), (0.46, 0.4), (0.58, 0.97), (0.72, 0.6), (0.86, 0.5), (1.0, 0.55)),
    "strato_base": ((0.0, 1000.0), (0.46, 900.0), (0.6, 750.0), (0.72, 350.0), (0.86, 280.0), (1.0, 220.0)),
    "strato_thickness": ((0.0, 450.0), (0.6, 600.0), (0.72, 300.0), (1.0, 350.0)),
    "deck_coverage": ((0.0, 0.0), (0.48, 0.0), (0.58, 1.0), (1.0, 1.0)),
    "deck_base": ((0.0, 1500.0), (0.6, 1300.0), (0.72, 700.0), (0.86, 500.0), (1.0, 400.0)),
    "deck_thickness": ((0.0, 500.0), (0.6, 900.0), (0.72, 1800.0), (0.86, 3000.0), (1.0, 4500.0)),
    "deck_density": ((0.0, 1.0), (0.6, 1.0), (0.72, 1.1), (0.86, 1.3), (1.0, 1.7)),
    "dust": ((0.0, 1.0), (0.3, 1.4), (0.6, 2.2), (1.0, 3.0)),
    "visibility": ((0.0, 40000.0), (0.3, 25000.0), (0.6, 15000.0), (0.72, 9000.0), (0.86, 6000.0), (1.0, 5000.0)),
    "rain": ((0.0, 0.0), (0.64, 0.0), (0.72, 2.0), (0.86, 15.0), (1.0, 40.0)),
    "wet": ((0.0, 0.0), (0.64, 0.0), (0.72, 0.55), (0.86, 1.0), (1.0, 1.0)),
    "cool": ((0.0, 0.0), (0.46, 0.3), (0.6, 0.6), (1.0, 1.0)),
    "darken": ((0.0, 1.0), (0.6, 0.9), (0.72, 0.75), (0.86, 0.6), (1.0, 0.4)),
    "sky_key": ((0.0, 0.7), (0.46, 0.6), (0.6, 0.5), (0.72, 0.42), (0.86, 0.34), (1.0, 0.14)),
    "compensation": ((0.0, 0.8), (0.6, 0.8), (0.86, 0.8), (1.0, 0.65)),
}
PRESETS = {
    "clear": {"storm": 0.0, "note": "no clouds, clean air"},
    "hazy": {"storm": 0.05, "dust": 4.5, "visibility": 6000.0, "note": "clear sky in dust and haze: milky sky, soft sun, distant hills fade"},
    "fair_cumulus": {"storm": 0.18, "note": "small fair-weather cumulus, a fifth of the sky, thin cirrus"},
    "scattered": {"storm": 0.32, "note": "scattered cumulus, about two fifths of the sky"},
    "broken": {"storm": 0.46, "note": "broken cumulus and stratocumulus, about three quarters of the sky"},
    "overcast": {"storm": 0.6, "note": "a full stratus deck under stratocumulus: grey, shadowless light"},
    "light_rain": {"storm": 0.72, "note": "nimbostratus with light rain, wet ground"},
    "heavy_rain": {"storm": 0.86, "note": "dark nimbostratus, heavy rain, low visibility, streaming wet ground"},
    "thunderstorm": {"storm": 1.0, "lightning": True, "note": "a dark, low, thick and lumpy deck with heavy rain, a darkened land and lightning"},
    "golden_hour": {"storm": 0.18, "time_of_day": "golden_hour", "note": "fair cumulus lit gold by a low sun"},
    "clear_golden_hour": {"storm": 0.0, "time_of_day": "golden_hour", "note": "clear sky, sun 6 degrees high"},
    "dusk": {"storm": 0.0, "time_of_day": "dusk", "note": "clear sky after sunset: blue hour, no sun lamp"},
    "scattered_dusk": {"storm": 0.32, "time_of_day": "sunset", "note": "scattered cumulus lit from below at sunset"},
    "stormy_golden_hour": {"storm": 1.0, "lightning": True, "time_of_day": "golden_hour", "note": "thunderstorm at golden hour: the low sun reaches only the horizon"},
}
OVERRIDES = ("dust", "visibility", "rain", "wet", "lightning")


def curve(name, storm):
    points = CURVES[name]
    if storm <= points[0][0]:
        return points[0][1]
    for (left, low), (right, high) in zip(points, points[1:]):
        if storm <= right:
            share = (storm - left) / (right - left)
            return low + share * (high - low)
    return points[-1][1]


def layers(storm, seed):
    """Cloud layers of the continuum; a layer whose coverage or density is zero is left out."""
    found = []
    cirrus = curve("cirrus_coverage", storm)
    if cirrus > 0.005:
        found.append({"genus": "cirrus", "coverage": cirrus, "seed": seed + 1, "wind_direction": 70.0})
    cumulus = curve("cumulus_coverage", storm)
    if cumulus > 0.005:
        found.append({"genus": "cumulus", "coverage": cumulus, "base": curve("cumulus_base", storm),
                      "thickness": curve("cumulus_thickness", storm), "seed": seed + 2, "wind_direction": 95.0})
    strato = curve("strato_coverage", storm)
    if strato > 0.005:
        found.append({"genus": "stratocumulus", "coverage": strato, "base": curve("strato_base", storm),
                      "thickness": curve("strato_thickness", storm), "seed": seed + 3, "wind_direction": 95.0})
    deck = curve("deck_coverage", storm)
    if deck > 0.005:
        genus = "stratus" if storm < 0.66 else "nimbostratus"
        density = curve("deck_density", storm)
        found.append({"genus": genus, "coverage": deck, "base": curve("deck_base", storm), "thickness": curve("deck_thickness", storm),
                      "density": density, "seed": seed + 4, "wind_direction": 95.0})
    return found


def state(storm, seed=0):
    return {
        "storm": storm,
        "layers": layers(storm, seed),
        "dust": curve("dust", storm),
        "visibility": curve("visibility", storm),
        "rain": curve("rain", storm),
        "wet": curve("wet", storm),
        "cool": curve("cool", storm),
        "darken": curve("darken", storm),
        "compensation": curve("compensation", storm),
        "sky_key": curve("sky_key", storm),
        "lightning": False,
    }


def preset(name):
    if name not in PRESETS:
        raise bad_args(f"unknown weather preset {name}; choose one of {', '.join(PRESETS)}")
    return PRESETS[name]


def sun_for(time_of_day):
    if time_of_day not in TIMES:
        raise bad_args(f"unknown time_of_day {time_of_day}; choose one of {', '.join(TIMES)}")
    return dict(TIMES[time_of_day])
