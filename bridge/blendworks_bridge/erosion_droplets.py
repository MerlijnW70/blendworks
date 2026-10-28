import numpy

BATCH = 512


def locate(heights, spacing, position):
    column_float = position[:, 0] / spacing[0]
    row_float = position[:, 1] / spacing[1]
    cell_column = numpy.clip(column_float.astype(numpy.int64), 0, heights.shape[1] - 2)
    cell_row = numpy.clip(row_float.astype(numpy.int64), 0, heights.shape[0] - 2)
    return cell_row, cell_column, row_float - cell_row, column_float - cell_column


def height_and_gradient(heights, spacing, position):
    cell_row, cell_column, along_row, along_column = locate(heights, spacing, position)
    h00 = heights[cell_row, cell_column]
    h01 = heights[cell_row, cell_column + 1]
    h10 = heights[cell_row + 1, cell_column]
    h11 = heights[cell_row + 1, cell_column + 1]
    height = (h00 * (1.0 - along_column) + h01 * along_column) * (1.0 - along_row) + (h10 * (1.0 - along_column) + h11 * along_column) * along_row
    gradient_x = ((h01 - h00) * (1.0 - along_row) + (h11 - h10) * along_row) / spacing[0]
    gradient_y = ((h10 - h00) * (1.0 - along_column) + (h11 - h01) * along_column) / spacing[1]
    return height, numpy.stack([gradient_x, gradient_y], axis=1)


def inside(heights, spacing, position):
    rows, columns = heights.shape
    return (position[:, 0] >= 0.0) & (position[:, 0] < (columns - 1) * spacing[0]) & (position[:, 1] >= 0.0) & (position[:, 1] < (rows - 1) * spacing[1])


def corner_nodes(heights, spacing, position):
    cell_row, cell_column, along_row, along_column = locate(heights, spacing, position)
    rows = numpy.stack([cell_row, cell_row, cell_row + 1, cell_row + 1], axis=1)
    columns = numpy.stack([cell_column, cell_column + 1, cell_column, cell_column + 1], axis=1)
    weights = numpy.stack([(1.0 - along_row) * (1.0 - along_column), (1.0 - along_row) * along_column, along_row * (1.0 - along_column), along_row * along_column], axis=1)
    return rows, columns, weights


class Brush:
    def __init__(self, spacing, radius):
        self.spacing = spacing
        self.radius = max(radius, 1.5 * max(spacing))
        reach = (int(numpy.ceil(self.radius / spacing[1])), int(numpy.ceil(self.radius / spacing[0])))
        rows, columns = numpy.meshgrid(numpy.arange(-reach[0], reach[0] + 1), numpy.arange(-reach[1], reach[1] + 1), indexing="ij")
        self.offsets = (rows.ravel(), columns.ravel())

    def nodes(self, shape, position):
        centre_column = numpy.rint(position[:, 0] / self.spacing[0]).astype(numpy.int64)
        centre_row = numpy.rint(position[:, 1] / self.spacing[1]).astype(numpy.int64)
        rows = centre_row[:, None] + self.offsets[0][None, :]
        columns = centre_column[:, None] + self.offsets[1][None, :]
        distance = numpy.hypot(columns * self.spacing[0] - position[:, 0:1], rows * self.spacing[1] - position[:, 1:2])
        weights = numpy.maximum(0.0, 1.0 - distance / self.radius)
        weights /= weights.sum(axis=1, keepdims=True)
        valid = (rows >= 0) & (rows < shape[0]) & (columns >= 0) & (columns < shape[1])
        return numpy.where(valid, rows, 0), numpy.where(valid, columns, 0), weights * valid


