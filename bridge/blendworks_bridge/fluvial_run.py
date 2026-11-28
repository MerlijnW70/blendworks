"""A fluvial terrain run from settings to grids, rivers and lakes."""

import time

import numpy

from . import fluvial_fields, fluvial_measure, fluvial_model, fluvial_spinup
from . import terrain_kernels as kernels

NETWORK_AREA = 1e6
"""Strahler orders and Hack's law are counted on channels that drain at least this much: channel heads lie at
0.1-1 km^2 (Montgomery & Dietrich 1988), so 1 km^2 keeps every counted cell on a channel. They are counted on
the tree of each cell's main D-infinity receiver (the one taking the larger share), the graph the incision follows."""
INITIAL_SLOPE = 5e-4
INITIAL_RELIEF = 2.0
INITIAL_WAVES = 30.0
RIVER_COUNT = 4
RIVER_POINTS = 200
LEAST_LAKE_CELLS = 16

DEFAULTS = {
    "uplift_shape": "block", "crest": 1.0, "behind": 1.0, "along": 0.0, "margin_share": 0.0, "axis_angle": 0.0,
    "base_level": ["south"], "area_exponent": 0.45, "slope_exponent": 1.0, "diffusivity": 0.01,
    "critical_slope": None, "threshold_slope": None, "channel_area": 1e5, "carve": True, "flow": "dinf",
    "lithology": None, "uplift_values": None, "seed": 0, "initial_slope": INITIAL_SLOPE, "initial_relief": INITIAL_RELIEF, "initial_waves": INITIAL_WAVES,
    "weak_belts": None, "threshold_angles": None, "head_slope": 0.6, "head_exponent": 2.0,
    "threads": 4,
}


def settings_of(given):
    settings = dict(DEFAULTS)
    settings.update({key: value for key, value in given.items() if value is not None})
    for key in ("uplift_rate", "erodibility"):
        if key not in settings:
            raise ValueError(f"the run needs {key}")
    return settings


def belts_of(settings, side, cell, edges):
    belts = settings["weak_belts"]
    if not belts:
        return None
    return fluvial_fields.weak_belts((side, side), (cell, cell), edges, belts["shares"], belts["width_share"], belts.get("wander", 0.0), settings["seed"])


def erodibility_field(settings, side, cell, weak=None):
    lithology, erodibility = settings["lithology"], settings["erodibility"]
    shape, spacing = (side, side), (cell, cell)
    if lithology:
        erodibility = fluvial_fields.lithology_bands(shape, spacing, erodibility, lithology["factors"],
                                                     lithology["band_share"] * side * cell, lithology.get("angle", 0.0))
    if weak is not None:
        erodibility = numpy.where(weak, erodibility * settings["weak_belts"]["factor"], erodibility)
    return erodibility


def threshold_maker(settings, side, cell, weak=None):
    """With threshold_angles [low, high] in degrees, a function (shape, step) giving each step its own critical
    tangents: seeded multi-scale noise down to two cells, drawn afresh every step, so slopes cut back to the threshold
    are not one plane but a rough face of crags and chutes. Weak rock takes the lower half of the range."""
    angles = settings["threshold_angles"]
    if not angles:
        return None
    extent = (side - 1) * cell

    def tangent_of(shape, index):
        spacing = extent / (shape[0] - 1)
        level_weak = None if weak is None else fluvial_fields.resample(weak.astype(numpy.float64), shape) > 0.5
        field = fluvial_fields.critical_angles(shape, (spacing, spacing), angles[0], angles[1], settings["seed"] + 7919 * (index + 1),
                                               level_weak, shortest=2.0 * spacing)
        return numpy.tan(numpy.radians(field))
    return tangent_of


def uplift_maker(settings, edges, extent):
    def uplift_of(shape, spacing):
        margin = settings["margin_share"] * extent if settings["margin_share"] else None
        return fluvial_fields.uplift_field(shape, spacing, settings["uplift_rate"], settings["uplift_shape"],
                                           axis_angle=settings["axis_angle"], margin=margin, values=settings["uplift_values"],
                                           edges=edges, crest=settings["crest"], behind=settings["behind"],
                                           along=settings["along"], seed=settings["seed"])
    return uplift_of


def law_of(settings, edges, erodibility, threshold_of=None):
    return fluvial_model.Law(erodibility=erodibility, area_exponent=settings["area_exponent"], slope_exponent=settings["slope_exponent"],
                             diffusivity=settings["diffusivity"], critical_slope=settings["critical_slope"], carve=settings["carve"],
                             edges=edges, threads=settings["threads"], channel_area=settings["channel_area"],
                             threshold_slope=settings["threshold_slope"], threshold_of=threshold_of, flow=settings["flow"],
                             head_slope=settings["head_slope"], head_exponent=settings["head_exponent"])


def trace_river(outlet, area, ordering, least):
    """Cells of the river ending at outlet, followed upstream through the donor with the largest area."""
    path = [outlet]
    current = outlet
    while True:
        start, end = ordering.donor_start[current], ordering.donor_start[current + 1]
        if start == end:
            break
        donors = ordering.donors[start:end]
        best = int(donors[numpy.argmax(area[donors])])
        if area[best] < least:
            break
        path.append(best)
        current = best
    return path[::-1]


