"""Shape statistics of stones and the three transport histories; sources in docs/research/rock-realism.md.

- Roundness: Wadell (1932), the mean radius of curvature of the corners of the outline in the plane of the long and
  intermediate axes over the radius of the largest inscribed circle; a corner is a part of the outline curved more tightly
  than that circle. Powers (1953) classes: very angular 0.12 to 0.17, angular to 0.25, subangular to 0.35, subrounded to
  0.49, rounded to 0.70, well rounded above. The class ranges below widen Powers' bands by about 0.07, the scatter of
  visual and image estimates of the same grains (Blott and Pye 2008), since a sharp corner on an outline of OUTLINE_POINTS
  steps reads no lower than about 0.1.
- Sphericity: Krumbein's (1941) intercept sphericity (b c / a^2)^(1/3) of the long, intermediate and short axes.
- Flatness: c / a, the short over the long axis (Sneed and Folk 1958).
- Histories: talus blocks are fresh fragments, blocky with about six faces (Domokos et al. 2020), angular to subangular;
  shore stones are reworked by waves to subangular and subrounded; river cobbles are rolled to rounded (Kuenen 1956). Abrasion rounds
  corners and edges first, by their curvature (Firey 1974; Domokos and Gibbons 2012), so faces stay flat while edges round.
"""
import numpy

from .portable_math import acos

HISTORIES = {
    "talus": {"roundness": (0.1, 0.42), "sphericity": (0.55, 0.88), "flatness": (0.35, 0.85),
              "intermediate": (0.55, 0.95), "short": (0.6, 0.9), "chips": 4, "chip_depth": 0.06, "fresh_faces": 0.5, "fresh": True},
    "shore": {"roundness": (0.3, 0.62), "sphericity": (0.5, 0.88), "flatness": (0.3, 0.8),
              "intermediate": (0.55, 0.95), "short": (0.55, 0.85), "chips": 6, "chip_depth": 0.1, "fresh_faces": 0.0, "fresh": True},
    "river": {"roundness": (0.45, 0.85), "sphericity": (0.5, 0.88), "flatness": (0.28, 0.75),
              "intermediate": (0.55, 0.95), "short": (0.45, 0.8), "chips": 3, "chip_depth": 0.14, "fresh_faces": 0.0, "fresh": False},
}
ORDER = ("talus", "shore", "river")
OUTLINE_POINTS = 360
SMOOTHING = 2
INSCRIBED_GRID = 64


def history_of(transport):
    """The history class of a transport from 0 (a fresh fragment) to 1 (a long-rolled cobble)."""
    return ORDER[min(2, int(transport * 3.0))]


def target_roundness(transport):
    """The roundness abrasion works towards: the class's range, entered in proportion to the transport within the class."""
    name = history_of(transport)
    low, high = HISTORIES[name]["roundness"]
    within = min(1.0, max(0.0, transport * 3.0 - ORDER.index(name)))
    return low + (0.2 + 0.6 * within) * (high - low)


