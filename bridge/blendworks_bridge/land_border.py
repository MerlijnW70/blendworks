"""How distant land meets the region: at each border point the land takes the region's height and outward slope, and the
difference to the synthesized field fades with distance from the border. The broad part of the difference (the region's
valleys and slopes, smoothed along the border) fades over a long reach, so a valley runs on out of the region; the fine
part fades over a short reach, so the land soon has its own detail. Both fades are 1 with zero slope at the border."""
import numpy

PERIMETER_SAMPLES = 4096
MAX_SLOPE_GAP = 1.0


def fade(distance, reach):
    u = numpy.clip(distance / max(reach, 1e-9), 0.0, 1.0)
    return 1.0 - u * u * (3.0 - 2.0 * u)


def smooth_periodic(parameter, values, perimeter, length):
    """Gaussian smoothing of values along a closed border, sigma `length` metres, by FFT on an even resampling."""
    grid = numpy.linspace(0.0, perimeter, PERIMETER_SAMPLES, endpoint=False)
    even = numpy.interp(grid, parameter, values, period=perimeter)
    frequencies = numpy.fft.rfftfreq(PERIMETER_SAMPLES, perimeter / PERIMETER_SAMPLES)
    kernel = numpy.exp(-2.0 * (numpy.pi * frequencies * length) ** 2)
    smoothed = numpy.fft.irfft(numpy.fft.rfft(even) * kernel, PERIMETER_SAMPLES)
    return numpy.interp(parameter, grid, smoothed, period=perimeter)


class BorderCorrection:
    def __init__(self, rect, border_xy, residual, slope_gap, water, reaches, smooth_length):
        self.rect = rect
        self.perimeter = rect.perimeter()
        parameter = rect.perimeter_parameter(border_xy)
        order = numpy.argsort(parameter, kind="stable")
        self.parameter = parameter[order]
        residual = numpy.asarray(residual, dtype=numpy.float64)[order]
        self.broad = smooth_periodic(self.parameter, residual, self.perimeter, smooth_length)
        self.fine = residual - self.broad
        self.slope_gap = numpy.clip(numpy.asarray(slope_gap, dtype=numpy.float64)[order], -MAX_SLOPE_GAP, MAX_SLOPE_GAP)
        self.water = numpy.asarray(water, dtype=numpy.float64)[order]
        self.reach_fine, self.reach_broad, self.reach_slope = reaches

    def along(self, values, parameter):
        return numpy.interp(parameter, self.parameter, values, period=self.perimeter)

    def apply(self, xy):
        """(height to add, water share from the border) at points outside the region."""
        distance = self.rect.distance(xy)
        parameter = self.rect.perimeter_parameter(self.rect.project(xy))
        broad = self.along(self.broad, parameter) * fade(distance, self.reach_broad)
        fine = self.along(self.fine, parameter) * fade(distance, self.reach_fine)
        u = numpy.clip(distance / self.reach_slope, 0.0, 1.0)
        slope = self.along(self.slope_gap, parameter) * distance * (1.0 - u) ** 2
        water = self.along(self.water, parameter) * fade(distance, self.reach_fine)
        return broad + fine + slope, water

    def describe(self):
        return {
            "fine_reach": round(self.reach_fine, 3),
            "broad_reach": round(self.reach_broad, 3),
            "slope_reach": round(self.reach_slope, 3),
            "largest_correction": round(float(numpy.abs(self.broad + self.fine).max()), 4) if len(self.fine) else 0.0,
        }
