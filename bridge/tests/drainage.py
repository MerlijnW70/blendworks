import heapq

import numpy

NEIGHBOURS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def filled(heights):
    rows, columns = heights.shape
    level = heights.copy()
    seen = numpy.zeros(heights.shape, dtype=bool)
    queue = []
    for row in range(rows):
        for column in range(columns):
            if row in (0, rows - 1) or column in (0, columns - 1):
                heapq.heappush(queue, (level[row, column], row, column))
                seen[row, column] = True
    while queue:
        height, row, column = heapq.heappop(queue)
        for step_row, step_column in NEIGHBOURS:
            other_row, other_column = row + step_row, column + step_column
            if 0 <= other_row < rows and 0 <= other_column < columns and not seen[other_row, other_column]:
                seen[other_row, other_column] = True
                level[other_row, other_column] = max(level[other_row, other_column], height + 1e-6)
                heapq.heappush(queue, (level[other_row, other_column], other_row, other_column))
    return level


def accumulation(heights):
    level = filled(heights)
    rows, columns = level.shape
    area = numpy.ones(level.shape)
    receiver = {}
    for flat in numpy.argsort(-level, axis=None):
        row, column = divmod(int(flat), columns)
        best, target = 0.0, None
        for step_row, step_column in NEIGHBOURS:
            other_row, other_column = row + step_row, column + step_column
            if 0 <= other_row < rows and 0 <= other_column < columns:
                drop = (level[row, column] - level[other_row, other_column]) / (1.4142 if step_row and step_column else 1.0)
                if drop > best:
                    best, target = drop, (other_row, other_column)
        if target is not None:
            area[target] += area[row, column]
            receiver[(row, column)] = target
    return area, receiver


def drainage(heights, threshold):
    area, receiver = accumulation(heights)
    channel = area >= threshold
    inflow = numpy.zeros(heights.shape, dtype=int)
    for source, target in receiver.items():
        if channel[source] and channel[target]:
            inflow[target] += 1
    return {
        "channel_share": float(channel.mean()),
        "confluences": int((inflow >= 2).sum()),
        "sink_volume": float((filled(heights) - heights).sum()),
    }
