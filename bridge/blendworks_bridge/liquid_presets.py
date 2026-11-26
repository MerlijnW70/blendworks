import copy

from .errors import bad_args

MM = 1000.0
FILTERED = 0.05
POPE_FRY_WATER = (0.2224, 0.0565, 0.00922)
SEDIMENT_SCATTERING = 0.51
SEDIMENT_ABSORPTION_443 = 0.04
SEDIMENT_SLOPE = 0.011
CHANNEL_WAVELENGTHS = (600.0, 550.0, 450.0)


def sediment(concentration):
    """Mineral particles in g/m3: Babin et al. 2003 mass-specific scattering (flat over the visible) and absorption."""
    import math

    absorption = [SEDIMENT_ABSORPTION_443 * concentration * math.exp(-SEDIMENT_SLOPE * (wavelength - 443.0)) for wavelength in CHANNEL_WAVELENGTHS]
    return absorption, [SEDIMENT_SCATTERING * concentration] * 3


def water(concentration):
    absorption, scattering = sediment(concentration)
    return [a + b for a, b in zip(POPE_FRY_WATER, absorption)], scattering


def per_metre(values):
    return [value * MM for value in values]


FRESH_ABSORPTION, FRESH_SCATTERING = water(1.0)
SEA_ABSORPTION, SEA_SCATTERING = water(0.5)
MUDDY_ABSORPTION, MUDDY_SCATTERING = water(100.0)

