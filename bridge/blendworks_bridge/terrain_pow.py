"""Portable exp, ln and pow from basic arithmetic, so both engines give the same bits on every platform."""

import numpy

LN2_HI = 6.93147180369123816490e-01
LN2_LO = 1.90821492927058770002e-10
INV_LN2 = 1.44269504088896338700e00
SQRT_HALF = 0.70710678118654752440
TWO_54 = 18014398509481984.0
EXP_MAX = 709.782712893384
EXP_MIN = -745.1332191019411
ATANH_TERMS = 13
EXP_TERMS = 17
MANTISSA = numpy.int64(0x000FFFFFFFFFFFFF)
ONE_BITS = numpy.int64(0x3FF0000000000000)


def atanh_coefficients():
    return [1.0 / float(2 * index + 1) for index in range(ATANH_TERMS)]


def exp_coefficients():
    found = [1.0]
    for index in range(1, EXP_TERMS):
        found.append(found[-1] / float(index))
    return found


def ln(values):
    x = numpy.asarray(values, dtype=numpy.float64)
    with numpy.errstate(all="ignore"):
        tiny = x < numpy.finfo(numpy.float64).tiny
        value = numpy.where(tiny, x * TWO_54, x)
        exponent = numpy.where(tiny, -54, 0).astype(numpy.int64)
        bits = value.view(numpy.int64)
        exponent = exponent + ((bits >> 52) & 0x7FF) - 1023
        fraction = ((bits & MANTISSA) | ONE_BITS).view(numpy.float64)
        large = fraction >= 2.0 * SQRT_HALF
        fraction = numpy.where(large, fraction * 0.5, fraction)
        exponent = exponent + large
        s = (fraction - 1.0) / (fraction + 1.0)
        square = s * s
        coefficients = atanh_coefficients()
        series = numpy.full(x.shape, coefficients[-1])
        for coefficient in reversed(coefficients[:-1]):
            series = series * square + coefficient
        k = exponent.astype(numpy.float64)
        found = k * LN2_HI + (k * LN2_LO + 2.0 * s * series)
        found = numpy.where(x == 0.0, -numpy.inf, found)
        found = numpy.where(x == numpy.inf, numpy.inf, found)
        return numpy.where(numpy.isnan(x) | (x < 0.0), numpy.nan, found)


def power_of_two(exponent):
    return ((exponent + 1023).astype(numpy.int64) << 52).view(numpy.float64)


def scale(value, exponent):
    high = exponent > 1023
    low = exponent < -1022
    middle = numpy.clip(exponent, -1022, 1023)
    found = value * power_of_two(middle)
    found = numpy.where(high, value * power_of_two(numpy.full(exponent.shape, 1023)) * power_of_two(numpy.clip(exponent - 1023, -1022, 1023)), found)
    return numpy.where(low, value * power_of_two(numpy.clip(exponent + 1022, -1022, 1023)) * power_of_two(numpy.full(exponent.shape, -1022)), found)


def exp(values):
    x = numpy.asarray(values, dtype=numpy.float64)
    with numpy.errstate(all="ignore"):
        safe = numpy.where(numpy.isfinite(x), numpy.clip(x, EXP_MIN, EXP_MAX), 0.0)
        k = numpy.floor(safe * INV_LN2 + 0.5)
        r = (safe - k * LN2_HI) - k * LN2_LO
        coefficients = exp_coefficients()
        series = numpy.full(x.shape, coefficients[-1])
        for coefficient in reversed(coefficients[:-1]):
            series = series * r + coefficient
        found = scale(series, k.astype(numpy.int64))
        found = numpy.where(x > EXP_MAX, numpy.inf, found)
        found = numpy.where(x < EXP_MIN, 0.0, found)
        return numpy.where(numpy.isnan(x), x, found)


def pow(base, exponent):
    x = numpy.asarray(base, dtype=numpy.float64)
    y = float(exponent)
    with numpy.errstate(all="ignore"):
        if y == 1.0:
            return x.copy()
        if y == 0.0:
            return numpy.ones_like(x)
        if y == 2.0:
            found = x * x
        elif y == 0.5:
            found = numpy.sqrt(x)
        elif y == 1.5:
            found = x * numpy.sqrt(x)
        elif y == -1.0:
            found = 1.0 / x
        else:
            found = exp(y * ln(x))
            found = numpy.where(x == 0.0, 0.0 if y > 0.0 else numpy.inf, found)
            found = numpy.where(x == 1.0, 1.0, found)
            found = numpy.where(x == numpy.inf, numpy.inf if y > 0.0 else 0.0, found)
        return numpy.where(numpy.isnan(x) | (x < 0.0), numpy.nan, found)
