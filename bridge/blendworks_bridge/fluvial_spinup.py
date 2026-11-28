"""Coarse-to-fine spin-up of the fluvial model."""

import math
import time
from dataclasses import dataclass, field, replace

import numpy

from .fluvial_fields import base_distance, resample, strike_variation
from .fluvial_model import outlet_cells, step

COARSE_COURANT = 150.0
"""The implicit scheme is stable at any step (Braun & Willett 2013): dt only sets how far a knickpoint may move
per step, dt = courant * dx / (K A_max^m S^(n-1)), the courant number counting cells. For n = 1 the steady state
does not depend on dt, so the coarsest level, which only seeks it, takes long steps; finer levels shorter ones."""
FINE_COURANT = 30.0
COARSE_STEPS = 200
MIDDLE_STEPS = 20
FINEST_STEPS = 5
REFINE_RELIEF = 0.01
"""Random relief added to a refined level, enough to break the ties of the interpolated surface."""
VALLEY_CELLS = 4
"""Stream power with hillslope diffusion spaces valleys by L_c = (D / K)^(1 / 2m) (Perron, Kirchner & Dietrich 2008).
A coarse level cannot resolve the physical spacing, so its valleys would follow the grid; there the diffusivity
stands for the unresolved hillslopes and channels and is raised until L_c spans at least this many cells."""
HEAD_CELLS = 8
"""Every cell that drains more than the channel head area incises. If that is a single cell, each cell of a valley
wall becomes its own channel, a comb of one-cell gullies; a level's head area is at least this many cells."""
STEADY_TOLERANCE = 0.01
COARSEST = 512
"""The coarsest level: fine enough that its grid does not show in the network and that it resolves channel heads
of 0.1 km^2 at 30 m cells (Montgomery & Dietrich 1988), coarse enough to reach steady state in its budget."""


@dataclass
class Schedule:
    """levels: grid sides from coarse to fine. steps: the step budget of each level. The run of a level stops
    once the surface changes by less than tolerance times the mean uplift per step."""
    levels: list
    steps: list
    courant: list
    tolerance: float = STEADY_TOLERANCE
    max_dt: float = 1.0e5


