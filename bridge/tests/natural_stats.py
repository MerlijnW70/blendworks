import bpy
import numpy

BOUNDARY_STEP = 0.02
HARD_RATIO = 0.7
WINDOW = 3


def baked_pixels(name, size):
    values = numpy.array(bpy.data.images[name].pixels[:], dtype=numpy.float64).reshape(size, size, 4)
    return values[..., :3]


def luminance_of(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def variation(values):
    return float(values.std() / values.mean())


def to_linear(encoded):
    encoded = numpy.asarray(encoded, dtype=numpy.float64)
    return numpy.where(encoded <= 0.04045, encoded / 12.92, ((encoded + 0.055) / 1.055) ** 2.4)


def hard_edge_share(values):
    reach = WINDOW
    wide = numpy.abs(values[:, 2 * reach :] - values[:, : -2 * reach])
    single = numpy.abs(numpy.diff(values, axis=1))
    steps = numpy.stack([single[:, shift : shift + wide.shape[1]] for shift in range(2 * reach)])
    sharpest = steps.max(axis=0)
    boundary = wide > BOUNDARY_STEP
    if not boundary.any():
        return 0.0, 0
    return float((sharpest[boundary] >= HARD_RATIO * wide[boundary]).mean()), int(boundary.sum())
