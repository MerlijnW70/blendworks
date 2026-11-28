"""Noise stacks: octaves, gains and domain warping evaluated in world metres."""

import numpy

from .limits import FRACTION, LACUNARITY, MAX_LENGTH, MAX_SEED, OCTAVES, SMALLEST_LACUNARITY
from .noise import BASES, basis_value
from .schema import integer, length, number, string

MODES = ("fbm", "ridged", "billow")
OFFSET_SPAN = 512.0
WARP_STREAMS = 3

STACK_FIELDS = {
    "seed": integer("Random seed; the same seed gives the same field.", 0, MAX_SEED, 0),
    "basis": string("perlin is smooth gradient noise; worley_f1 is the distance to the nearest feature point (pits); worley_f2_minus_f1 is zero on cell borders (cracks, flagstones).", list(BASES), "perlin"),
    "scale": length("Wavelength of the first octave in metres, measured in world space.", 1.0, MAX_LENGTH),
    "octaves": integer("Number of octaves, each at lacunarity times the frequency of the last.", 1, OCTAVES, 4),
    "lacunarity": number("Frequency ratio between octaves.", SMALLEST_LACUNARITY, LACUNARITY, 2.0),
    "hurst": number("Hurst exponent 0..1: each octave's amplitude is lacunarity^-hurst of the last (0.5 rough, 1 smooth); at lacunarity 2 the gain is 2^-hurst.", 0.0, FRACTION, 0.7),
    "mode": string("fbm sums the noise; ridged sums ridge_offset - |noise| (crests); billow sums |noise| (rounded lumps).", list(MODES), "fbm"),
    "ridge_offset": number("ridged: the value of a crest before scaling, 0..1; the octave term is ridge_offset - |noise|.", 0.0, FRACTION, 1.0),
    "warp": number("Domain warp in metres: the lookup point moves by warp times a second fBm, at most this far on each axis.", 0.0, MAX_LENGTH, 0.0),
    "warp_octaves": integer("Octaves of the warp fBm.", 1, OCTAVES, 2),
}


def octave_frame(seed, octave, stream=0):
    rng = numpy.random.default_rng([int(seed), int(octave), int(stream)])
    quaternion = rng.normal(size=4)
    w, x, y, z = quaternion / numpy.linalg.norm(quaternion)
    rotation = numpy.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    return rotation, rng.uniform(0.0, OFFSET_SPAN, 3), int(rng.integers(0, 2**62))


def octave_point(points, scale, lacunarity, seed, octave, stream=0):
    rotation, offset, lattice_seed = octave_frame(seed, octave, stream)
    return (points @ rotation.T) * (lacunarity**octave / scale) + offset, lattice_seed


def octave_gains(octaves, lacunarity, hurst):
    return numpy.array([lacunarity ** (-hurst * octave) for octave in range(octaves)])


def octave_value(basis, mode, ridge_offset, points, scale, lacunarity, seed, octave, stream=0):
    lattice, lattice_seed = octave_point(points, scale, lacunarity, seed, octave, stream)
    value = basis_value(basis, lattice, lattice_seed)
    if mode == "ridged":
        return ridge_offset - numpy.abs(value)
    if mode == "billow":
        return numpy.abs(value)
    return value


def stack_value(points, params, seed=None, stream=0):
    seed = params["seed"] if seed is None else seed
    gains = octave_gains(params["octaves"], params["lacunarity"], params["hurst"])
    total = numpy.zeros(len(points))
    for octave, gain in enumerate(gains):
        total += gain * octave_value(params["basis"], params["mode"], params["ridge_offset"], points, params["scale"], params["lacunarity"], seed, octave, stream)
    return total / gains.sum()


def warp_field(points, params):
    shift = numpy.zeros_like(points)
    gains = octave_gains(params["warp_octaves"], params["lacunarity"], params["hurst"])
    for axis in range(WARP_STREAMS):
        for octave, gain in enumerate(gains):
            shift[:, axis] += gain * octave_value("perlin", "fbm", 1.0, points, params["scale"], params["lacunarity"], params["seed"], octave, axis + 1)
        shift[:, axis] /= gains.sum()
    return shift


def stack_field(points, params):
    points = numpy.asarray(points, dtype=numpy.float64)
    if params["warp"] > 0.0:
        points = points + params["warp"] * warp_field(points, params)
    return stack_value(points, params)


def stack_bounds(params):
    if params["mode"] == "ridged":
        return params["ridge_offset"] - 1.0, params["ridge_offset"]
    if params["mode"] == "billow":
        return 0.0, 1.0
    return -1.0, 1.0


def finest_wavelength(params):
    return params["scale"] / params["lacunarity"] ** (params["octaves"] - 1)
