"""The height field of distant land: octaves of gradient noise whose amplitudes are calibrated until the land measures as
the region does (band variances, then the share and size of water and of flat ground), a range field for the ranges
style, and the drop of a round earth. Every number comes from a seeded noise, so the same seed gives the same land."""
import math

import numpy

from . import land_stats
from .noise_stack import octave_value

STYLES = ("rolling", "ranges")
LONG_HURST_CAP = 0.5
LONGEST_ROLLING = 20_000.0
LONGEST_RANGE = 16_000.0
SHORTEST_RANGE = 400.0
SPECTRUM_ROUNDS = 5
SIZE_ROUNDS = 2
FLAT_STEPS = 12
STEP_CLAMP = (0.25, 4.0)
LOWNESS_WEIGHT = 1.0
SHORE_WIDTH = 0.12
WATER_DEPTH = 0.25
FLAT_KEEP = 0.04
PATCH_SAMPLES = 2048
OCTAVE_STREAM = 7
WATER_STREAM = 11
FLAT_STREAM = 13
RANGE_STREAM = 17
CHUNK = 65_536

_moments = {}


def noise_moments():
    """Standard deviation of one octave of Perlin noise and the mean of a ridged octave, measured once on fixed points."""
    if not _moments:
        points = numpy.random.default_rng(0).uniform(0.0, 4000.0, (PATCH_SAMPLES * 8, 3))
        points[:, 2] = 0.0
        values = octave_value("perlin", "fbm", 1.0, points, 37.0, 1.0, 1, 0)
        _moments["std"] = float(values.std())
        _moments["ridge_mean"] = float(((1.0 - numpy.abs(values)) ** 2).mean())
    return _moments