PRESETS = {
    "water_fresh": {
        "mode": "clear", "ior": 1.333, "absorption": FRESH_ABSORPTION, "scattering": FRESH_SCATTERING, "anisotropy": 0.9,
        "roughness": 0.02, "density": 998.0, "viscosity": 1.0e-3, "surface_tension": 0.0728, "contact_angle": 20.0,
        "sources": ["daimon_masumura_2007", "pope_fry_1997", "babin_2003", "water_properties"],
    },
    "water_sea": {
        "mode": "clear", "ior": 1.339, "absorption": SEA_ABSORPTION, "scattering": SEA_SCATTERING, "anisotropy": 0.9,
        "roughness": 0.02, "density": 1025.0, "viscosity": 1.08e-3, "surface_tension": 0.0735, "contact_angle": 20.0,
        "foam": {"color": [0.6, 0.6, 0.6]},
        "sources": ["quan_fry_1995", "pope_fry_1997", "babin_2003", "sharqawy_2010", "nayar_2014", "whitlock_1982"],
    },
    "water_muddy": {
        "mode": "clear", "ior": 1.333, "absorption": MUDDY_ABSORPTION, "scattering": MUDDY_SCATTERING, "anisotropy": 0.9,
        "roughness": 0.03, "density": 1060.0, "viscosity": 1.1e-3, "surface_tension": 0.072, "contact_angle": 20.0,
        "sources": ["daimon_masumura_2007", "pope_fry_1997", "babin_2003", "water_properties"],
    },
    "wine": {
        "mode": "clear", "ior": 1.343, "absorption": per_metre((0.11632, 0.25191, 0.29434)), "scattering": per_metre((0.00081, 0.0, 0.0)),
        "anisotropy": 0.97, "roughness": 0.01, "density": 990.0, "viscosity": 1.5e-3, "surface_tension": 0.047, "contact_angle": 15.0,
        "sources": ["narasimhan_2006", "wine_properties"],
    },
    "wine_white": {
        "mode": "clear", "ior": 1.343, "absorption": per_metre((0.01078, 0.01186, 0.02400)), "scattering": per_metre((0.00021, 0.00033, 0.00048)),
        "anisotropy": 0.95, "roughness": 0.01, "density": 990.0, "viscosity": 1.5e-3, "surface_tension": 0.047, "contact_angle": 15.0,
        "sources": ["narasimhan_2006", "wine_properties"],
    },
    "beer": {
        "mode": "clear", "ior": 1.343, "absorption": per_metre((0.01149, 0.02491, 0.05779)), "scattering": per_metre((0.00029, 0.00055, 0.00059)),
        "anisotropy": 0.95, "roughness": 0.01, "density": 1010.0, "viscosity": 1.6e-3, "surface_tension": 0.045, "contact_angle": 15.0,
        "foam": {"height": 0.02, "color": [0.93, 0.89, 0.78], "scatter_radius": 0.0015}, "bubbles": True,
        "sources": ["narasimhan_2006", "beer_properties"],
    },
    "oil": {
        "mode": "clear", "ior": 1.469, "absorption": [12.0, 6.0, 184.0], "scattering": [0.0, 0.0, 0.0], "anisotropy": 0.0,
        "roughness": 0.01, "density": 913.0, "viscosity": 0.084, "surface_tension": 0.033, "contact_angle": 10.0,
        "sources": ["codex_olive_oil", "borello_domenici_2019", "oil_properties"],
    },
    "milk": {
        "mode": "opaque", "ior": 1.346, "absorption": per_metre((0.00153, 0.00460, 0.01993)), "scattering": per_metre((18.2052, 20.3826, 22.3698)),
        "anisotropy": 0.71, "roughness": 0.05, "density": 1033.0, "viscosity": 2.0e-3, "surface_tension": 0.046, "contact_angle": 20.0,
        "sources": ["narasimhan_2006", "milk_properties"],
    },
    "juice": {
        "mode": "clear", "ior": 1.348, "absorption": per_metre((0.01296, 0.02374, 0.05218)), "scattering": per_metre((0.00257, 0.00311, 0.00413)),
        "anisotropy": 0.95, "roughness": 0.01, "density": 1045.0, "viscosity": 1.6e-3, "surface_tension": 0.06, "contact_angle": 20.0,
        "sources": ["narasimhan_2006", "juice_properties"],
    },
    "juice_grapefruit": {
        "mode": "clear", "ior": 1.348, "absorption": per_metre((0.08587, 0.18314, 0.25262)), "scattering": per_metre((0.15496, 0.15391, 0.15995)),
        "anisotropy": 0.93, "roughness": 0.01, "density": 1045.0, "viscosity": 1.8e-3, "surface_tension": 0.06, "contact_angle": 20.0,
        "sources": ["narasimhan_2006", "juice_properties"],
    },
    "coffee": {
        "mode": "clear", "ior": 1.334, "absorption": per_metre((4.79838, 6.57512, 8.84925)), "scattering": per_metre((7.78262 * FILTERED, 8.13050 * FILTERED, 8.53875 * FILTERED)),
        "anisotropy": 0.9, "concentration": 0.12, "roughness": 0.01, "density": 1000.0, "viscosity": 1.0e-3, "surface_tension": 0.065,
        "contact_angle": 20.0, "sources": ["narasimhan_2006", "coffee_strength", "coffee_properties"],
    },
    "paint": {
        "mode": "opaque", "ior": 1.5, "base_color": [0.85, 0.85, 0.83], "mean_free_path": [5e-6, 5e-6, 5e-6], "anisotropy": 0.0,
        "roughness": 0.25, "density": 1300.0, "viscosity": 1.0, "surface_tension": 0.035, "contact_angle": 30.0,
        "sources": ["paint_hiding", "paint_properties"],
    },
    "honey": {
        "mode": "clear", "ior": 1.4915, "absorption": [20.0, 39.8, 156.5], "scattering": [0.0, 0.0, 0.0], "anisotropy": 0.0,
        "roughness": 0.005, "density": 1420.0, "viscosity": 14.1, "surface_tension": 0.06, "contact_angle": 30.0,
        "sources": ["honey_refraction", "usda_honey_colour", "honey_viscosity", "caramel_hue"],
    },
    "syrup": {
        "mode": "clear", "ior": 1.455, "absorption": [27.6, 54.8, 215.7], "scattering": [0.0, 0.0, 0.0], "anisotropy": 0.0,
        "roughness": 0.005, "density": 1330.0, "viscosity": 0.15, "surface_tension": 0.06, "contact_angle": 30.0,
        "sources": ["usda_maple_2015", "caramel_hue", "sucrose_refraction", "syrup_properties"],
    },
    "mud": {
        "mode": "opaque", "ior": 1.333, "base_color": [0.09, 0.07, 0.05], "mean_free_path": [2e-4, 1.6e-4, 1.2e-4], "anisotropy": 0.0,
        "roughness": 0.3, "density": 1600.0, "viscosity": 50.0, "surface_tension": 0.07, "contact_angle": 40.0,
        "sources": ["wet_soil_albedo", "mud_properties"],
    },
    "lava": {
        "mode": "emissive", "ior": 1.6, "temperature": 1423.0, "emissivity": 0.6, "crust": 0.7, "crust_color": [0.035, 0.032, 0.03],
        "crust_emissivity": 0.95, "edge_temperature": 798.0, "roughness": 0.7, "density": 2700.0, "viscosity": 380.0,
        "surface_tension": 0.35, "contact_angle": 90.0, "sources": ["usgs_lava_temperature", "draper_1847", "lava_emissivity", "chevrel_lava_viscosity"],
    },
    "molten_metal": {
        "mode": "emissive", "metallic": True, "ior": 2.9, "temperature": 1873.0, "emissivity": 0.39, "crust": 0.15,
        "crust_color": [0.05, 0.045, 0.04], "crust_emissivity": 0.9, "edge_temperature": 1100.0, "roughness": 0.15, "base_color": [0.55, 0.55, 0.55],
        "density": 7050.0, "viscosity": 5.5e-3, "surface_tension": 1.74, "contact_angle": 120.0,
        "sources": ["kobatake_iron_emissivity", "iron_properties"],
    },
}

GLASS = {"ior": 1.52, "absorption": [1.2, 0.4, 1.0], "roughness": 0.0, "sources": ["soda_lime_glass"]}


def preset(name):
    if name not in PRESETS:
        raise bad_args(f"unknown liquid preset {name}")
    return copy.deepcopy(PRESETS[name])


def capillary_length(entry):
    return (entry["surface_tension"] / (entry["density"] * 9.81)) ** 0.5
