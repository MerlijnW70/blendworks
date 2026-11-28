"""Measures of a fluvial surface: Strahler, Hack, pits, aspect."""

import math

import numpy

HACK_BINS = 24
LEAST_HACK_POINTS = 6
STEEP_ENOUGH = 0.05


def level_donors(ordering, cells):
    """The donors of cells, concatenated, and for each cell where its donors start in that list."""
    start = ordering.donor_start[cells].astype(numpy.int64)
    count = ordering.donor_start[cells + 1].astype(numpy.int64) - start
    offsets = numpy.concatenate(([0], numpy.cumsum(count)))
    owner = numpy.repeat(numpy.arange(cells.size), count)
    index = start[owner] + numpy.arange(offsets[-1]) - offsets[owner]
    return ordering.donors[index].astype(numpy.int64), owner, offsets


def strahler(ordering, channel):
    """Strahler order of every channel cell (0 off the channels): 1 at a channel head; where two or more donors
    share the highest order k the cell takes k + 1, otherwise k. Cells are visited level by level from the far
    end of the queue, so every donor is done before its receiver."""
    flat = channel.ravel()
    order = numpy.zeros(flat.size, dtype=numpy.int32)
    for index in range(ordering.levels - 1, -1, -1):
        cells = ordering.level(index).astype(numpy.int64)
        cells = cells[flat[cells]]
        if cells.size == 0:
            continue
        donors, owner, _ = level_donors(ordering, cells)
        donor_order = order[donors]
        top = numpy.zeros(cells.size, dtype=numpy.int32)
        numpy.maximum.at(top, owner, donor_order)
        ties = numpy.zeros(cells.size, dtype=numpy.int32)
        numpy.add.at(ties, owner, (donor_order == top[owner]) & (donor_order > 0))
        order[cells] = numpy.where(top == 0, 1, numpy.where(ties >= 2, top + 1, top))
    return order.reshape(channel.shape)


