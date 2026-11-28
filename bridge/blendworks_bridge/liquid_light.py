"""Photometry for liquids: blackbody, emission strength and diffuse reflectance."""

import math

import numpy

PLANCK = 6.62607015e-34
LIGHT_SPEED = 2.99792458e8
BOLTZMANN = 1.380649e-23
LUMINOUS_EFFICACY = 683.0
METER_CONSTANT = 12.5
MID_GREY = 0.18
REFERENCE_EV = 15.0
CELSIUS = 273.15
DRAPER_POINT = 798.0
FIT_LOW = 900.0
FIT_HIGH = 1900.0


def photopic(wavelength_nm):
    """CIE 1931 y-bar by the multi-lobe fit of Wyman, Sloan and Shirley (JCGT 2013)."""
    lam = numpy.asarray(wavelength_nm, dtype=float)
    first = numpy.where(lam < 568.8, (lam - 568.8) * 0.0213, (lam - 568.8) * 0.0247)
    second = numpy.where(lam < 530.9, (lam - 530.9) * 0.0613, (lam - 530.9) * 0.0322)
    return 0.821 * numpy.exp(-0.5 * first * first) + 0.286 * numpy.exp(-0.5 * second * second)


def planck(wavelength_m, temperature):
    lam = numpy.asarray(wavelength_m, dtype=float)
    exponent = numpy.minimum(PLANCK * LIGHT_SPEED / (lam * BOLTZMANN * temperature), 700.0)
    return 2.0 * PLANCK * LIGHT_SPEED ** 2 / lam ** 5 / numpy.expm1(exponent)


def blackbody_luminance(temperature):
    """Luminance of a black body in cd/m2: 683 lm/W times the integral of y-bar times Planck's radiance."""
    if temperature <= 0.0:
        return 0.0
    lam = numpy.linspace(360.0, 830.0, 941)
    radiance = planck(lam * 1e-9, temperature) * 1e-9
    return float(LUMINOUS_EFFICACY * numpy.trapezoid(photopic(lam) * radiance, lam))


def scene_unit():
    """cd/m2 of one scene-linear unit: exposure 0 stands for EV100 15, metered by ISO 2720 (K = 12.5) as 18 % grey."""
    return 2.0 ** REFERENCE_EV * METER_CONSTANT / 100.0 / MID_GREY


def emission_strength(temperature, emissivity):
    return emissivity * blackbody_luminance(temperature) / scene_unit()


def emission_fit(emissivity):
    """Strength = exp(a - b / T) through the exact values at 900 K and 1900 K, so a shader can follow the temperature."""
    low = math.log(max(emission_strength(FIT_LOW, emissivity), 1e-300))
    high = math.log(max(emission_strength(FIT_HIGH, emissivity), 1e-300))
    slope = (low - high) / (1.0 / FIT_HIGH - 1.0 / FIT_LOW)
    return high + slope / FIT_HIGH, slope


def diffuse_reflectance(scattering, absorption, ior):
    """Jensen et al. 2001 (dipole) total diffuse reflectance from the reduced albedo, per channel."""
    eta = ior
    fdr = -1.440 / eta ** 2 + 0.710 / eta + 0.668 + 0.0636 * eta
    boundary = (1.0 + fdr) / (1.0 - fdr)
    result = []
    for sigma_s, sigma_a in zip(scattering, absorption):
        total = sigma_s + sigma_a
        albedo = sigma_s / total if total > 0.0 else 0.0
        root = math.sqrt(3.0 * (1.0 - albedo))
        result.append(0.5 * albedo * (1.0 + math.exp(-4.0 / 3.0 * boundary * root)) * math.exp(-root))
    return result


def transmittance(absorption, scattering, thickness):
    return [math.exp(-(a + s) * thickness) for a, s in zip(absorption, scattering)]


def fresnel(cosine, ior):
    """Unpolarised Fresnel reflectance from air into a medium of index ior."""
    cos_i = min(max(cosine, 0.0), 1.0)
    sin_t = math.sqrt(max(0.0, 1.0 - cos_i * cos_i)) / ior
    if sin_t >= 1.0:
        return 1.0
    cos_t = math.sqrt(1.0 - sin_t * sin_t)
    rs = (cos_i - ior * cos_t) / (cos_i + ior * cos_t)
    rp = (ior * cos_i - cos_t) / (ior * cos_i + cos_t)
    return 0.5 * (rs * rs + rp * rp)
