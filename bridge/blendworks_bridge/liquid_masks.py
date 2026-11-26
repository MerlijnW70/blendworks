import numpy

from . import liquid_world
from .errors import bad_args

MODES = ("avoid", "shore", "ignore")
WATERLINE_EDGE = 0.15


def corner_depth(target, surface, depsgraph, band=0.0):
    """liquid_depth at the corners of the surface's triangles (positive under water, minus the distance to the water when dry),
    measured at least band metres past the water line."""
    depth = liquid_world.target_depth(target, depsgraph, band + 2.0 * WATERLINE_EDGE + 1.0)
    if depth is None:
        return None
    if len(depth) <= int(surface.vertex_ids.max()):
        raise bad_args(f"{target.name}'s modifiers change its vertices, so the liquid mask cannot read it")
    return depth[surface.vertex_ids]


def mask(corners, surface, triangle, weights, mode, shore, edge=WATERLINE_EDGE, depth=0.0):
    """avoid: 0 under water, rising to 1 over edge metres above the water line; shore: 1 from depth metres under the water
    line to shore metres above it."""
    if corners is None or mode == "ignore":
        return numpy.ones(len(triangle))
    dry = -surface.interpolate(corners, triangle, weights)
    if mode == "avoid":
        return numpy.clip(dry / max(edge, 1e-6), 0.0, 1.0)
    rising = numpy.clip((dry + depth) / max(min(edge, shore * 0.25), 1e-6), 0.0, 1.0)
    falling = numpy.clip((shore - dry) / max(edge, 1e-6), 0.0, 1.0)
    return rising * falling
