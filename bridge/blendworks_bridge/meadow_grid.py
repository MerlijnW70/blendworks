"""Height grid and terrain measures for meadow fields.

A regular height grid over the ground meshes, in world metres, and the terrain measures the meadow fields are built
from: slope, curvature, height relative to the surroundings and the upslope area that drains through each cell."""
import math

import numpy

GRID_CELLS = 512
SMALLEST_CELL = 0.5
FILL_PASSES = 256
FLOW_EXPONENT = 1.1
NEIGHBOURS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


class Grid:
    """Cell (row, column) has its centre at low + (column + 0.5, row + 0.5) * cell."""

    def __init__(self, low, high, cells=GRID_CELLS, smallest=SMALLEST_CELL):
        span = numpy.maximum(numpy.asarray(high, dtype=float) - numpy.asarray(low, dtype=float), smallest)
        self.cell = max(float(span.max()) / cells, smallest)
        self.low = numpy.asarray(low, dtype=float)
        self.columns = int(math.ceil(span[0] / self.cell)) + 1
        self.rows = int(math.ceil(span[1] / self.cell)) + 1
        self.heights = None

    @property
    def shape(self):
        return self.rows, self.columns

    def centres(self):
        xs = self.low[0] + (numpy.arange(self.columns) + 0.5) * self.cell
        ys = self.low[1] + (numpy.arange(self.rows) + 0.5) * self.cell
        return numpy.meshgrid(xs, ys)

    def index_of(self, xy):
        column = numpy.clip(((xy[:, 0] - self.low[0]) / self.cell).astype(int), 0, self.columns - 1)
        row = numpy.clip(((xy[:, 1] - self.low[1]) / self.cell).astype(int), 0, self.rows - 1)
        return row, column

    def sample(self, values, xy):
        """Bilinear value of a grid field at world points (n, 2 or 3)."""
        u = numpy.clip((xy[:, 0] - self.low[0]) / self.cell - 0.5, 0.0, self.columns - 1.0)
        v = numpy.clip((xy[:, 1] - self.low[1]) / self.cell - 0.5, 0.0, self.rows - 1.0)
        c0 = numpy.minimum(numpy.floor(u).astype(int), self.columns - 2) if self.columns > 1 else numpy.zeros(len(u), dtype=int)
        r0 = numpy.minimum(numpy.floor(v).astype(int), self.rows - 2) if self.rows > 1 else numpy.zeros(len(v), dtype=int)
        c1 = numpy.minimum(c0 + 1, self.columns - 1)
        r1 = numpy.minimum(r0 + 1, self.rows - 1)
        fu, fv = u - c0, v - r0
        top = values[r0, c0] * (1.0 - fu) + values[r0, c1] * fu
        bottom = values[r1, c0] * (1.0 - fu) + values[r1, c1] * fu
        return top * (1.0 - fv) + bottom * fv


def filled(values, known):
    """Unknown cells take the mean of their known neighbours, pass by pass; any left take the mean of all."""
    values = numpy.where(known, values, 0.0)
    known = known.copy()
    for _ in range(FILL_PASSES):
        if known.all():
            break
        padded = numpy.pad(values * known, 1)
        weights = numpy.pad(known.astype(float), 1)
        total = numpy.zeros_like(values)
        count = numpy.zeros_like(values)
        for dr, dc in NEIGHBOURS:
            total += padded[1 + dr:1 + dr + values.shape[0], 1 + dc:1 + dc + values.shape[1]]
            count += weights[1 + dr:1 + dr + values.shape[0], 1 + dc:1 + dc + values.shape[1]]
        grow = (~known) & (count > 0)
        values = numpy.where(grow, total / numpy.maximum(count, 1.0), values)
        known = known | grow
    if not known.all():
        values = numpy.where(known, values, values[known].mean() if known.any() else 0.0)
    return values


def raster_mean(grid, points, values):
    """Mean of values over the points falling in each cell, and which cells received any."""
    row, column = grid.index_of(points)
    flat = row * grid.columns + column
    size = grid.rows * grid.columns
    total = numpy.bincount(flat, weights=values, minlength=size)
    count = numpy.bincount(flat, minlength=size)
    known = count > 0
    mean = numpy.divide(total, count, out=numpy.zeros(size), where=known)
    return mean.reshape(grid.shape), known.reshape(grid.shape)


