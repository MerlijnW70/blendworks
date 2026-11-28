//! Implicit stream-power incision (Braun & Willett 2013, "A very efficient O(n), implicit and
//! parallel method to solve the stream power equation governing fluvial incision and landscape
//! evolution", Geomorphology 180-181:170-179) on a single-receiver graph:
//! dh/dt = -K A^m S^n, discretised as h = h* - F (h - h_r)^n with F = K dt A^m / d^n, d the
//! distance to the receiver. Cells are solved level by level from the outlets, so each receiver
//! is solved before its donors. A cell without receiver, or not above its solved receiver, keeps
//! its height.
//! n = 1: h = (h* + F h_r) / (1 + F).
//! other n: Newton on f(h) = h - h* + F (h - h_r)^n, which changes sign over [h_r, h*]; a step
//! that would leave the bracket is replaced by bisection, and the iteration stops when a step is
//! below `NEWTON_TOLERANCE` x (1 + |h|) or after `NEWTON_STEPS` steps.

use crate::error::{check, KernelError, KernelResult};
use crate::grid::Grid;
use crate::levels::Levels;
use crate::pow::pow;
use crate::ffi::views::atomic_f64;
use crate::team::{spans, F64View};

pub const NEWTON_TOLERANCE: f64 = 1e-12;
pub const NEWTON_STEPS: usize = 100;

pub fn solve_cell(start: f64, below: f64, factor: f64, exponent: f64) -> f64 {
    if !(start > below) || !(factor > 0.0) {
        return start;
    }
    if exponent == 1.0 {
        return (start + factor * below) / (1.0 + factor);
    }
    let mut low = below;
    let mut high = start;
    let mut height = start;
    for _ in 0..NEWTON_STEPS {
        let rise = height - below;
        let power = pow(rise, exponent);
        let residual = height - start + factor * power;
        if residual > 0.0 {
            high = height;
        } else {
            low = height;
        }
        let mut next = f64::NAN;
        if rise > 0.0 {
            let slope = 1.0 + factor * exponent * power / rise;
            next = height - residual / slope;
        }
        if !(next >= low && next <= high) {
            next = 0.5 * (low + high);
        }
        let step = next - height;
        height = next;
        if step.abs() <= NEWTON_TOLERANCE * (1.0 + height.abs()) {
            break;
        }
    }
    height
}

pub struct Law {
    pub area_exponent: f64,
    pub slope_exponent: f64,
    pub dt: f64,
}

impl Law {
    pub fn check(&self) -> KernelResult<()> {
        check(self.area_exponent.is_finite() && (0.0..=10.0).contains(&self.area_exponent), || format!("the area exponent m must be in [0, 10], got {}", self.area_exponent))?;
        check(self.slope_exponent.is_finite() && self.slope_exponent > 0.0 && self.slope_exponent <= 10.0, || format!("the slope exponent n must be in (0, 10], got {}", self.slope_exponent))?;
        check(self.dt.is_finite() && self.dt >= 0.0, || format!("the time step must be finite and at least 0, got {}", self.dt))
    }
}

#[allow(clippy::too_many_arguments)]
pub fn incise(grid: &Grid, heights: &[f64], receivers: &[i32], levels: &Levels, area: &[f64], erodibility: &[f64], law: &Law, threads: usize, solved: &mut [f64]) -> KernelResult<()> {
    for (name, length) in [("heights", heights.len()), ("receivers", receivers.len()), ("area", area.len()), ("erodibility", erodibility.len()), ("solved", solved.len())] {
        grid.expect_len(name, length, 1)?;
    }
    law.check()?;
    let count = grid.count();
    let found = spans(count, threads, |_, cells| {
        for cell in cells {
            let receiver = receivers[cell];
            if receiver < -1 || receiver >= count as i32 || receiver == cell as i32 {
                return Err(KernelError::invalid(format!("cell {} has receiver {}, outside 0..{} and not -1", cell, receiver, count)));
            }
            if heights[cell].is_finite() && receiver >= 0 {
                if !(erodibility[cell].is_finite() && erodibility[cell] >= 0.0) {
                    return Err(KernelError::invalid(format!("erodibility of cell {} must be finite and at least 0, got {}", cell, erodibility[cell])));
                }
                if !(area[cell].is_finite() && area[cell] >= 0.0) {
                    return Err(KernelError::invalid(format!("area of cell {} must be finite and at least 0, got {}", cell, area[cell])));
                }
            }
        }
        Ok(())
    });
    found.into_iter().collect::<KernelResult<()>>()?;
    let mut factors = vec![0.0f64; count];
    crate::team::rows_mut(&mut factors, grid.columns, threads, |first, block| {
        for (offset, value) in block.iter_mut().enumerate() {
            let cell = first * grid.columns + offset;
            let receiver = receivers[cell];
            if receiver >= 0 && heights[cell].is_finite() {
                let distance = grid.distance(cell, receiver as usize);
                *value = erodibility[cell] * law.dt * pow(area[cell], law.area_exponent) / pow(distance, law.slope_exponent);
            }
        }
    });
    let factors: &[f64] = &factors;
    let heights_out = F64View(atomic_f64(solved)?);
    heights_out.fill_from(heights, threads);
    levels.sweep(threads, false, |cell| {
        let receiver = receivers[cell];
        let start = heights[cell];
        if receiver < 0 || !start.is_finite() {
            return;
        }
        let below = heights_out.get(receiver as usize);
        if !below.is_finite() {
            return;
        }
        heights_out.set(cell, solve_cell(start, below, factors[cell], law.slope_exponent));
    })?;
    Ok(())
}
