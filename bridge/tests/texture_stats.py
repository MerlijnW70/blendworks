import bpy
import numpy

BLOCK = 24
GRADIENT_FLOOR = 0.004


def luminance(image_name, size):
    pixels = numpy.array(bpy.data.images[image_name].pixels[:], dtype=numpy.float64).reshape(size, size, 4)
    return 0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1] + 0.0722 * pixels[..., 2]


def smoothed(values):
    kernel = numpy.array([1.0, 2.0, 1.0]) / 4.0
    rows = numpy.apply_along_axis(lambda row: numpy.convolve(row, kernel, "same"), 1, values)
    return numpy.apply_along_axis(lambda column: numpy.convolve(column, kernel, "same"), 0, rows)


def gradient_share(values, floor=GRADIENT_FLOOR):
    gradient_y, gradient_x = numpy.gradient(smoothed(values))
    return float((numpy.hypot(gradient_x, gradient_y) > floor).mean())


def vein_statistics(values):
    gradient_y, gradient_x = numpy.gradient(smoothed(values))
    energy = gradient_x ** 2 + gradient_y ** 2
    strong = energy > GRADIENT_FLOOR ** 2
    angle = numpy.arctan2(gradient_y, gradient_x)[strong]
    weight = energy[strong]
    doubled = numpy.hypot((weight * numpy.cos(2 * angle)).sum(), (weight * numpy.sin(2 * angle)).sum())
    size = values.shape[0] // BLOCK * BLOCK

    def blocks(field):
        return field[:size, :size].reshape(size // BLOCK, BLOCK, size // BLOCK, BLOCK).sum(axis=(1, 3))

    xx, yy, xy = blocks(gradient_x ** 2), blocks(gradient_y ** 2), blocks(gradient_x * gradient_y)
    total = xx + yy
    local = numpy.sqrt((xx - yy) ** 2 + 4 * xy ** 2) / numpy.maximum(total, 1e-12)
    return {
        "orientation": float(doubled / weight.sum()),
        "elongation": float((local * total).sum() / total.sum()),
        "contrast": float(numpy.median(values) - numpy.percentile(values, 2)),
        "dark_share": float((values < numpy.median(values) - 0.12).mean()),
    }
