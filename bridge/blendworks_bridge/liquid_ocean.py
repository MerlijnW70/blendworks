"""Ocean surface grid, skirt and beach heights."""

import math

import numpy
from mathutils import Vector

from . import liquid_bodies, liquid_spectrum
from .limits import MAX_WAVE_CELLS
from .liquid_grid import DOWN

MAX_CELLS = MAX_WAVE_CELLS
SKIRT_RINGS = 24
HORIZON = 30_000.0
BEACH_SLOPE = 0.03
BEACH_FLOOR = 20.0
OPEN_DEPTH = 1000.0


def square_grid(centre, size, cells):
    step = size / cells
    axis = numpy.arange(cells + 1) * step - size / 2.0
    x, y = numpy.meshgrid(axis + centre[0], axis + centre[1])
    points = numpy.stack([x.ravel(), y.ravel(), numpy.zeros(x.size)], axis=1)
    index = numpy.arange((cells + 1) ** 2).reshape(cells + 1, cells + 1)
    a, b, c, d = index[:-1, :-1].ravel(), index[:-1, 1:].ravel(), index[1:, 1:].ravel(), index[1:, :-1].ravel()
    triangles = numpy.concatenate([numpy.stack([a, b, c], axis=1), numpy.stack([a, c, d], axis=1)])
    border = numpy.concatenate([index[0, :-1], index[:-1, -1], index[-1, :0:-1], index[:0:-1, 0]])
    return points, triangles, border


def skirt(points, border, centre, radius, rings):
    """Flat rings from the edge of the square grid out to the horizon, spaced geometrically."""
    start = points[border, :2] - numpy.array(centre[:2])
    reach = numpy.linalg.norm(start, axis=1)
    shares = numpy.geomspace(1.0, radius / max(reach.min(), 1e-6), rings + 1)[1:]
    new_points, triangles = [], []
    previous = border
    offset = len(points)
    count = len(border)
    for share in shares:
        ring = numpy.column_stack([centre[0] + start[:, 0] * share, centre[1] + start[:, 1] * share, numpy.zeros(count)])
        indices = offset + numpy.arange(count)
        new_points.append(ring)
        following = numpy.roll(numpy.arange(count), -1)
        triangles.append(numpy.stack([previous, indices, indices[following]], axis=1))
        triangles.append(numpy.stack([previous, indices[following], previous[following]], axis=1))
        previous = indices
        offset += count
    return numpy.concatenate(new_points), numpy.concatenate(triangles)


def ground_depth(points, level, ground):
    if ground is None:
        return numpy.full(len(points), OPEN_DEPTH)
    depth = numpy.full(len(points), OPEN_DEPTH)
    top = ground.high[2] + 1.0
    for index, (x, y) in enumerate(points[:, :2].tolist()):
        hit = ground.tree.ray_cast(Vector((x, y, top)), DOWN)[0]
        if hit is not None:
            depth[index] = level - hit.z
    return depth


def beach_heights(x, y, level, direction, shore):
    heading = math.radians(direction)
    along = x * math.sin(heading) + y * math.cos(heading)
    return numpy.maximum(level + (along - shore) * BEACH_SLOPE, level - BEACH_FLOOR)


def beach_mesh(centre, size, level, direction, shore):
    cells = 128
    points, triangles, _ = square_grid(centre, size * 1.2, cells)
    points[:, 2] = beach_heights(points[:, 0], points[:, 1], level, direction, shore)
    return points, triangles


def build(args, ground, state, wind, seed):
    centre = args.get("centre", [0.0, 0.0])
    size = args.get("size", 400.0)
    level = args.get("level", 0.0)
    cells = min(args.get("cells", MAX_CELLS), MAX_CELLS)
    cell = size / cells
    choppiness = args.get("choppiness", 0.8)
    points, triangles, border = square_grid(centre, size, cells)
    points[:, 2] = level
    depth = ground_depth(points, level, ground)
    tile = liquid_bodies.mesh_tile(state, wind["direction"], cell, seed, choppiness, size)
    heights, shifts, jacobian = liquid_bodies.wave_displacement(points, tile, state, numpy.maximum(depth, 0.0), choppiness)
    fraction = liquid_spectrum.whitecap_fraction(wind["speed"])
    foam = liquid_bodies.foam_values(jacobian, fraction, depth, state["hs"])
    foam = numpy.where(depth < 0.0, 0.0, foam)
    points[:, 2] += heights
    points[:, :2] += shifts
    if args.get("horizon", True):
        ring_points, ring_triangles = skirt(points, border, centre, args.get("horizon_distance", HORIZON), SKIRT_RINGS)
        ring_points[:, 2] = level
        points = numpy.concatenate([points, ring_points])
        triangles = numpy.concatenate([triangles, ring_triangles])
        foam = numpy.concatenate([foam, numpy.zeros(len(ring_points))])
        depth = numpy.concatenate([depth, numpy.full(len(ring_points), OPEN_DEPTH)])
    uvs = numpy.column_stack([points[:, 0] / size, points[:, 1] / size])
    report = {
        "size": size,
        "cell": cell,
        "mesh_hs": round(float(4.0 * heights.std()), 6),
        "whitecap_fraction": round(fraction, 6),
        "tile": None if tile is None else {"size": round(tile.size, 3), "resolution": tile.resolution, "hs": round(4.0 * math.sqrt(tile.variance), 6)},
    }
    return points, triangles, uvs, {"lq_foam": foam, "lq_depth": depth}, report
