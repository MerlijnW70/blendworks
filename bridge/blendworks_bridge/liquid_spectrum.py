import math

import numpy

GRAVITY = 9.81
U19_PER_U10 = 1.026
PM_HEIGHT = 0.21
PM_PEAK = 0.877
JONSWAP_HEIGHT = 1.6e-3
JONSWAP_PEAK = 3.5
JONSWAP_PEAK_POWER = -0.33
JONSWAP_GAMMA = 3.3
SIGMA_BELOW = 0.07
SIGMA_ABOVE = 0.09
SPREAD_MAX = 10.0
WHITECAP_FACTOR = 3.84e-6
WHITECAP_POWER = 3.41
SLOPE_UPWIND = 3.16e-3
SLOPE_CROSS_BASE = 3.0e-3
SLOPE_CROSS = 1.92e-3
BREAKER_INDEX = 0.78
CALM = 0.05


def sea_state(wind, fetch):
    """Significant height and peak angular frequency: fetch-limited JONSWAP until it reaches the fully developed Pierson-Moskowitz sea."""
    if wind <= CALM:
        return {"hs": 0.0, "omega": 0.0, "regime": "calm", "chi": 0.0}
    u19 = wind * U19_PER_U10
    developed_hs = PM_HEIGHT * u19 * u19 / GRAVITY
    developed_omega = PM_PEAK * GRAVITY / u19
    chi = GRAVITY * fetch / (wind * wind)
    limited_hs = JONSWAP_HEIGHT * math.sqrt(chi) * wind * wind / GRAVITY
    limited_omega = 2.0 * math.pi * JONSWAP_PEAK * chi ** JONSWAP_PEAK_POWER * GRAVITY / wind
    if limited_hs < developed_hs:
        return {"hs": limited_hs, "omega": max(limited_omega, developed_omega), "regime": "fetch_limited", "chi": chi}
    return {"hs": developed_hs, "omega": developed_omega, "regime": "fully_developed", "chi": chi}


def peak_wavelength(omega):
    return 2.0 * math.pi * GRAVITY / (omega * omega) if omega > 0.0 else 0.0


def whitecap_fraction(wind):
    return min(WHITECAP_FACTOR * max(wind, 0.0) ** WHITECAP_POWER, 1.0)


def slope_variance(wind):
    """Cox and Munk's clean-surface mean square slopes, upwind and crosswind."""
    return SLOPE_UPWIND * wind, SLOPE_CROSS_BASE + SLOPE_CROSS * wind


def jonswap_shape(omega, peak, gamma):
    with numpy.errstate(divide="ignore", over="ignore", invalid="ignore"):
        sigma = numpy.where(omega <= peak, SIGMA_BELOW, SIGMA_ABOVE)
        ratio = peak / omega
        base = omega ** -5.0 * numpy.exp(-1.25 * ratio ** 4)
        peaked = gamma ** numpy.exp(-((omega - peak) ** 2) / (2.0 * sigma * sigma * peak * peak))
        value = base * peaked
    return numpy.where(omega > 0.0, numpy.nan_to_num(value), 0.0)


def spreading(theta, omega, peak):
    """Mitsuyasu's cos^2s spreading with Goda and Suzuki's frequency-dependent s, normalised over direction."""
    with numpy.errstate(divide="ignore", invalid="ignore"):
        ratio = omega / peak if peak > 0.0 else numpy.ones_like(omega)
        exponent = numpy.where(ratio < 1.0, SPREAD_MAX * ratio ** 5.0, SPREAD_MAX * ratio ** -2.5)
    exponent = numpy.clip(numpy.nan_to_num(exponent), 0.5, 60.0)
    log_gamma = numpy.vectorize(math.lgamma)
    norm = numpy.exp(2.0 * exponent * math.log(2.0) + 2.0 * log_gamma(exponent + 1.0) - log_gamma(2.0 * exponent + 1.0)) / (2.0 * math.pi)
    return numpy.abs(numpy.cos(theta / 2.0)) ** (2.0 * exponent) * norm


class Tile:
    """A periodic square of sea surface synthesised by FFT from a directional spectrum, deterministic amplitudes and seeded phases."""

    def __init__(self, heights, slope_x, slope_y, shift_x, shift_y, jacobian, size, variance):
        self.heights = heights
        self.slope_x = slope_x
        self.slope_y = slope_y
        self.shift_x = shift_x
        self.shift_y = shift_y
        self.jacobian = jacobian
        self.size = size
        self.variance = variance

    @property
    def resolution(self):
        return self.heights.shape[0]

    def sample(self, field, x, y):
        n = self.resolution
        u = numpy.mod(numpy.asarray(x) / self.size * n, n)
        v = numpy.mod(numpy.asarray(y) / self.size * n, n)
        i0 = numpy.floor(u).astype(int) % n
        j0 = numpy.floor(v).astype(int) % n
        fu, fv = u - numpy.floor(u), v - numpy.floor(v)
        i1, j1 = (i0 + 1) % n, (j0 + 1) % n
        return (field[j0, i0] * (1 - fu) * (1 - fv) + field[j0, i1] * fu * (1 - fv)
                + field[j1, i0] * (1 - fu) * fv + field[j1, i1] * fu * fv)


