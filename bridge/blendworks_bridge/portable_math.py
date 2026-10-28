import numpy

PI = 3.14159265358979311600e00
HALF_PI_HIGH = 1.57079632679489655800e00
HALF_PI_LOW = 6.12323399573676603587e-17
P = (1.66666666666666657415e-01, -3.25565818622400915405e-01, 2.01212532134862925881e-01, -4.00555345006794114027e-02, 7.91534994289814532176e-04, 3.47933107596021167570e-05)
Q = (-2.40339491173441421878e00, 2.02094576023350569471e00, -6.88283971605453293030e-01, 7.70381505559019352791e-02)
HIGH_WORD = numpy.uint64(0xFFFFFFFF00000000)


def ratio(z):
    p = z * (P[0] + z * (P[1] + z * (P[2] + z * (P[3] + z * (P[4] + z * P[5])))))
    q = 1.0 + z * (Q[0] + z * (Q[1] + z * (Q[2] + z * Q[3])))
    return p / q


def acos(values):
    x = numpy.asarray(values, dtype=numpy.float64)
    size = numpy.abs(x)
    result = numpy.full(x.shape, numpy.nan)
    middle = size < 0.5
    xm = x[middle]
    result[middle] = HALF_PI_HIGH - (xm - (HALF_PI_LOW - xm * ratio(xm * xm)))
    low = (x <= -0.5) & (x > -1.0)
    zl = (1.0 + x[low]) * 0.5
    sl = numpy.sqrt(zl)
    result[low] = PI - 2.0 * (sl + (ratio(zl) * sl - HALF_PI_LOW))
    high = (x >= 0.5) & (x < 1.0)
    zh = (1.0 - x[high]) * 0.5
    sh = numpy.sqrt(zh)
    trimmed = (sh.view(numpy.uint64) & HIGH_WORD).view(numpy.float64)
    correction = (zh - trimmed * trimmed) / (sh + trimmed)
    result[high] = 2.0 * (trimmed + (ratio(zh) * sh + correction))
    result[x == 1.0] = 0.0
    result[x == -1.0] = PI
    return result