def principal_axes(points, triangles):
    """Axes of a closed mesh from the second moments of its surface (each triangle by its area), longest first, and the
    extents a >= b >= c of the mesh along them."""
    corners = points[triangles]
    area = 0.5 * numpy.linalg.norm(numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    centres = corners.mean(axis=1)
    weight = area / area.sum()
    middle = (centres * weight[:, None]).sum(axis=0)
    offset = centres - middle
    moment = (offset * weight[:, None]).T @ offset
    values, vectors = numpy.linalg.eigh(moment)
    vectors = vectors[:, numpy.argsort(values)[::-1]]
    spans = numpy.ptp((points - middle) @ vectors, axis=0)
    order = numpy.argsort(spans)[::-1]
    return vectors[:, order], spans[order], middle


def sphericity(spans):
    a, b, c = spans
    return float((b * c / (a * a)) ** (1.0 / 3.0))


def flatness(spans):
    return float(spans[2] / spans[0])


def hull(xy):
    """Convex hull of plane points, counter-clockwise (Andrew's monotone chain)."""
    order = numpy.lexsort((xy[:, 1], xy[:, 0]))
    points = [tuple(row) for row in xy[order].tolist()]
    chains = []
    for sequence in (points, points[::-1]):
        chain = []
        for point in sequence:
            while len(chain) >= 2 and (chain[-1][0] - chain[-2][0]) * (point[1] - chain[-2][1]) - (chain[-1][1] - chain[-2][1]) * (point[0] - chain[-2][0]) <= 0.0:
                chain.pop()
            chain.append(point)
        chains.append(chain[:-1])
    return numpy.array(chains[0] + chains[1])


def resampled(outline, count):
    closed = numpy.vstack([outline, outline[:1]])
    lengths = numpy.concatenate([[0.0], numpy.cumsum(numpy.linalg.norm(numpy.diff(closed, axis=0), axis=1))])
    where = numpy.linspace(0.0, lengths[-1], count, endpoint=False)
    return numpy.column_stack([numpy.interp(where, lengths, closed[:, axis]) for axis in range(2)]), lengths[-1]


def inscribed_radius(outline):
    """Radius of the largest circle inside a convex outline: the largest distance to its edges over a grid, refined twice
    around the best point."""
    start, end = outline, numpy.roll(outline, -1, axis=0)
    edge = end - start
    normal = numpy.column_stack([edge[:, 1], -edge[:, 0]]) / numpy.linalg.norm(edge, axis=1)[:, None]
    low, high = outline.min(axis=0), outline.max(axis=0)
    best = 0.0
    centre, span = 0.5 * (low + high), 0.5 * (high - low)
    for _ in range(3):
        axis = numpy.linspace(-1.0, 1.0, INSCRIBED_GRID)
        grid = numpy.stack(numpy.meshgrid(centre[0] + span[0] * axis, centre[1] + span[1] * axis), axis=-1).reshape(-1, 2)
        inside = numpy.einsum("pj,ej->pe", grid, -normal) + numpy.einsum("ej,ej->e", start, normal)[None, :]
        clearance = inside.min(axis=1)
        pick = int(numpy.argmax(clearance))
        best = max(best, float(clearance[pick]))
        centre, span = grid[pick], span * 4.0 / INSCRIBED_GRID
    return best


def roundness(points):
    """Wadell roundness of the outline of points seen along z (a stone lying on its short axis): the convex outline at
    OUTLINE_POINTS equal steps, the turn of each step, corners where the turn over 2 * SMOOTHING + 1 steps is tighter than the
    inscribed circle, each corner's radius its tightest radius of curvature over that window, and their mean over the inscribed radius. A circle reads
    1; a square about 0.12, the floor this outline resolution gives a sharp corner (Powers' very angular)."""
    outline, perimeter = resampled(hull(points[:, :2]), OUTLINE_POINTS)
    step = perimeter / OUTLINE_POINTS
    before = outline - numpy.roll(outline, 1, axis=0)
    after = numpy.roll(outline, -1, axis=0) - outline
    lengths = numpy.maximum(numpy.linalg.norm(before, axis=1) * numpy.linalg.norm(after, axis=1), 1e-300)
    turn = acos(numpy.clip(numpy.einsum("ij,ij->i", before, after) / lengths, -1.0, 1.0))
    window = 2 * SMOOTHING + 1
    smoothed = sum(numpy.roll(turn, shift) for shift in range(-SMOOTHING, SMOOTHING + 1))
    radius_inside = inscribed_radius(outline)
    if radius_inside <= 0.0:
        return 0.0
    local = window * step / numpy.maximum(smoothed, 1e-12)
    tight = local < radius_inside
    if not tight.any():
        return 1.0
    if tight.all():
        return min(1.0, float(local.mean()) / radius_inside)
    first = int(numpy.argmin(tight))
    radii, run = [], []
    for flag, radius in zip(numpy.roll(tight, -first).tolist() + [False], numpy.roll(local, -first).tolist() + [0.0]):
        if flag:
            run.append(radius)
        elif run:
            radii.append(min(run))
            run = []
    return min(1.0, float(numpy.mean(radii)) / radius_inside)


def shape_report(points, triangles):
    """Roundness, sphericity and flatness of a stone in its own axes."""
    axes, spans, middle = principal_axes(points, triangles)
    aligned = (points - middle) @ axes
    return {"roundness": roundness(aligned), "sphericity": sphericity(spans), "flatness": flatness(spans), "axes": spans.tolist()}


def in_ranges(report, history):
    ranges = HISTORIES[history]
    return all(ranges[key][0] <= report[key] <= ranges[key][1] for key in ("roundness", "sphericity", "flatness"))
