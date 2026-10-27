import math

GAP = 0.015
PAD = 0.01
WIDTH_FACTORS = (0.8, 1.0, 1.4, 2.0, 3.0)


def island_boxes(data):
    boxes = {}
    for island, uvs in zip(data.islands, data.uvs):
        if uvs is None:
            continue
        box = boxes.setdefault(island, [math.inf, math.inf, -math.inf, -math.inf])
        for u, v in uvs:
            box[0] = min(box[0], u)
            box[1] = min(box[1], v)
            box[2] = max(box[2], u)
            box[3] = max(box[3], v)
    return boxes


def shelves(sizes, width, gap):
    placed = {}
    x = y = row = 0.0
    for island, (w, h) in sizes:
        if x > 0 and x + w > width:
            x = 0.0
            y += row + gap
            row = 0.0
        placed[island] = (x, y)
        x += w + gap
        row = max(row, h)
    return placed


def side_of(placed, sizes):
    width = max(placed[island][0] + w for island, (w, h) in sizes)
    height = max(placed[island][1] + h for island, (w, h) in sizes)
    return max(width, height)


def best_layout(sizes, gap):
    area = sum(w * h for _, (w, h) in sizes)
    widest = max(w for _, (w, h) in sizes)
    layouts = []
    for factor in WIDTH_FACTORS:
        placed = shelves(sizes, max(widest, math.sqrt(area) * factor), gap)
        layouts.append((side_of(placed, sizes), placed))
    return min(layouts, key=lambda layout: layout[0])


def pack_islands(data):
    boxes = island_boxes(data)
    if not boxes:
        return
    sizes = [(island, (max(box[2] - box[0], 1e-9), max(box[3] - box[1], 1e-9))) for island, box in boxes.items()]
    sizes.sort(key=lambda item: (-item[1][1], item[0]))
    loose_side, _ = best_layout(sizes, 0.0)
    side, placed = best_layout(sizes, GAP * loose_side)
    scale = (1.0 - 2 * PAD) / side
    for index, (island, uvs) in enumerate(zip(data.islands, data.uvs)):
        if uvs is None:
            continue
        box = boxes[island]
        ox, oy = placed[island]
        data.uvs[index] = [((u - box[0] + ox) * scale + PAD, (v - box[1] + oy) * scale + PAD) for u, v in uvs]