def default_schedule(side):
    """Levels halving down from side to COARSEST cells (side itself when smaller). Most of the budget goes to the
    coarsest level, which seeks the steady state; the middle levels refine it and the finest takes a few steps."""
    levels = [side]
    while (levels[-1] - 1) // 2 + 1 >= COARSEST:
        levels.append((levels[-1] - 1) // 2 + 1)
    levels.reverse()
    steps = [COARSE_STEPS] + [MIDDLE_STEPS] * max(len(levels) - 2, 0) + ([FINEST_STEPS] if len(levels) > 1 else [])
    courant = [COARSE_COURANT] + [FINE_COURANT] * (len(levels) - 1)
    return Schedule(levels=levels, steps=steps, courant=courant)


def stable_dt(law, spacing, area, slope, schedule, erodibility, courant):
    """The step from the knickpoint rule above, at the current largest area and steepest channel slope."""
    exponent = law.slope_exponent - 1.0
    celerity = float(numpy.max(erodibility)) * float(area.max()) ** law.area_exponent * max(slope, 1e-6) ** exponent
    return min(schedule.max_dt, courant * min(spacing) / max(celerity, 1e-30))


def level_diffusivity(law, spacing, erodibility):
    """The law's diffusivity, or the larger one that spaces this level's valleys VALLEY_CELLS cells apart."""
    resolved = float(numpy.min(erodibility)) * (VALLEY_CELLS * max(spacing)) ** (2.0 * law.area_exponent)
    return max(law.diffusivity, resolved)


@dataclass
class LevelReport:
    side: int
    spacing: float
    steps: int
    years: float
    dt: list
    change: float
    steady: bool
    seconds: float


@dataclass
class Spun:
    heights: numpy.ndarray
    last: object
    eroded: numpy.ndarray
    levels: list = field(default_factory=list)
    years: float = 0.0


def channel_slope(heights, receivers, spacing):
    flat = heights.ravel()
    target = receivers >= 0
    if not target.any():
        return 0.0
    drop = flat[target] - flat[receivers[target]]
    return float(numpy.percentile(numpy.maximum(drop, 0.0), 99) / min(spacing))


def run_level(heights, uplift, spacing, law, erodibility, steps, courant, schedule, eroded, first_index=0):
    """Steps one level until steady or its budget is spent; returns the surface and its report."""
    started = time.perf_counter()
    moving = ~outlet_cells(heights.shape, law.edges)
    uplift = numpy.where(moving, uplift, 0.0)
    mean_uplift = float(uplift[moving].mean()) if moving.any() else 0.0
    area, slope = numpy.full(1, heights.size * spacing[0] * spacing[1]), 0.1
    taken, years, dts, change, steady, last = 0, 0.0, [], math.inf, False, None
    while taken < steps:
        dt = stable_dt(law, spacing, area, slope, schedule, erodibility, courant)
        last = step(heights, uplift, spacing, law, dt, first_index + taken)
        change = float(numpy.abs(last.heights - heights)[moving].mean()) / max(mean_uplift * dt, 1e-30)
        eroded = eroded + last.eroded
        heights, area = last.heights, last.area
        slope = channel_slope(heights, last.receivers, spacing)
        taken, years = taken + 1, years + dt
        dts.append(dt)
        if change < schedule.tolerance:
            steady = True
            break
    report = LevelReport(side=heights.shape[0], spacing=spacing[0], steps=taken, years=years, dt=[min(dts), max(dts)] if dts else [0.0, 0.0],
                         change=change, steady=steady, seconds=time.perf_counter() - started)
    return heights, last, eroded, report


def spin_up(side, cell, uplift_of, law, schedule=None, seed=0, initial_relief=1.0, initial_slope=0.0, initial_waves=0.0, start=None):
    """Runs the schedule to a side x side grid of cell metres. uplift_of(shape, spacing) gives the uplift rate
    field of a level. The coarsest level starts from start (resampled) or from a random surface of initial_relief
    metres (seeded), which only breaks the symmetry of the flat. Each finer level starts from the coarser
    surface, resampled bilinearly, with a little random relief added to break the ties of the interpolation.
    initial_slope (a gradient) tilts the starting surface away from the base level, so every cell drains from the
    first step and the network organises everywhere at once instead of growing headward from the base level.
    initial_waves (metres) adds smooth seeded relief with wavelengths of a third of the domain and more, so the
    coarsest network starts with long-wavelength structure and not only cell-scale noise."""
    schedule = schedule or default_schedule(side)
    extent = (side - 1) * cell
    rng = numpy.random.default_rng(seed)
    heights, eroded, reports, years, last = None, None, [], 0.0, None
    for index, level in enumerate(schedule.levels):
        spacing = (extent / (level - 1), extent / (level - 1))
        shape = (level, level)
        if heights is None:
            heights = resample(start, shape) if start is not None else initial_slope * base_distance(shape, spacing, law.edges)
            if initial_waves:
                heights = heights + initial_waves * (strike_variation(shape, spacing, 1.0, seed + 3, waves=6) - 1.0)
            eroded = numpy.zeros(shape)
        else:
            heights, eroded = resample(heights, shape), resample(eroded, shape)
        heights = heights + rng.random(shape) * (initial_relief if index == 0 else REFINE_RELIEF)
        heights[outlet_cells(shape, law.edges)] = 0.0
        erodibility = law.erodibility if numpy.ndim(law.erodibility) == 0 else resample(law.erodibility, shape)
        tangent = law.threshold_slope if numpy.ndim(law.threshold_slope) == 0 else resample(law.threshold_slope, shape)
        head = law.channel_area if index == 0 else max(law.channel_area, HEAD_CELLS * spacing[0] * spacing[1])
        level_law = replace(law, erodibility=erodibility, threshold_slope=tangent, diffusivity=level_diffusivity(law, spacing, erodibility), channel_area=head)
        heights, last, eroded, report = run_level(heights, uplift_of(shape, spacing), spacing, level_law, erodibility,
                                                 schedule.steps[index], schedule.courant[index], schedule, eroded,
                                                 sum(report.steps for report in reports))
        years += report.years
        reports.append(report)
    return Spun(heights=heights, last=last, eroded=eroded, levels=reports, years=years)