def smoothstep(edge0, edge1, value):
    t = numpy.clip((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lod_fade(wavelength, spacing):
    """1 for octaves three spacings long or more, 0 for those under 1.5: the mesh cannot carry shorter ones."""
    if spacing is None:
        return 1.0
    return numpy.clip((wavelength / spacing - 1.5) / 1.5, 0.0, 1.0)


def plane_points(xy):
    xy = numpy.asarray(xy, dtype=numpy.float64)
    return numpy.column_stack([xy[:, 0], xy[:, 1], numpy.zeros(len(xy))])


class LandField:
    """Octaves are (wavelength, amplitude) pairs; streams keep the noise of each octave and of each mask apart."""

    def __init__(self, stats, style, seed, region_size, range_height=0.0, range_start=0.0, range_reach=1.0):
        self.stats = stats
        self.style = style
        self.seed = int(seed)
        self.region_size = float(region_size)
        moments = noise_moments()
        self.noise_std = moments["std"]
        self.ridge_mean = moments["ridge_mean"]
        self.octaves = self.first_octaves(stats)
        self.water = None
        self.flat = None
        self.range_height = float(range_height) if style == "ranges" else 0.0
        self.range_start = float(range_start)
        self.range_reach = max(float(range_reach), 1.0)
        self.range_octaves = self.mountain_octaves(stats)

    def first_octaves(self, stats):
        bands = list(zip(stats["wavelengths"], stats["band_variances"]))
        octaves = [[wavelength, math.sqrt(max(variance, 0.0)) / self.noise_std] for wavelength, variance in bands]
        if not octaves:
            return []
        top_wavelength, top_amplitude = octaves[0]
        exponent = min(stats["hurst"], LONG_HURST_CAP)
        wavelength = top_wavelength * 2.0
        longest = min(LONGEST_ROLLING, max(16.0 * self.region_size, top_wavelength * 2.0))
        while wavelength <= longest:
            octaves.insert(0, [wavelength, top_amplitude * (wavelength / top_wavelength) ** exponent])
            wavelength *= 2.0
        return octaves

    def mountain_octaves(self, stats):
        if self.style != "ranges":
            return []
        shortest = max(SHORTEST_RANGE, 2.0 * stats["dominant_wavelength"])
        octaves, wavelength, gain = [], LONGEST_RANGE, 1.0
        while wavelength >= shortest:
            octaves.append((wavelength, gain))
            wavelength /= 2.0
            gain *= 0.5
        total = sum(weight for _, weight in octaves) or 1.0
        return [(wavelength, weight / total) for wavelength, weight in octaves]

    def octave(self, points, wavelength, index, stream):
        return octave_value("perlin", "fbm", 1.0, points, wavelength, 1.0, self.seed + 1009 * stream, index)

    def octave_table(self, points, spacing=None):
        """Faded octave values per point: one column per octave of self.octaves."""
        table = numpy.zeros((len(points), len(self.octaves)))
        for index, (wavelength, amplitude) in enumerate(self.octaves):
            fade = lod_fade(wavelength, spacing)
            if amplitude == 0.0 or numpy.all(fade == 0.0):
                continue
            table[:, index] = amplitude * fade * self.octave(points, wavelength, index, OCTAVE_STREAM)
        return table

    def longer_than(self, wavelength):
        return numpy.array([octave[0] >= wavelength for octave in self.octaves], dtype=bool)

    def mask_field(self, points, wavelength, stream):
        first = self.octave(points, wavelength, 0, stream)
        second = self.octave(points, wavelength / 2.0, 1, stream)
        return (first + 0.5 * second) / (self.noise_std * math.sqrt(1.25))

    def lowness(self, table, wavelength):
        smooth = table[:, self.longer_than(4.0 * wavelength)].sum(axis=1)
        detail = table.sum(axis=1) - smooth
        return detail / max(self.stats["relief"], 1e-6), smooth

    def shaped(self, points, table):
        """Heights with lakes and flats: (heights, water share 0..1 per point)."""
        heights = table.sum(axis=1)
        water = numpy.zeros(len(points))
        if self.flat is not None:
            low, smooth = self.lowness(table, self.flat["wavelength"])
            score = self.mask_field(points, self.flat["wavelength"], FLAT_STREAM) + LOWNESS_WEIGHT * low
            weight = smoothstep(self.flat["threshold"] + SHORE_WIDTH, self.flat["threshold"] - SHORE_WIDTH, score)
            flattened = smooth + FLAT_KEEP * (heights - smooth)
            heights = heights + weight * (flattened - heights)
        if self.water is not None:
            low, _ = self.lowness(table, self.water["wavelength"])
            level = table[:, self.longer_than(8.0 * self.water["wavelength"])].sum(axis=1) - WATER_DEPTH * self.stats["relief"]
            score = self.mask_field(points, self.water["wavelength"], WATER_STREAM) + LOWNESS_WEIGHT * low
            water = smoothstep(self.water["threshold"] + SHORE_WIDTH, self.water["threshold"] - SHORE_WIDTH, score)
            heights = heights + water * (level - heights)
        return heights, water

    def ranges(self, points, spacing, border_distance):
        if not self.range_octaves or self.range_height <= 0.0:
            return numpy.zeros(len(points))
        rise = numpy.maximum(border_distance - self.range_start, 0.0) / self.range_reach
        envelope = (1.0 - numpy.exp(-rise)) * smoothstep(0.0, 1.0, rise * 4.0)
        total = numpy.zeros(len(points))
        live = envelope > 0.0
        if not live.any():
            return total
        for index, (wavelength, weight) in enumerate(self.range_octaves):
            fade = lod_fade(wavelength, None if spacing is None else spacing[live])
            value = self.octave(points[live], wavelength, index, RANGE_STREAM)
            total[live] += weight * fade * ((1.0 - numpy.abs(value)) ** 2 - self.ridge_mean)
        return self.range_height * envelope * total / max(1.0 - self.ridge_mean, 1e-6)

    def evaluate(self, xy, spacing=None, border_distance=None):
        """Heights relative to the region's mean level and water shares at points [x, y], in chunks."""
        xy = numpy.asarray(xy, dtype=numpy.float64)
        heights = numpy.zeros(len(xy))
        water = numpy.zeros(len(xy))
        for start in range(0, len(xy), CHUNK):
            stop = min(start + CHUNK, len(xy))
            points = plane_points(xy[start:stop])
            local = None if spacing is None else numpy.asarray(spacing)[start:stop]
            table = self.octave_table(points, local)
            part, wet = self.shaped(points, table)
            if border_distance is not None:
                part = part + self.ranges(points, local, numpy.asarray(border_distance)[start:stop])
            heights[start:stop] = part
            water[start:stop] = wet
        return heights, water

    def calibrate(self, shape, spacing, origin):
        """Scale the octaves until a patch of the region's size measures as the region, then place water and flats."""
        patch = patch_points(shape, spacing, origin)
        points = plane_points(patch)
        targets = numpy.array(self.stats["band_variances"])
        for _ in range(SPECTRUM_ROUNDS):
            heights = self.octave_table(points).sum(axis=1).reshape(shape)
            measured = land_stats.statistics(heights, spacing)
            ratios = numpy.ones(len(self.octaves))
            offset = len(self.octaves) - len(targets)
            for band, (target, found) in enumerate(zip(targets, measured["band_variances"])):
                if target > 0.0 and found > 0.0:
                    ratios[offset + band] = numpy.clip(math.sqrt(target / found), *STEP_CLAMP)
            if offset > 0 and targets.size and measured["band_variances"][0] > 0.0 and targets[0] > 0.0:
                ratios[:offset] = ratios[offset]
            for index, ratio in enumerate(ratios):
                self.octaves[index][1] *= float(ratio)
        self.fit_long_octaves(points, shape, spacing, len(self.octaves) - len(targets))
        found = land_stats.statistics(self.octave_table(points).sum(axis=1).reshape(shape), spacing)["relief"]
        if found > 0.0:
            for octave in self.octaves:
                octave[1] *= self.stats["relief"] / found
        if self.stats["water_share"] > 0.0:
            self.water = self.place_mask(shape, spacing, origin, self.stats["water_size"], self.stats["water_share"], WATER_STREAM)
        if self.stats["flat_share"] > 0.0:
            self.flat = self.place_flats(shape, spacing, origin)
        heights, water = self.evaluate(patch)
        return land_stats.statistics(heights.reshape(shape), spacing, water.reshape(shape) >= 0.5)

    def fit_long_octaves(self, points, shape, spacing, count):
        """Octaves longer than the region cannot be measured in it; they keep the measured spectral slope but are scaled
        down, by bisection, until a region-sized patch has no more relief than the region."""
        if count == 0:
            return
        table = self.octave_table(points)
        short = table[:, count:].sum(axis=1)
        long_part = table[:, :count].sum(axis=1)

        def relief(factor):
            return land_stats.statistics((short + factor * long_part).reshape(shape), spacing)["relief"]

        target = self.stats["relief"]
        if relief(1.0) <= target:
            return
        low, high = 0.0, 1.0
        for _ in range(FLAT_STEPS):
            middle = 0.5 * (low + high)
            if relief(middle) > target:
                high = middle
            else:
                low = middle
        for index in range(count):
            self.octaves[index][1] *= low

    def mask_scores(self, points, table, wavelength, stream):
        low, _ = self.lowness(table, wavelength)
        return self.mask_field(points, wavelength, stream) + LOWNESS_WEIGHT * low

    def place_mask(self, shape, spacing, origin, size, share, stream):
        size = size if size > 0.0 else self.stats["dominant_wavelength"]
        wavelength = 2.0 * size
        extent = max(shape[0] * spacing, 6.0 * size)
        wide_spacing = extent / shape[0]
        patch = patch_points(shape, wide_spacing, origin)
        points = plane_points(patch)
        table = self.octave_table(points)
        for _ in range(SIZE_ROUNDS):
            scores = self.mask_scores(points, table, wavelength, stream)
            threshold = float(numpy.quantile(scores, share))
            found = land_stats.patch_size((scores < threshold).reshape(shape), wide_spacing)
            if found <= 0.0:
                break
            wavelength *= min(max(size / found, 0.25), 4.0)
        scores = self.mask_scores(points, table, wavelength, stream)
        return {"wavelength": wavelength, "threshold": float(numpy.quantile(scores, share))}

    def place_flats(self, shape, spacing, origin):
        placed = self.place_mask(shape, spacing, origin, self.stats["flat_size"], self.stats["flat_share"], FLAT_STREAM)
        patch = patch_points(shape, spacing, origin)
        points = plane_points(patch)
        table = self.octave_table(points)
        scores = self.mask_scores(points, table, placed["wavelength"], FLAT_STREAM)
        low, high = 0.0, 1.0
        for _ in range(FLAT_STEPS):
            middle = 0.5 * (low + high)
            self.flat = {"wavelength": placed["wavelength"], "threshold": float(numpy.quantile(scores, middle))}
            heights, water = self.shaped(points, table)
            share = land_stats.statistics(heights.reshape(shape), spacing, water.reshape(shape) >= 0.5)["flat_share"]
            if share < self.stats["flat_share"]:
                low = middle
            else:
                high = middle
        return {"wavelength": placed["wavelength"], "threshold": float(numpy.quantile(scores, 0.5 * (low + high)))}

    def describe(self):
        return {
            "style": self.style,
            "octaves": [[round(w, 3), round(a, 6)] for w, a in self.octaves],
            "water": None if self.water is None else {key: round(value, 6) for key, value in self.water.items()},
            "flat": None if self.flat is None else {key: round(value, 6) for key, value in self.flat.items()},
            "range_height": round(self.range_height, 3),
        }


def patch_points(shape, spacing, origin):
    rows, columns = shape
    xs = origin[0] + (numpy.arange(columns) - (columns - 1) / 2.0) * spacing
    ys = origin[1] + (numpy.arange(rows) - (rows - 1) / 2.0) * spacing
    grid_x, grid_y = numpy.meshgrid(xs, ys)
    return numpy.column_stack([grid_x.ravel(), grid_y.ravel()])


def earth_drop(xy, centre, radius):
    """How far a round earth of this radius falls below the tangent plane at centre: R - sqrt(R^2 - r^2)."""
    if radius is None or radius <= 0.0:
        return numpy.zeros(len(xy))
    reach = numpy.hypot(xy[:, 0] - centre[0], xy[:, 1] - centre[1])
    reach = numpy.minimum(reach, radius)
    return radius - numpy.sqrt(radius * radius - reach * reach)
