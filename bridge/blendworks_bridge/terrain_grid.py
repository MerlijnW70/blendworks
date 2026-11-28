"""Grid description shared by the terrain kernels: shape, spacing, outlet edges and cell status."""

import math

import numpy

NEIGHBOURS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))
OPPOSITE = (4, 5, 6, 7, 0, 1, 2, 3)
EDGE_NORTH = 1
EDGE_EAST = 2
EDGE_SOUTH = 4
EDGE_WEST = 8
EDGE_NODATA = 16
EDGE_ALL = 31
NODATA = 0
INTERIOR = 1
OUTLET = 2
MAX_CELLS = 2**31 - 1


class TerrainGrid:
    def __init__(self, rows, columns, spacing=(1.0, 1.0), edges=EDGE_ALL):
        self.rows = int(rows)
        self.columns = int(columns)
        self.spacing_x = float(spacing[0])
        self.spacing_y = float(spacing[1])
        self.edges = int(edges)
        if self.rows < 1 or self.columns < 1:
            raise ValueError(f"the grid needs at least one row and one column, got {self.rows} x {self.columns}")
        if self.rows * self.columns > MAX_CELLS:
            raise ValueError(f"a grid of {self.rows} x {self.columns} cells is larger than the {MAX_CELLS} cells the kernels index")
        for name, value in (("spacing x", self.spacing_x), ("spacing y", self.spacing_y)):
            if not (math.isfinite(value) and value > 0.0):
                raise ValueError(f"{name} must be a finite number above 0, got {value}")
        if not 0 <= self.edges <= EDGE_ALL:
            raise ValueError(f"edges must be a mask of the bits 1 north, 2 east, 4 south, 8 west and 16 no-data, got {self.edges}")

    @classmethod
    def of(cls, heights, spacing=(1.0, 1.0), edges=EDGE_ALL):
        shape = numpy.shape(heights)
        if len(shape) != 2:
            raise ValueError(f"heights must be a 2-D grid, got shape {shape}")
        return cls(shape[0], shape[1], spacing, edges)

    @property
    def count(self):
        return self.rows * self.columns

    @property
    def shape(self):
        return (self.rows, self.columns)

    def distances(self):
        diagonal = math.sqrt(self.spacing_x * self.spacing_x + self.spacing_y * self.spacing_y)
        return [diagonal if row and column else (self.spacing_y if row else self.spacing_x) for row, column in NEIGHBOURS]

    def neighbours(self):
        index = numpy.arange(self.count, dtype=numpy.int64).reshape(self.shape)
        padded = numpy.pad(index, 1, mode="constant", constant_values=-1)
        return numpy.array([padded[1 + row : 1 + row + self.rows, 1 + column : 1 + column + self.columns].ravel() for row, column in NEIGHBOURS])

    def status(self, heights):
        flat = numpy.asarray(heights, dtype=numpy.float64).ravel()
        valid = numpy.isfinite(flat)
        rows, columns = numpy.divmod(numpy.arange(self.count), self.columns)
        open_edge = numpy.zeros(self.count, dtype=bool)
        open_edge |= bool(self.edges & EDGE_NORTH) & (rows == 0)
        open_edge |= bool(self.edges & EDGE_SOUTH) & (rows == self.rows - 1)
        open_edge |= bool(self.edges & EDGE_WEST) & (columns == 0)
        open_edge |= bool(self.edges & EDGE_EAST) & (columns == self.columns - 1)
        if self.edges & EDGE_NODATA:
            table = self.neighbours()
            inside = table >= 0
            open_edge |= (inside & ~valid[numpy.maximum(table, 0)]).any(axis=0)
        found = numpy.where(open_edge, OUTLET, INTERIOR).astype(numpy.uint8)
        found[~valid] = NODATA
        return found

    def distance(self, cells, others):
        cell_rows, cell_columns = numpy.divmod(numpy.asarray(cells, dtype=numpy.int64), self.columns)
        other_rows, other_columns = numpy.divmod(numpy.asarray(others, dtype=numpy.int64), self.columns)
        along_y = (cell_rows.astype(numpy.float64) - other_rows.astype(numpy.float64)) * self.spacing_y
        along_x = (cell_columns.astype(numpy.float64) - other_columns.astype(numpy.float64)) * self.spacing_x
        return numpy.sqrt(along_x * along_x + along_y * along_y)


def flat_heights(heights):
    return numpy.ascontiguousarray(heights, dtype=numpy.float64).ravel()