def height_grid(points, cells=GRID_CELLS, smallest=SMALLEST_CELL):
    """A grid over the points' footprint with the mean point height in each cell, gaps filled from their neighbours."""
    grid = Grid(points[:, :2].min(axis=0), points[:, :2].max(axis=0), cells, smallest)
    mean, known = raster_mean(grid, points, points[:, 2])
    grid.heights = filled(mean, known)
    return grid


def gaussian(values, sigma_cells):
    """Separable Gaussian blur with mirrored edges; sigma in cells."""
    if sigma_cells < 0.3:
        return values.copy()
    reach = int(math.ceil(3.0 * sigma_cells))
    offsets = numpy.arange(-reach, reach + 1)
    kernel = numpy.exp(-0.5 * (offsets / sigma_cells) ** 2)
    kernel /= kernel.sum()
    result = values
    for axis in (0, 1):
        width = result.shape[axis]
        padded = numpy.pad(result, [(reach, reach) if index == axis else (0, 0) for index in (0, 1)], mode="reflect" if width > reach else "edge")
        total = numpy.zeros_like(result)
        for offset, weight in zip(offsets, kernel):
            start = reach + offset
            total += weight * (padded[start:start + width, :] if axis == 0 else padded[:, start:start + width])
        result = total
    return result


def slope_tangent(grid):
    """Tangent of the steepest slope of each cell."""
    dy, dx = numpy.gradient(grid.heights, grid.cell)
    return numpy.hypot(dx, dy)


def curvature(grid, smoothing):
    """Laplacian of the heights smoothed over smoothing metres, per metre: positive in hollows, negative on crests."""
    smooth = gaussian(grid.heights, smoothing / grid.cell)
    padded = numpy.pad(smooth, 1, mode="edge")
    laplace = padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:] - 4.0 * smooth
    return laplace / (grid.cell * grid.cell)


def relative_height(grid, radius):
    """Height above the Gaussian mean of the surroundings within about radius metres (topographic position)."""
    return grid.heights - gaussian(grid.heights, 0.5 * radius / grid.cell)


def upslope_area(grid):
    """Specific catchment area in metres: the area that drains through each cell per metre of contour, routed downhill to
    every lower neighbour in proportion to slope to the power 1.1 (multiple flow direction)."""
    heights = grid.heights
    rows, columns = heights.shape
    padded = numpy.pad(heights, 1, mode="edge")
    drops, targets = [], []
    index = numpy.arange(rows * columns).reshape(rows, columns)
    padded_index = numpy.pad(index, 1, mode="edge")
    for dr, dc in NEIGHBOURS:
        distance = grid.cell * math.hypot(dr, dc)
        neighbour = padded[1 + dr:1 + dr + rows, 1 + dc:1 + dc + columns]
        drops.append(numpy.maximum((heights - neighbour) / distance, 0.0) ** FLOW_EXPONENT * (padded_index[1 + dr:1 + dr + rows, 1 + dc:1 + dc + columns] != index))
        targets.append(padded_index[1 + dr:1 + dr + rows, 1 + dc:1 + dc + columns])
    drops = numpy.stack(drops, axis=-1).reshape(-1, 8)
    targets = numpy.stack(targets, axis=-1).reshape(-1, 8)
    total = drops.sum(axis=1)
    shares = numpy.divide(drops, total[:, None], out=numpy.zeros_like(drops), where=total[:, None] > 0)
    order = numpy.argsort(-heights.ravel(), kind="stable")
    area = [grid.cell * grid.cell] * (rows * columns)
    share_rows = shares.tolist()
    target_rows = targets.tolist()
    for cell in order.tolist():
        amount = area[cell]
        for share, target in zip(share_rows[cell], target_rows[cell]):
            if share > 0.0:
                area[target] += amount * share
    return numpy.array(area).reshape(rows, columns) / grid.cell


def wetness_index(grid, smallest_slope):
    """Topographic wetness index ln(a / tan b) of Beven and Kirkby (1979)."""
    return numpy.log(upslope_area(grid) / numpy.maximum(slope_tangent(grid), smallest_slope))
