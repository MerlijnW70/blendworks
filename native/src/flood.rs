//! Priority-Flood (Barnes, Lehman & Mulla 2014, "Priority-flood: an optimal depression-filling
//! and watershed-labeling algorithm for digital elevation models", Computers & Geosciences
//! 62:117-127, Algorithms 2 and 3). The outlets seed a priority queue ordered by (height, cell);
//! a plain first-in first-out pit queue is served first whenever it holds cells. Popping a cell
//! closes its open neighbours: a neighbour at or below the level of the popped cell is raised to
//! that level and joins the pit queue, any other joins the priority queue. The level is the
//! popped height itself (filling flat) or, with epsilon, the next float above it, so the filled
//! surface drains everywhere. Cells no outlet reaches keep their heights. The queue is one
//! sequence of pops, so the kernel runs on one thread.

use std::cmp::Ordering;
use std::collections::{BinaryHeap, VecDeque};

use crate::error::KernelResult;
use crate::grid::{Grid, NODATA, OUTLET};

#[derive(Debug, Clone, Copy, PartialEq)]
struct Entry {
    height: f64,
    cell: usize,
}

impl Eq for Entry {}

impl Ord for Entry {
    fn cmp(&self, other: &Self) -> Ordering {
        other.height.total_cmp(&self.height).then_with(|| other.cell.cmp(&self.cell))
    }
}

impl PartialOrd for Entry {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// The next float above `value` (IEEE nextUp).
pub fn next_up(value: f64) -> f64 {
    if value.is_nan() || value == f64::INFINITY {
        return value;
    }
    if value == 0.0 {
        return f64::from_bits(1);
    }
    let bits = value.to_bits();
    if value > 0.0 {
        f64::from_bits(bits + 1)
    } else {
        f64::from_bits(bits - 1)
    }
}

/// Fills `filled` and returns the number of cells raised.
pub fn priority_flood(grid: &Grid, heights: &[f64], epsilon: bool, filled: &mut [f64]) -> KernelResult<usize> {
    grid.expect_len("heights", heights.len(), 1)?;
    grid.expect_len("filled", filled.len(), 1)?;
    let count = grid.count();
    let status = grid.status(heights, 1);
    filled.copy_from_slice(heights);
    let mut closed = vec![false; count];
    let mut open = BinaryHeap::new();
    let mut pit = VecDeque::new();
    for cell in 0..count {
        if status[cell] == OUTLET {
            closed[cell] = true;
            open.push(Entry { height: heights[cell], cell });
        }
    }
    let mut raised = 0usize;
    loop {
        let cell = if let Some(cell) = pit.pop_front() {
            cell
        } else if let Some(entry) = open.pop() {
            entry.cell
        } else {
            break;
        };
        let level = if epsilon { next_up(filled[cell]) } else { filled[cell] };
        grid.for_neighbours(cell, |_, other| {
            if closed[other] || status[other] == NODATA {
                return;
            }
            closed[other] = true;
            if filled[other] <= level {
                if filled[other] < level {
                    raised += 1;
                }
                filled[other] = level;
                pit.push_back(other);
            } else {
                open.push(Entry { height: filled[other], cell: other });
            }
        });
    }
    Ok(raised)
}
