"""One step of the fluvial model on the terrain kernels."""

from dataclasses import dataclass, field
from typing import Optional

import numpy

from . import terrain_kernels as kernels
from .terrain_grid import EDGE_EAST, EDGE_NORTH, EDGE_SOUTH, EDGE_WEST

WORLD_EDGES = {"north": EDGE_SOUTH, "south": EDGE_NORTH, "east": EDGE_EAST, "west": EDGE_WEST}
"""World directions (+Y north) to the kernels' edge bits: rows grow along +y and the kernels call row 0 north,
so the world's north side (the last row) is the kernels' south edge."""


def edge_mask(sides):
    """The kernels' edge bits for base level on the given world sides."""
    mask = 0
    for side in sides:
        if side not in WORLD_EDGES:
            raise ValueError(f"a base level side must be one of {', '.join(WORLD_EDGES)}, got {side!r}")
        mask |= WORLD_EDGES[side]
    if not mask:
        raise ValueError("base level needs at least one side")
    return mask


def outlet_cells(shape, edges):
    """True on the cells of the open sides, which stay at base level."""
    rows, columns = shape
    mask = numpy.zeros(shape, dtype=bool)
    if edges & EDGE_NORTH:
        mask[0, :] = True
    if edges & EDGE_SOUTH:
        mask[rows - 1, :] = True
    if edges & EDGE_WEST:
        mask[:, 0] = True
    if edges & EDGE_EAST:
        mask[:, columns - 1] = True
    return mask


@dataclass
class Law:
    """The physics of a run. erodibility K (m^(1 - 2m)/yr for n = 1) may be a grid; diffusivity D in m^2/yr;
    critical_slope (a gradient) makes the diffusion non-linear (Roering et al. 1999), None keeps it linear.
    channel_area (m^2) is the drainage area of a channel head at the gradient head_slope: steeper ground starts
    channels at smaller areas, A_c(S) = channel_area (S / head_slope)^-head_exponent (Montgomery & Dietrich 1992
    found A S^2 about constant). Stream power acts only on channel cells; the hillslopes above are shaped by the
    hillslope processes alone.
    threshold_slope (a gradient, or a grid of them; or threshold_of, a function (shape, step) giving one grid per
    step for a threshold that varies from step to step) is the threshold of landsliding: where uplift outpaces soil
    transport, hillslopes are cut back to it and stand as planes near it (Burbank et al. 1996; Montgomery 2001).
    Each step ends on the threshold surface, so no slope stands steeper. flow is dinf (incision over the D-infinity
    graph, n = 1 only) or d8 (along the lake-routed receivers, any n)."""
    erodibility: object
    area_exponent: float = 0.45
    slope_exponent: float = 1.0
    diffusivity: float = 0.01
    critical_slope: Optional[float] = None
    carve: bool = True
    channel_area: float = 0.0
    head_slope: float = 0.6
    head_exponent: float = 2.0
    threshold_of: Optional[object] = None
    threshold_slope: Optional[float] = None
    max_ratio: float = 0.999
    flow: str = "dinf"
    edges: int = EDGE_NORTH
    threads: int = 4


@dataclass
class Step:
    heights: numpy.ndarray
    receivers: numpy.ndarray
    ordering: object
    area: numpy.ndarray
    water: numpy.ndarray
    lake: numpy.ndarray
    eroded: numpy.ndarray
    basins: int = 0
    extra: dict = field(default_factory=dict)


def route(heights, spacing, law):
    """The D8 graph after lake routing (Cordonnier, Bovy & Braun 2019) with its order and area: the routed receivers,
    lakes and lake depths of the outputs and the network measures. With law.flow "d8" the incision follows it too."""
    receivers, _ = kernels.d8(heights, spacing, law.edges, law.threads, "core")
    ordering = kernels.order(receivers, heights.shape, 1, law.threads, "core")
    lakes = kernels.route_lakes(heights, receivers, ordering, law.carve, spacing, law.edges, law.threads, "core")
    routed = kernels.order(lakes.receivers, heights.shape, 1, law.threads, "core")
    weights = numpy.full(heights.size, spacing[0] * spacing[1])
    area = kernels.accumulate(routed, weights, threads=law.threads, engine="core")
    return lakes, routed, area