def rivers(heights, area, ordering, receivers, cell, least, count=RIVER_COUNT):
    """The largest rivers as world points [x, y, z] from source to mouth, at most RIVER_POINTS each."""
    flat_area = area.ravel()
    mouths = numpy.flatnonzero(receivers < 0)
    mouths = mouths[numpy.argsort(-flat_area[mouths])][:count]
    found = []
    columns = heights.shape[1]
    for mouth in mouths:
        if flat_area[mouth] < least:
            continue
        cells = numpy.array(trace_river(int(mouth), flat_area, ordering, least))
        stride = max(1, len(cells) // RIVER_POINTS + 1)
        cells = numpy.append(cells[::stride], cells[-1]) if cells[-1] != cells[::stride][-1] else cells[::stride]
        points = numpy.stack([(cells % columns) * cell, (cells // columns) * cell, heights.ravel()[cells]], axis=1)
        found.append({"points": points.round(3).tolist(), "area_km2": round(float(flat_area[mouth]) / 1e6, 3)})
    return found


def lakes(heights, water, lake, cell):
    """Lakes of at least LEAST_LAKE_CELLS flooded cells: level, centre, area and largest depth."""
    depth = numpy.maximum(water - heights, 0.0)
    found = []
    labels, counts = numpy.unique(lake[lake > 0], return_counts=True)
    for label, cells in zip(labels, counts):
        if cells < LEAST_LAKE_CELLS:
            continue
        rows, columns = numpy.nonzero(lake == label)
        found.append({"level": round(float(water[rows[0], columns[0]]), 3), "centre": [round(float(columns.mean() * cell), 3), round(float(rows.mean() * cell), 3)],
                      "area_km2": round(float(cells) * cell * cell / 1e6, 4), "depth": round(float(depth[rows, columns].max()), 3)})
    return found


def run(settings, side, cell, schedule=None):
    """Spins up a side x side grid of cell metres and returns the output grids, rivers, lakes and measures."""
    started = time.perf_counter()
    settings = settings_of(settings)
    edges = fluvial_model.edge_mask(settings["base_level"])
    extent = (side - 1) * cell
    weak = belts_of(settings, side, cell, edges)
    law = law_of(settings, edges, erodibility_field(settings, side, cell, weak), threshold_maker(settings, side, cell, weak))
    schedule = schedule or fluvial_spinup.default_schedule(side)
    spun = fluvial_spinup.spin_up(side, cell, uplift_maker(settings, edges, extent), law, schedule, seed=settings["seed"],
                                  initial_relief=settings["initial_relief"], initial_slope=settings["initial_slope"],
                                  initial_waves=settings["initial_waves"])
    seconds = time.perf_counter() - started
    heights, outlets = spun.heights, fluvial_model.outlet_cells(spun.heights.shape, edges)
    spacing = (cell, cell)
    final_law = law_of(settings, edges, 0.0)
    routed_lakes, _, _ = fluvial_model.route(heights, spacing, final_law)
    table, shares, _, area = fluvial_model.spread_flow(heights, spacing, final_law)
    area = numpy.asarray(area).reshape(heights.shape)
    receivers = fluvial_measure.dominant_receivers(table, shares)
    tree = kernels.order(receivers, heights.shape, 1, settings["threads"], "core")
    water = numpy.asarray(routed_lakes.water, dtype=numpy.float64).reshape(heights.shape)
    channel = fluvial_model.channel_mask(final_law, heights, spacing, area) & ~outlets
    measured = fluvial_measure.measure(heights, spacing, receivers, tree, area, outlets, NETWORK_AREA)
    measured["undrained_pits"] = fluvial_measure.undrained_pits(routed_lakes.receivers, outlets, heights.shape)
    measured.update(fluvial_measure.hillslope_metrics(tree, receivers, channel, spacing, heights.shape, outlets))
    grids = {
        "height": heights, "drainage_area": area, "receivers": receivers.reshape(heights.shape),
        "channel": channel, "strahler": measured["strahler"],
        "lake_depth": numpy.maximum(water - heights, 0.0), "erosion": spun.eroded,
    }
    summary = {key: value for key, value in measured.items() if not isinstance(value, numpy.ndarray)}
    summary.update({"seconds": round(seconds, 2), "years": round(spun.years), "network_area_m2": NETWORK_AREA,
                    "levels": [{"side": r.side, "cell": round(r.spacing, 3), "steps": r.steps, "years": round(r.years), "dt": [round(v) for v in r.dt],
                                "change": round(r.change, 4), "steady": r.steady, "seconds": round(r.seconds, 2)} for r in spun.levels]})
    return {"grids": grids, "summary": summary, "rivers": rivers(heights, area, tree, receivers, cell, NETWORK_AREA),
            "lakes": lakes(heights, water, numpy.asarray(routed_lakes.lake).reshape(heights.shape), cell), "settings": settings}