def wave_numbers(resolution, size):
    k = numpy.fft.fftfreq(resolution, d=size / resolution) * 2.0 * math.pi
    kx, ky = numpy.meshgrid(k, k)
    return kx, ky


def spectral_amplitudes(state, direction, resolution, size, band, gamma):
    kx, ky = wave_numbers(resolution, size)
    k = numpy.hypot(kx, ky)
    omega = numpy.sqrt(GRAVITY * k)
    heading = math.radians(direction)
    wind = numpy.array([math.sin(heading), math.cos(heading)])
    theta = numpy.arctan2(kx * wind[1] - ky * wind[0], kx * wind[0] + ky * wind[1])
    shape = jonswap_shape(omega, state["omega"], gamma)
    with numpy.errstate(divide="ignore", invalid="ignore"):
        density = numpy.where(k > 0.0, shape * spreading(theta, omega, state["omega"]) * (GRAVITY / (2.0 * omega)) / k, 0.0)
    cell = (2.0 * math.pi / size) ** 2
    energy = numpy.nan_to_num(density) * cell
    low, high = band
    energy = numpy.where((k >= low) & (k < high), energy, 0.0)
    return kx, ky, k, energy


def normalisation(state, direction, gamma):
    """The factor that turns the spectral shape into a spectrum of variance (Hs / 4)^2, integrated on a fine polar grid."""
    if state["hs"] <= 0.0:
        return 0.0
    peak = state["omega"]
    omega = numpy.linspace(peak * 0.3, peak * 12.0, 4000)
    integral = numpy.trapezoid(jonswap_shape(omega, peak, gamma), omega)
    return (state["hs"] / 4.0) ** 2 / integral


def synthesise(state, direction, resolution, size, seed, band=(0.0, math.inf), choppiness=0.0, gamma=None):
    gamma = (JONSWAP_GAMMA if state.get("regime") == "fetch_limited" else 1.0) if gamma is None else gamma
    scale = normalisation(state, direction, gamma)
    kx, ky, k, energy = spectral_amplitudes(state, direction, resolution, size, band, gamma)
    energy = energy * scale
    amplitude = numpy.sqrt(2.0 * energy)
    rng = numpy.random.default_rng([seed, resolution, 0x5EA])
    phase = rng.uniform(0.0, 2.0 * math.pi, size=amplitude.shape)
    spectrum = amplitude * numpy.exp(1j * phase) * resolution * resolution
    heights = numpy.real(numpy.fft.ifft2(spectrum))
    slope_x = numpy.real(numpy.fft.ifft2(1j * kx * spectrum))
    slope_y = numpy.real(numpy.fft.ifft2(1j * ky * spectrum))
    with numpy.errstate(divide="ignore", invalid="ignore"):
        unit_x = numpy.where(k > 0.0, kx / k, 0.0)
        unit_y = numpy.where(k > 0.0, ky / k, 0.0)
    shift_x = -choppiness * numpy.real(numpy.fft.ifft2(1j * unit_x * spectrum))
    shift_y = -choppiness * numpy.real(numpy.fft.ifft2(1j * unit_y * spectrum))
    dxx = choppiness * numpy.real(numpy.fft.ifft2(unit_x * kx * spectrum))
    dyy = choppiness * numpy.real(numpy.fft.ifft2(unit_y * ky * spectrum))
    dxy = choppiness * numpy.real(numpy.fft.ifft2(unit_x * ky * spectrum))
    jacobian = (1.0 + dxx) * (1.0 + dyy) - dxy * dxy
    variance = float(energy.sum())
    return Tile(heights, slope_x, slope_y, shift_x, shift_y, jacobian, size, variance)


def tile_size(state, minimum):
    return max(minimum, 10.0 * peak_wavelength(state["omega"]))


def foam_threshold(jacobian, fraction):
    if fraction <= 0.0:
        return -math.inf
    return float(numpy.quantile(jacobian, min(fraction, 1.0)))


def depth_limit(depth):
    """Largest wave height that depth carries before breaking: McCowan's breaker index."""
    return BREAKER_INDEX * numpy.maximum(depth, 0.0)