def spread_flow(heights, spacing, law):
    """The D-infinity graph the incision follows (Tarboton 1997): on the surface filled by Priority-Flood with epsilon
    (Barnes et al. 2014) every cell descends strictly to the base level, so the graph has no cycle and flow crosses a
    lake to its spill point. Each cell sends its flow to the one or two neighbours bracketing its true downslope
    direction, so channels follow the slope instead of the eight grid directions. Returns the receiver table, the
    shares, their order and the drainage area in m^2."""
    filled, _ = kernels.priority_flood(heights, True, law.edges, "core")
    table, shares = kernels.dinf(filled, spacing, law.edges, law.threads, "core")
    ordering = kernels.order(table, heights.shape, 8, law.threads, "core")
    weights = numpy.full(heights.size, spacing[0] * spacing[1])
    area = kernels.accumulate(ordering, weights, shares, law.threads, "core")
    return table, shares, ordering, area

def channel_mask(law, heights, spacing, area):
    """True where the drainage area reaches the head area at the cell's slope (steepest of the central differences)."""
    area = numpy.asarray(area).reshape(heights.shape)
    if law.head_exponent == 0.0:
        return area >= law.channel_area
    rise_y, rise_x = numpy.gradient(heights, spacing[1], spacing[0])
    slope = numpy.maximum(numpy.hypot(rise_x, rise_y), 1e-3)
    return area * (slope / law.head_slope) ** law.head_exponent >= law.channel_area


def erodibility_grid(law, shape, channel):
    """K on the channel cells, zero on the hillslopes above the channel heads."""
    value = law.erodibility
    if numpy.ndim(value) == 0:
        grid = numpy.full(shape[0] * shape[1], float(value))
    else:
        grid = numpy.asarray(value, dtype=numpy.float64)
        if grid.shape != tuple(shape):
            raise ValueError(f"the erodibility grid must have shape {tuple(shape)}, got {grid.shape}")
        grid = grid.ravel()
    return numpy.where(numpy.asarray(channel).ravel(), grid, 0.0)


def step(heights, uplift, spacing, law, dt, index=0):
    """Advances the surface by dt years (Braun & Willett 2013): routes the flow on the current surface, lifts it
    by uplift * dt (zero on the base level cells), solves incision implicitly along the receivers, then
    diffuses the hillslopes over the same step. The channels are
    detachment-limited with more transport capacity than the hillslopes supply (Whipple & Tucker 2002): hillslope
    material that reaches a channel cell is carried away, so the hillslope processes may lower a channel cell but
    never raise it. eroded is the height removed relative to the lifted surface (negative where material was laid
    down). Last the surface is cut back to the threshold slopes; that removes material, never adds it, so it keeps
    the channel rule. index numbers the step for a threshold that varies from step to step."""
    lakes, routed, area = route(heights, spacing, law)
    lifted = heights + uplift * dt
    if law.flow == "dinf" and law.slope_exponent == 1.0:
        table, shares, spread, area = spread_flow(heights, spacing, law)
        channel = channel_mask(law, heights, spacing, area)
        incised = kernels.incise_many(lifted, table, shares, spread, area, erodibility_grid(law, heights.shape, channel),
                                      law.area_exponent, dt, spacing, law.threads, "core")
    else:
        channel = channel_mask(law, heights, spacing, area)
        incised = kernels.incise(lifted, lakes.receivers, routed, area, erodibility_grid(law, heights.shape, channel),
                                 law.area_exponent, law.slope_exponent, dt, spacing, law.threads, "core")
    shaped = incised
    if law.diffusivity > 0.0:
        shaped = kernels.diffuse(shaped, law.diffusivity, dt, spacing, law.edges, critical_slope=law.critical_slope,
                                 max_ratio=law.max_ratio, threads=law.threads, engine="core")
    area = numpy.asarray(area).reshape(heights.shape)
    surface = numpy.where(channel, numpy.minimum(incised, shaped), shaped)
    tangent = law.threshold_of(heights.shape, index) if law.threshold_of is not None else law.threshold_slope
    if tangent is not None:
        surface, _ = kernels.threshold(surface, tangent, spacing, law.edges, "core")
    water = numpy.asarray(lakes.water, dtype=numpy.float64).reshape(heights.shape)
    return Step(heights=surface, receivers=numpy.asarray(lakes.receivers), ordering=routed, area=area, water=water,
                lake=numpy.asarray(lakes.lake).reshape(heights.shape), eroded=lifted - surface, basins=lakes.basins,
                extra={"tangent": tangent, "channel": channel})
