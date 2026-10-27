import numpy

BACKGROUND_PERCENTILE = 80
DARKEST_PERCENTILE = 1
CORE = 0.5
EDGE = 0.15


def vein_depth(values):
    background = numpy.percentile(values, BACKGROUND_PERCENTILE)
    darkest = numpy.percentile(values, DARKEST_PERCENTILE)
    return numpy.clip((background - values) / max(background - darkest, 1e-6), 0.0, 1.0)


def runs(mask):
    lengths = numpy.zeros(mask.shape)
    for row_index, row in enumerate(mask):
        start = None
        for column, value in enumerate(list(row) + [False]):
            if value and start is None:
                start = column
            elif not value and start is not None:
                lengths[row_index, start:column] = column - start
                start = None
    return lengths


def vein_widths(core, pixel):
    across = numpy.minimum(runs(core), runs(core.T).T)
    return across[core] * pixel


def vein_profile(values, pixel):
    depth = vein_depth(values)
    core = depth >= CORE
    edge = (depth > EDGE) & ~core
    widths = vein_widths(core, pixel)
    if widths.size == 0:
        return {"core_share": 0.0, "softness": 0.0, "width_p10": 0.0, "width_p50": 0.0, "width_p90": 0.0}
    return {
        "core_share": float(core.mean()),
        "softness": float(edge.sum() / core.sum()),
        "width_p10": float(numpy.percentile(widths, 10)),
        "width_p50": float(numpy.percentile(widths, 50)),
        "width_p90": float(numpy.percentile(widths, 90)),
    }
