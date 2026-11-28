"""Fluvial terrain presets with cited parameter ranges."""

SOURCES = {
    "burbank1996": "Burbank, D. W. et al. (1996) Bedrock incision, rock uplift and threshold hillslopes in the northwestern Himalayas. Nature 379:505-510, doi:10.1038/379505a0 (incision 2-12 mm/yr; hillslopes at about 32 degrees)",
    "dadson2003": "Dadson, S. J. et al. (2003) Links between erosion, runoff variability and seismicity in the Taiwan orogen. Nature 426:648-651, doi:10.1038/nature02150 (erosion 3-6 mm/yr over decades to millions of years)",
    "montgomery2002": "Montgomery, D. R. and Brandon, M. T. (2002) Topographic controls on erosion rates in tectonically active mountain ranges. Earth and Planetary Science Letters 201:481-489, doi:10.1016/S0012-821X(02)00725-2 (0.01-1 mm/yr below the threshold relief)",
    "whipple1999": "Whipple, K. X. and Tucker, G. E. (1999) Dynamics of the stream-power river incision model. Journal of Geophysical Research 104(B8):17661-17674, doi:10.1029/1999JB900120 (m/n about 0.4-0.6)",
    "kirby2012": "Kirby, E. and Whipple, K. X. (2012) Expression of active tectonics in erosional landscapes. Journal of Structural Geology 44:54-75, doi:10.1016/j.jsg.2012.07.009 (concavity 0.35-0.65)",
    "stock1999": "Stock, J. D. and Montgomery, D. R. (1999) Geologic constraints on bedrock river incision using the stream power law. Journal of Geophysical Research 104(B3):4983-4993, doi:10.1029/98JB02139 (K over five orders of magnitude with lithology)",
    "roering1999": "Roering, J. J., Kirchner, J. W. and Dietrich, W. E. (1999) Evidence for nonlinear, diffusive sediment transport on hillslopes. Water Resources Research 35(3):853-870, doi:10.1029/1998WR900090 (D about 0.003 m^2/yr, critical gradient 1.25)",
    "hurst2012": "Hurst, M. D. et al. (2012) Using hilltop curvature to derive the spatial distribution of erosion rates. Journal of Geophysical Research 117:F02017, doi:10.1029/2011JF002057 (D about 0.0086 m^2/yr)",
    "montgomery2001": "Montgomery, D. R. (2001) Slope distributions, threshold hillslopes, and steady-state topography. American Journal of Science 301:432-454, doi:10.2475/ajs.301.4-5.432 (hillslopes cut back to a threshold of about 30-40 degrees)",
    "montgomery1988": "Montgomery, D. R. and Dietrich, W. E. (1988) Where do channels begin? Nature 336:232-234, doi:10.1038/336232a0; and (1992) Channel initiation and the problem of landscape scale. Science 255:826-830 (channel source areas of 10^2-10^5 m^2 and more on gentle slopes)",
}

RANGES = {
    "uplift_rate": (1e-5, 1.2e-2, ("burbank1996", "dadson2003", "montgomery2002")),
    "erodibility": (1e-7, 1e-4, ("stock1999",)),
    "area_exponent": (0.35, 0.65, ("whipple1999", "kirby2012")),
    "diffusivity": (1e-3, 2e-2, ("roering1999", "hurst2012")),
    "critical_slope": (1.0, 1.5, ("roering1999",)),
    "threshold_slope": (0.45, 0.84, ("burbank1996",)),
    "channel_area": (1e3, 1e6, ("montgomery1988",)),
}
"""Each parameter: (low, high, sources) of its cited range."""

LIST_RANGES = {
    "threshold_angles": (24.0, 40.0, ("burbank1996", "montgomery2001")),
    "weak_factor": (2.0, 100.0, ("stock1999",)),
}
"""Ranges of list-valued parameters: every value of the list lies in its range."""

SETTING_UPLIFT = {
    "young_alpine": (1e-3, 1.2e-2, ("burbank1996", "dadson2003")),
    "mature_mountain": (1e-4, 1e-3, ("montgomery2002",)),
    "dissected_plateau": (1e-5, 5e-4, ("montgomery2002",)),
}
"""Narrower ranges for the tectonic setting each preset stands for."""

PRESETS = {
    "young_alpine": {
        "description": "A young range rising fast between two base levels: a central divide, steep threshold hillslopes and deep valleys.",
        "uplift_rate": 7e-3, "uplift_shape": "range", "crest": 1.0, "behind": 1.0, "along": 0.3,
        "base_level": ["south", "north"],
        "erodibility": 1.2e-5, "area_exponent": 0.45, "diffusivity": 5e-3, "critical_slope": 1.25,
        "threshold_angles": [30.0, 38.0], "channel_area": 1e4,
        "weak_belts": {"shares": [0.55], "width_share": 0.1, "wander": 0.1, "factor": 4.0},
    },
    "mature_mountain": {
        "description": "Older mountains rising slowly: lower relief, gentler threshold slopes and wider valleys.",
        "uplift_rate": 5e-4, "uplift_shape": "range", "crest": 1.0, "behind": 1.0, "along": 0.2,
        "base_level": ["south", "north"],
        "erodibility": 2e-5, "area_exponent": 0.45, "diffusivity": 1e-2, "critical_slope": 1.25,
        "threshold_angles": [28.0, 35.0], "channel_area": 3e4,
    },
    "dissected_plateau": {
        "description": "A slowly lifted block cut from every side, with hard and soft rock in bands.",
        "uplift_rate": 2e-4, "uplift_shape": "block", "margin_share": 0.05,
        "base_level": ["south", "north", "east", "west"],
        "erodibility": 1e-5, "lithology": {"factors": [0.3, 1.0, 0.6], "band_share": 0.08, "angle": 30.0},
        "area_exponent": 0.45, "diffusivity": 1e-2, "critical_slope": 1.25, "threshold_angles": [26.0, 33.0], "channel_area": 1e5,
    },
}


def preset(name):
    """A copy of the named preset's settings."""
    if name not in PRESETS:
        raise ValueError(f"preset must be one of {', '.join(PRESETS)}, got {name!r}")
    found = dict(PRESETS[name])
    found.pop("description")
    return found


def out_of_range(name):
    """The parameters of a preset outside their cited ranges, as (parameter, value, low, high)."""
    settings = PRESETS[name]
    found = []
    for key, (low, high, _) in RANGES.items():
        value = settings.get(key)
        if value is not None and not low <= value <= high:
            found.append((key, value, low, high))
    for value in settings.get("threshold_angles") or []:
        low, high, _ = LIST_RANGES["threshold_angles"]
        if not low <= value <= high:
            found.append(("threshold_angles", value, low, high))
    belts = settings.get("weak_belts")
    if belts:
        low, high, _ = LIST_RANGES["weak_factor"]
        if not low <= belts["factor"] <= high:
            found.append(("weak_factor", belts["factor"], low, high))
    low, high, _ = SETTING_UPLIFT[name]
    if not low <= settings["uplift_rate"] <= high:
        found.append(("uplift_rate", settings["uplift_rate"], low, high))
    return found