class Droplets:
    def __init__(self, heights, free, spacing, settings):
        self.heights = heights
        self.free = free
        self.spacing = spacing
        self.settings = settings
        self.brush = Brush(spacing, settings["radius"])
        self.cell_area = spacing[0] * spacing[1]
        self.patch = settings["step"] ** 2
        self.carried = 0.0

    def apply(self, nodes, amount, sign):
        rows, columns, weights = nodes
        share = weights * self.free[rows, columns]
        change = sign * (amount * self.patch / self.cell_area)[:, None] * share
        numpy.add.at(self.heights, (rows.ravel(), columns.ravel()), change.ravel())
        return amount * share.sum(axis=1)

    def drop(self, position, amount):
        return self.apply(corner_nodes(self.heights, self.spacing, position), amount, 1.0)

    def cut(self, position, amount):
        return self.apply(self.brush.nodes(self.heights.shape, position), amount, -1.0)

    def finish(self, position, sediment):
        if len(sediment):
            placed = self.drop(position, sediment)
            self.carried += float(numpy.sum(sediment - placed)) * self.patch

    def lose(self, sediment):
        self.carried += float(numpy.sum(sediment)) * self.patch

    def run(self, starts):
        settings = self.settings
        count = len(starts)
        position = numpy.array(starts, dtype=float)
        direction = numpy.zeros((count, 2))
        speed = numpy.ones(count)
        water = numpy.ones(count)
        sediment = numpy.zeros(count)
        alive = numpy.ones(count, dtype=bool)
        for _ in range(settings["max_lifetime"]):
            index = numpy.flatnonzero(alive)
            if not len(index):
                break
            old_height, gradient = height_and_gradient(self.heights, self.spacing, position[index])
            heading = direction[index] * settings["inertia"] - gradient * (1.0 - settings["inertia"])
            length = numpy.linalg.norm(heading, axis=1)
            still = length < 1e-12
            if still.any():
                self.finish(position[index[still]], sediment[index[still]])
                alive[index[still]] = False
                sediment[index[still]] = 0.0
                index, heading, length, old_height = index[~still], heading[~still], length[~still], old_height[~still]
            heading = heading / length[:, None]
            direction[index] = heading
            moved = position[index] + heading * settings["step"]
            gone = ~inside(self.heights, self.spacing, moved)
            if gone.any():
                self.lose(sediment[index[gone]])
                alive[index[gone]] = False
                sediment[index[gone]] = 0.0
                index, moved, old_height = index[~gone], moved[~gone], old_height[~gone]
            if not len(index):
                continue
            new_height, _ = height_and_gradient(self.heights, self.spacing, moved)
            change = new_height - old_height
            sine = -change / numpy.hypot(settings["step"], change)
            capacity = numpy.maximum(settings["capacity"] * sine * speed[index] * water[index], settings["min_capacity"])
            carrying = sediment[index]
            deposits = (carrying > capacity) | (change > 0.0)
            wanted = numpy.where(change > 0.0, numpy.minimum(change, carrying), (carrying - capacity) * settings["deposit_rate"])
            digging = numpy.maximum(numpy.minimum((capacity - carrying) * settings["erode_rate"], -change), 0.0)
            here = position[index]
            placed = numpy.zeros(len(index))
            taken = numpy.zeros(len(index))
            if deposits.any():
                placed[deposits] = self.drop(here[deposits], wanted[deposits])
            if not deposits.all():
                taken[~deposits] = self.cut(here[~deposits], digging[~deposits])
            sediment[index] = carrying - placed + taken
            speed[index] = numpy.sqrt(numpy.maximum(speed[index] ** 2 - change * settings["gravity"], 0.0))
            water[index] *= 1.0 - settings["evaporation"]
            position[index] = moved
        rest = numpy.flatnonzero(alive)
        self.finish(position[rest], sediment[rest])


def hydraulic_erode(heights, free, spacing, settings, droplets, seed):
    rng = numpy.random.default_rng(seed)
    extent = numpy.array([(heights.shape[1] - 1) * spacing[0], (heights.shape[0] - 1) * spacing[1]])
    engine = Droplets(heights, free, spacing, settings)
    remaining = droplets
    while remaining > 0:
        batch = min(BATCH, remaining)
        engine.run(rng.random((batch, 2)) * extent)
        remaining -= batch
    return engine.carried
