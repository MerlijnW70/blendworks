"""Statistics of a height grid that describe the character of land: relief, slopes, the variance in each octave band of
wavelengths, and the share and size of water and of flat ground. The region and the distant land are measured by the
same functions, so their numbers compare directly."""
import math

import numpy

FLAT_DEGREES = 2.0
SLOPE_QUANTILES = (0.1, 0.5, 0.9)
LEAST_BAND_CELLS = 2.0


def plane_residual(heights, valid):
    rows, columns = numpy.indices(heights.shape, dtype=numpy.float64)
    design = numpy.stack([columns[valid], rows[valid], numpy.ones(int(valid.sum()))], axis=1)
    solution, *_ = numpy.linalg.lstsq(design, heights[valid], rcond=None)
    plane = solution[0] * columns + solution[1] * rows + solution[2]
    return numpy.where(valid, heights - plane, 0.0)


def band_wavelengths(size, spacing):
    """Octave band centres from half the grid size down to two cells, longest first."""
    longest = size / 2.0
    bands = []
    wavelength = longest
    while wavelength >= LEAST_BAND_CELLS * spacing * 0.999:
        bands.append(wavelength)
        wavelength /= 2.0
    return bands


def band_variances(residual, valid, spacing, wavelengths):
    """Variance of the windowed residual carried by each octave band [w / sqrt 2, w sqrt 2), by Parseval."""
    rows, columns = residual.shape
    window = numpy.outer(numpy.hanning(rows), numpy.hanning(columns)) * valid
    energy = float((window ** 2).sum())
    if energy <= 0.0:
        return numpy.zeros(len(wavelengths))
    spectrum = numpy.abs(numpy.fft.fft2(residual * window)) ** 2 / (energy * rows * columns)
    ky = numpy.fft.fftfreq(rows, spacing)[:, None]
    kx = numpy.fft.fftfreq(columns, spacing)[None, :]
    with numpy.errstate(divide="ignore"):
        wavelength = 1.0 / numpy.hypot(kx, ky)
    variances = []
    for centre in wavelengths:
        inside = (wavelength < centre * math.sqrt(2.0)) & (wavelength >= centre / math.sqrt(2.0))
        variances.append(float(spectrum[inside].sum()))
    return numpy.array(variances)


def slopes(heights, valid, spacing):
    gradient_y, gradient_x = numpy.gradient(heights, spacing)
    inner = valid.copy()
    inner[1:, :] &= valid[:-1, :]
    inner[:-1, :] &= valid[1:, :]
    inner[:, 1:] &= valid[:, :-1]
    inner[:, :-1] &= valid[:, 1:]
    return numpy.degrees(numpy.arctan(numpy.hypot(gradient_x, gradient_y))), inner


def patches(mask):
    """Areas in cells of the 4-connected patches of a boolean grid, by union-find over the rows."""
    rows, columns = mask.shape
    labels = numpy.full(mask.shape, -1, dtype=numpy.int64)
    parent = []

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for row in range(rows):
        line = mask[row]
        for column in numpy.flatnonzero(line).tolist():
            left = labels[row, column - 1] if column > 0 and line[column - 1] else -1
            up = labels[row - 1, column] if row > 0 and mask[row - 1, column] else -1
            if left < 0 and up < 0:
                labels[row, column] = len(parent)
                parent.append(len(parent))
            elif left >= 0 and up >= 0:
                first, second = root(left), root(up)
                if first != second:
                    parent[max(first, second)] = min(first, second)
                labels[row, column] = min(first, second)
            else:
                labels[row, column] = max(left, up)
    if not parent:
        return numpy.zeros(0)
    roots = numpy.array([root(index) for index in range(len(parent))])
    flat = labels[mask]
    return numpy.bincount(roots[flat]).astype(numpy.float64)[numpy.unique(roots[flat])]


def patch_size(mask, spacing):
    """Area-weighted mean equivalent diameter of the patches in metres; 0 without patches."""
    areas = patches(mask) * spacing * spacing
    if areas.size == 0:
        return 0.0
    diameters = 2.0 * numpy.sqrt(areas / math.pi)
    return float((areas * diameters).sum() / areas.sum())


def statistics(heights, spacing, water=None, valid=None):
    """Character of a height grid of cells `spacing` metres apart. water marks cells under water; valid the measured ones."""
    heights = numpy.asarray(heights, dtype=numpy.float64)
    valid = numpy.ones(heights.shape, dtype=bool) if valid is None else numpy.asarray(valid, dtype=bool)
    water = numpy.zeros(heights.shape, dtype=bool) if water is None else (numpy.asarray(water, dtype=bool) & valid)
    if valid.sum() < 16:
        raise ValueError("too few measured points for land statistics")
    residual = plane_residual(heights, valid)
    measured = residual[valid]
    size = min(heights.shape) * spacing
    wavelengths = band_wavelengths(size, spacing)
    variances = band_variances(residual, valid, spacing, wavelengths)
    angle, inner = slopes(heights, valid, spacing)
    land = inner & ~water
    land_angles = angle[land] if land.any() else numpy.zeros(1)
    flat = land & (angle < FLAT_DEGREES)
    area = float(valid.sum())
    dominant = wavelengths[int(numpy.argmax(variances))] if len(wavelengths) else size
    return {
        "mean": float(heights[valid].mean()),
        "relief": float(measured.std()),
        "range": float(numpy.quantile(measured, 0.95) - numpy.quantile(measured, 0.05)),
        "slope": [float(value) for value in numpy.quantile(land_angles, SLOPE_QUANTILES)],
        "wavelengths": [float(value) for value in wavelengths],
        "band_variances": [float(value) for value in variances],
        "dominant_wavelength": float(dominant),
        "hurst": hurst(wavelengths, variances),
        "water_share": float(water.sum()) / area,
        "water_size": patch_size(water, spacing),
        "flat_share": float(flat.sum()) / area,
        "flat_size": patch_size(flat, spacing),
    }


def hurst(wavelengths, variances):
    """Slope of log amplitude against log wavelength over the bands that carry variance, kept within 0.2 and 1.2."""
    pairs = [(math.log(w), 0.5 * math.log(v)) for w, v in zip(wavelengths, variances) if v > 1e-12]
    if len(pairs) < 2:
        return 0.7
    x = numpy.array([pair[0] for pair in pairs])
    y = numpy.array([pair[1] for pair in pairs])
    slope = float(numpy.polyfit(x, y, 1)[0])
    return min(max(slope, 0.2), 1.2)


def compare(region, land):
    """Ratios and differences between two sets of statistics, as the tests and the reply state them."""
    return {
        "relief_ratio": land["relief"] / max(region["relief"], 1e-9),
        "slope_median_difference": land["slope"][1] - region["slope"][1],
        "slope_p90_difference": land["slope"][2] - region["slope"][2],
        "dominant_ratio": land["dominant_wavelength"] / max(region["dominant_wavelength"], 1e-9),
        "water_share_difference": land["water_share"] - region["water_share"],
        "flat_share_difference": land["flat_share"] - region["flat_share"],
    }
