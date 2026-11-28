//! Threshold hillslopes: where rock uplift outpaces soil transport, hillslopes are cut back by
//! landsliding to a critical angle and stand as planes near it (Burbank et al. 1996, Nature
//! 379:505-510; Montgomery 2001, American Journal of Science 301:432-454). The surface is lowered
//! until its gradient nowhere exceeds the cell's critical tangent s: out = min(h, u), where u solves
//! the eikonal equation |grad u| = s from the cells that keep their heights. It is solved by fast
//! marching (Sethian 1996, PNAS 93:1591-1595): cells are finished in increasing order of (out, cell)
//! (every cell's own height sorted once, merged with a priority queue of the lowered values, so the
//! queue only holds the marching front), and a neighbour's value comes from its finished neighbours along x and
//! y by the first-order upwind quadratic ((u - a)/dx)^2 + ((u - b)/dy)^2 = s^2. Unlike a path cost
//! over the eight neighbours, whose cones are octagons with faces along the grid, the solution is
//! isotropic, so threshold planes do not follow the grid directions. Each value comes from one fixed
//! sequence of operations, so the result depends only on the input. Outlets and no-data cells keep
//! their heights. The queue is one sequence of pops, so the kernel runs on one thread.

use std::cmp::Ordering;
use std::collections::BinaryHeap;

use crate::error::{check, KernelResult};
use crate::grid::{Grid, INTERIOR, NODATA};

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

/// The upwind value of a cell from the lowest finished neighbour along x (a) and along y (b),
/// either possibly infinite, at slope `s` with spacings `dx` and `dy`.
pub fn upwind(a: f64, b: f64, s: f64, dx: f64, dy: f64) -> f64 {
    let along_x = a + s * dx;
    let along_y = b + s * dy;
    if !a.is_finite() || !b.is_finite() {
        return if along_x < along_y { along_x } else { along_y };
    }
    let wx = 1.0 / (dx * dx);
    let wy = 1.0 / (dy * dy);
    let half = a * wx + b * wy;
    let total = wx + wy;
    let discriminant = half * half - total * (a * a * wx + b * b * wy - s * s);
    if discriminant >= 0.0 {
        let u = (half + discriminant.sqrt()) / total;
        if u >= a && u >= b {
            return u;
        }
    }
    if along_x < along_y {
        along_x
    } else {
        along_y
    }
}

/// The order-preserving bits of a float: unsigned order is the IEEE total order.
fn ordered_bits(value: f64) -> u64 {
    let bits = value.to_bits();
    if bits >> 63 == 1 {
        !bits
    } else {
        bits | (1u64 << 63)
    }
}

/// The valid cells in increasing order of (height, cell): a stable radix sort of the height bits in four passes
/// of 16 bits over the cells in index order, so equal heights keep index order.
fn sorted_cells(heights: &[f64], status: &[u8]) -> Vec<u32> {
    let mut cells: Vec<u32> = (0..heights.len() as u32).filter(|cell| status[*cell as usize] != NODATA).collect();
    let keys: Vec<u64> = heights.iter().map(|height| ordered_bits(*height)).collect();
    let mut spare = vec![0u32; cells.len()];
    for pass in 0..4 {
        let shift = pass * 16;
        let mut counts = vec![0usize; 65537];
        for cell in cells.iter() {
            counts[((keys[*cell as usize] >> shift) & 0xFFFF) as usize + 1] += 1;
        }
        for digit in 0..65536 {
            counts[digit + 1] += counts[digit];
        }
        for cell in cells.iter() {
            let digit = ((keys[*cell as usize] >> shift) & 0xFFFF) as usize;
            spare[counts[digit]] = *cell;
            counts[digit] += 1;
        }
        std::mem::swap(&mut cells, &mut spare);
    }
    cells
}