def flow_lengths(receivers, spacing, shape):
    """Distance from every cell to its receiver (0 at the roots)."""
    rows, columns = shape
    cells = numpy.arange(rows * columns)
    target = numpy.where(receivers >= 0, receivers, cells)
    dx = (target % columns - cells % columns) * spacing[0]
    dy = (target // columns - cells // columns) * spacing[1]
    return numpy.hypot(dx, dy)


def longest_path(ordering, receivers, spacing, shape):
    """Length of the longest flow path from a divide to each cell's centre."""
    step = flow_lengths(receivers, spacing, shape)
    longest = numpy.zeros(step.size)
    for index in range(ordering.levels - 1, -1, -1):
        cells = ordering.level(index).astype(numpy.int64)
        donors, owner, _ = level_donors(ordering, cells)
        if donors.size == 0:
            continue
        reach = numpy.zeros(cells.size)
        numpy.maximum.at(reach, owner, longest[donors] + step[donors])
        longest[cells] = reach
    return longest.reshape(shape)


def hack_fit(area, length, channel, threshold):
    """Hack's exponent h of L ~ A^h (Hack 1957) over the channel cells with at least twice the channel area:
    the median stream length in each of HACK_BINS logarithmic area bins, fitted by least squares in log-log.
    Returns h and the orders of magnitude of area it spans."""
    chosen = channel & (area >= 2.0 * threshold) & (length > 0.0)
    if chosen.sum() < LEAST_HACK_POINTS:
        return math.nan, 0.0
    log_area, log_length = numpy.log10(area[chosen]), numpy.log10(length[chosen])
    edges = numpy.linspace(log_area.min(), log_area.max(), HACK_BINS + 1)
    which = numpy.clip(numpy.digitize(log_area, edges) - 1, 0, HACK_BINS - 1)
    centres, medians = [], []
    for index in range(HACK_BINS):
        inside = which == index
        if inside.sum() >= 3:
            centres.append(float(numpy.median(log_area[inside])))
            medians.append(float(numpy.median(log_length[inside])))
    if len(centres) < LEAST_HACK_POINTS:
        return math.nan, float(log_area.max() - log_area.min())
    return float(numpy.polyfit(centres, medians, 1)[0]), float(log_area.max() - log_area.min())


def undrained_pits(receivers, outlets, shape):
    """Cells other than the base level that drain nowhere after lake routing."""
    roots = (numpy.asarray(receivers).reshape(shape) < 0) & ~outlets
    return int(roots.sum())


def aspect_shares(heights, spacing, steep=STEEP_ENOUGH):
    """Of the cells steeper than steep, the share whose downslope direction points into the eastern half
    (+x) and the share pointing into the northern half (+y)."""
    rise_y, rise_x = numpy.gradient(heights, spacing[1], spacing[0])
    slope = numpy.hypot(rise_x, rise_y)
    chosen = slope > steep
    if not chosen.any():
        return math.nan, math.nan
    east = float((-rise_x[chosen] > 0.0).mean())
    north = float((-rise_y[chosen] > 0.0).mean())
    return east, north


GRID_BAND = 2.0
RELIEF_WINDOW = 10_000.0


def local_relief(heights, spacing, window=RELIEF_WINDOW):
    """Median of the height range (crest to valley floor) over square windows window metres wide, the measure
    Montgomery & Brandon 2002 use for local relief."""
    cells = max(2, int(round(window / spacing[0])))
    rows, columns = heights.shape[0] // cells, heights.shape[1] // cells
    if rows == 0 or columns == 0:
        return float(numpy.ptp(heights))
    blocks = heights[: rows * cells, : columns * cells].reshape(rows, cells, columns, cells)
    return float(numpy.median(blocks.max(axis=(1, 3)) - blocks.min(axis=(1, 3))))


def grid_bias(heights, spacing, steep=STEEP_ENOUGH, band=GRID_BAND):
    """How much the surface follows the grid: for each grid direction (0, 45, 90 and 135 degrees, either sense) the
    gradient energy (slope squared, cells steeper than steep) per degree within band degrees of it, over the energy
    per degree from 2 band to 6 band degrees away; the largest of the four ratios. A surface without grid bias gives
    about 1 whatever its regional grain; ridges, channels and planes along the grid make a spike and raise it."""
    rise_y, rise_x = numpy.gradient(heights, spacing[1], spacing[0])
    energy = rise_x * rise_x + rise_y * rise_y
    chosen = energy > steep * steep
    if not chosen.any():
        return math.nan
    angle = numpy.degrees(numpy.arctan2(-rise_y[chosen], -rise_x[chosen])) % 180.0
    weights = energy[chosen]
    worst = 0.0
    for direction in (0.0, 45.0, 90.0, 135.0):
        offset = numpy.abs((angle - direction + 90.0) % 180.0 - 90.0)
        near = weights[offset <= band].sum() / (2.0 * band)
        around = weights[(offset >= 2.0 * band) & (offset <= 6.0 * band)].sum() / (8.0 * band)
        if around > 0.0:
            worst = max(worst, near / around)
    return float(worst)

def dominant_receivers(table, shares, width=8):
    """Each cell's main receiver in a table of several: the one taking the larger share (the first on a tie), -1
    where the cell has none. Its tree carries the Strahler orders, flow paths and rivers."""
    table = numpy.asarray(table).reshape(-1, width)
    shares = numpy.asarray(shares).reshape(-1, width)
    best = numpy.argmax(numpy.where(table >= 0, shares, -1.0), axis=1)
    chosen = table[numpy.arange(table.shape[0]), best]
    return numpy.where(shares[numpy.arange(table.shape[0]), best] > 0.0, chosen, -1).astype(numpy.int32)


def hillslope_metrics(ordering, receivers, channel, spacing, shape, outlets):
    """Drainage density (channel length per land area, km/km^2) and hillslope length: the flow distance from each
    ridge cell (a hillslope cell nothing drains into) down to the first channel cell, median over the ridge cells."""
    step = flow_lengths(receivers, spacing, shape)
    flat_channel = channel.ravel()
    land = ~outlets.ravel()
    density = float(step[flat_channel].sum()) / 1000.0 / max(float(land.sum()) * spacing[0] * spacing[1] / 1e6, 1e-12)
    to_channel = numpy.zeros(step.size)
    for index in range(ordering.levels):
        cells = ordering.level(index)
        targets = receivers[cells]
        moving = (targets >= 0) & ~flat_channel[cells]
        to_channel[cells[moving]] = to_channel[targets[moving]] + step[cells[moving]]
    has_donor = numpy.zeros(step.size, dtype=bool)
    has_donor[receivers[receivers >= 0]] = True
    ridges = ~has_donor & ~flat_channel & land & (to_channel > 0.0)
    length = float(numpy.median(to_channel[ridges])) if ridges.any() else math.nan
    return {"drainage_density": density, "hillslope_length": length}


def measure(heights, spacing, receivers, ordering, area, outlets, threshold):
    """Every measure of a routed surface; threshold is the channel area in m^2."""
    channel = (area >= threshold) & ~outlets
    order = strahler(ordering, channel)
    length = longest_path(ordering, receivers, spacing, heights.shape)
    hack, decades = hack_fit(area, length, channel, threshold)
    east, north = aspect_shares(heights, spacing)
    return {
        "channel": channel,
        "strahler": order,
        "longest_path": length,
        "trunk_order": int(order.max()),
        "hack_exponent": hack,
        "hack_decades": decades,
        "undrained_pits": undrained_pits(receivers, outlets, heights.shape),
        "aspect_east_share": east,
        "aspect_north_share": north,
        "relief": float(numpy.ptp(heights)),
        "grid_bias": grid_bias(heights, spacing),
        "local_relief": local_relief(heights, spacing),
    }