/// Writes the threshold surface into `out` and returns the number of cells lowered.
pub fn threshold(grid: &Grid, heights: &[f64], tangent: &[f64], out: &mut [f64]) -> KernelResult<usize> {
    grid.expect_len("heights", heights.len(), 1)?;
    grid.expect_len("critical tangent", tangent.len(), 1)?;
    grid.expect_len("out", out.len(), 1)?;
    let count = grid.count();
    check((0..count).all(|cell| !heights[cell].is_finite() || (tangent[cell].is_finite() && tangent[cell] >= 0.0)),
          || "the critical tangent must be finite and at least 0 on every valid cell".to_string())?;
    let status = grid.status(heights, 1);
    let (rows, columns) = (grid.rows, grid.columns);
    let (dx, dy) = (grid.spacing_x, grid.spacing_y);
    out.copy_from_slice(heights);
    let mut done = vec![false; count];
    let mut lowered = vec![false; count];
    let seeds: Vec<Entry> = sorted_cells(heights, &status).into_iter().map(|cell| Entry { height: heights[cell as usize], cell: cell as usize }).collect();
    let mut next_seed = 0usize;
    let mut open: BinaryHeap<Entry> = BinaryHeap::new();
    let lowest = |out: &[f64], done: &[bool], first: Option<usize>, second: Option<usize>| -> f64 {
        let mut found = f64::INFINITY;
        for other in [first, second].iter().flatten() {
            if done[*other] && out[*other] < found {
                found = out[*other];
            }
        }
        found
    };
    loop {
        let from_seeds = match (seeds.get(next_seed), open.peek()) {
            (Some(seed), Some(top)) => seed >= top,

            (Some(_), None) => true,
            (None, Some(_)) => false,
            (None, None) => break,
        };
        let entry = if from_seeds {
            next_seed += 1;
            seeds[next_seed - 1]
        } else {
            open.pop().expect("a queued cell")
        };
        let cell = entry.cell;
        if done[cell] || entry.height != out[cell] {
            continue;
        }
        done[cell] = true;
        let (row, column) = (cell / columns, cell % columns);
        let around = [
            if column + 1 < columns { Some(cell + 1) } else { None },
            if row + 1 < rows { Some(cell + columns) } else { None },
            if column > 0 { Some(cell - 1) } else { None },
            if row > 0 { Some(cell - columns) } else { None },
        ];
        for other in around.iter().flatten() {
            let other = *other;
            if done[other] || status[other] != INTERIOR {
                continue;
            }
            let (r, c) = (other / columns, other % columns);
            let a = lowest(out, &done, if c > 0 { Some(other - 1) } else { None }, if c + 1 < columns { Some(other + 1) } else { None });
            let b = lowest(out, &done, if r > 0 { Some(other - columns) } else { None }, if r + 1 < rows { Some(other + columns) } else { None });
            let reach = upwind(a, b, tangent[other], dx, dy);
            if reach < out[other] {
                out[other] = reach;
                lowered[other] = true;
                open.push(Entry { height: reach, cell: other });
            }
        }
    }
    Ok(lowered.iter().filter(|value| **value).count())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_spike_is_cut_back_to_the_critical_slope_and_lower_ground_is_kept() {
        let grid = Grid::new(5, 5, 10.0, 10.0, 0).expect("grid");
        let mut heights = vec![0.0; 25];
        heights[12] = 100.0;
        heights[0] = -3.0;
        let tangent = vec![0.5; 25];
        let mut out = vec![0.0; 25];
        let lowered = threshold(&grid, &heights, &tangent, &mut out).expect("threshold");
        assert_eq!(lowered, 1);
        assert!((out[12] - 5.0 / 2f64.sqrt()).abs() < 1e-12, "{}", out[12]);
        assert_eq!(out[0], -3.0);
        assert!(out.iter().zip(heights.iter()).all(|(after, before)| after <= before));
    }

    #[test]
    fn no_step_along_x_or_y_exceeds_the_critical_tangent() {
        let grid = Grid::new(9, 11, 10.0, 10.0, 0).expect("grid");
        let mut seed = 7u64;
        let heights: Vec<f64> = (0..99).map(|_| {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            (seed >> 40) as f64 / (1u64 << 24) as f64 * 80.0
        }).collect();
        let tangent: Vec<f64> = (0..99).map(|cell| 0.4 + (cell % 3) as f64 * 0.1).collect();
        let mut out = vec![0.0; 99];
        threshold(&grid, &heights, &tangent, &mut out).expect("threshold");
        for cell in 0..99 {
            for other in [cell + 1, cell + 11] {
                if other < 99 && (other != cell + 1 || other % 11 != 0) {
                    let (high, low) = if out[cell] > out[other] { (cell, other) } else { (other, cell) };
                    assert!(out[high] - out[low] <= tangent[high] * 10.0 + 1e-9, "{} above {}", high, low);
                }
            }
        }
    }

    #[test]
    fn a_cone_from_one_low_cell_is_round_not_octagonal() {
        let grid = Grid::new(41, 41, 1.0, 1.0, 0).expect("grid");
        let mut heights = vec![1000.0; 41 * 41];
        heights[20 * 41 + 20] = 0.0;
        let mut out = vec![0.0; 41 * 41];
        threshold(&grid, &heights, &vec![1.0; 41 * 41], &mut out).expect("threshold");
        let straight = out[20 * 41 + 40];
        let diagonal = out[(20 + 14) * 41 + 20 + 14];
        assert!((straight - 20.0).abs() < 1e-9);
        assert!((diagonal - 14.0 * 2f64.sqrt()).abs() < 1.0, "{}", diagonal);
    }
}
