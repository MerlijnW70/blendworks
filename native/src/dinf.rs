//! D-infinity flow directions (Tarboton 1997, "A new method for the determination of flow
//! directions and upslope areas in grid digital elevation models", Water Resources Research
//! 33(2):309-319). Each cell's eight triangular facets are formed by the cell, a side neighbour and
//! the diagonal neighbour next to it. On a facet the plane's steepest descent has slope
//! s = sqrt(s1^2 + s2^2) and angle r = atan(s2 / s1) from the side direction, with
//! s1 = (e0 - e1) / d1 and s2 = (e1 - e2) / d2; an angle outside [0, atan(d2 / d1)] is clamped to
//! the facet's edge, with the slope along that edge. The steepest facet (the first in slot order on
//! a tie) gives the direction, and the flow is shared between its two neighbours in proportion to
//! the angle: the diagonal takes r / r_max, the side neighbour the rest. A cell with no descending
//! facet has no receiver. The arctangent is built from additions, multiplications and divisions
//! only, so the shares are the same bits on every platform. Rows run in parallel; each cell is
//! computed alone.

use crate::error::KernelResult;
use crate::grid::{Grid, NODATA, OUTLET};
use crate::team::rows_mut2;

/// Facets as (side slot, diagonal slot) in the grid's neighbour order.
pub const FACETS: [(usize, usize); 8] = [(0, 1), (2, 1), (2, 3), (4, 3), (4, 5), (6, 5), (6, 7), (0, 7)];
const ATAN_TERMS: usize = 24;
const QUARTER_PI: f64 = 0.785_398_163_397_448_3;
const HALF_PI: f64 = 1.570_796_326_794_896_6;
const TAN_EIGHTH_PI: f64 = 0.414_213_562_373_095_03;

/// atan(t) for t >= 0: reduced to |u| <= tan(pi/8) by atan(t) = pi/2 - atan(1/t) and
/// atan(t) = pi/4 + atan((t - 1)/(t + 1)), then the series u - u^3/3 + u^5/5 - ... in Horner form.
pub fn atan_positive(t: f64) -> f64 {
    if t > 1.0 {
        return HALF_PI - atan_positive(1.0 / t);
    }
    if t > TAN_EIGHTH_PI {
        return QUARTER_PI + atan_series((t - 1.0) / (t + 1.0));
    }
    atan_series(t)
}

fn atan_series(u: f64) -> f64 {
    let square = u * u;
    let mut sum = 0.0;
    for term in (0..ATAN_TERMS).rev() {
        let coefficient = if term % 2 == 0 { 1.0 } else { -1.0 } / (2 * term + 1) as f64;
        sum = coefficient + square * sum;
    }
    u * sum
}

/// The two receivers of a cell and their shares, from its own height and its neighbours'
/// (f64::NAN for a neighbour outside the grid or without data).
pub fn facet_flow(here: f64, around: &[f64; 8], distances: &[f64; 8]) -> Option<((usize, f64), (usize, f64))> {
    let mut best: Option<(f64, usize, usize, f64, f64)> = None;
    for (side, diagonal) in FACETS.iter() {
        let (e1, e2) = (around[*side], around[*diagonal]);
        if e1.is_nan() || e2.is_nan() {
            continue;
        }
        let d1 = distances[*side];
        let diagonal_distance = distances[*diagonal];
        let d2 = (diagonal_distance * diagonal_distance - d1 * d1).sqrt();
        let widest = atan_positive(d2 / d1);
        let s1 = (here - e1) / d1;
        let s2 = (e1 - e2) / d2;
        let (angle, slope) = if s1 > 0.0 && s2 > 0.0 {
            let angle = atan_positive(s2 / s1);
            if angle > widest {
                (widest, (here - e2) / diagonal_distance)
            } else {
                (angle, (s1 * s1 + s2 * s2).sqrt())
            }
        } else if s1 > 0.0 {
            (0.0, s1)
        } else {
            (widest, (here - e2) / diagonal_distance)
        };
        if slope > 0.0 && best.map_or(true, |found| slope > found.0) {
            best = Some((slope, *side, *diagonal, angle, widest));
        }
    }
    best.map(|(_, side, diagonal, angle, widest)| {
        let share = angle / widest;
        ((side, 1.0 - share), (diagonal, share))
    })
}

/// Writes the D-infinity receivers into `table` and their shares into `shares`, eight slots per
/// cell in the grid's neighbour order, -1 and 0 in unused slots.
pub fn dinf(grid: &Grid, heights: &[f64], threads: usize, table: &mut [i32], shares: &mut [f64]) -> KernelResult<()> {
    grid.expect_len("heights", heights.len(), 1)?;
    grid.expect_len("receiver table", table.len(), 8)?;
    grid.expect_len("shares", shares.len(), 8)?;
    let status = grid.status(heights, threads);
    let distances = grid.distances();
    let columns = grid.columns;
    rows_mut2(table, columns * 8, shares, columns * 8, threads, |first_row, table_block, share_block| {
        table_block.iter_mut().for_each(|value| *value = -1);
        share_block.iter_mut().for_each(|value| *value = 0.0);
        for offset in 0..table_block.len() / 8 {
            let cell = first_row * columns + offset;
            if status[cell] == NODATA || status[cell] == OUTLET {
                continue;
            }
            let mut around = [f64::NAN; 8];
            let mut index = [usize::MAX; 8];
            grid.for_neighbours(cell, |slot, other| {
                if status[other] != NODATA {
                    around[slot] = heights[other];
                    index[slot] = other;
                }
            });
            if let Some(((side, side_share), (diagonal, diagonal_share))) = facet_flow(heights[cell], &around, &distances) {
                for (slot, share) in [(side, side_share), (diagonal, diagonal_share)] {
                    if share > 0.0 {
                        table_block[offset * 8 + slot] = index[slot] as i32;
                        share_block[offset * 8 + slot] = share;
                    }
                }
            }
        }
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_arctangent_matches_the_system_one_closely() {
        for step in 0..2000 {
            let t = step as f64 * 0.01;
            assert!((atan_positive(t) - t.atan()).abs() < 1e-15, "{}", t);
        }
    }

    #[test]
    fn a_plane_sends_its_flow_along_its_true_direction() {
        let grid = Grid::new(5, 5, 1.0, 1.0, 0).expect("grid");
        let angle = 0.3f64;
        let heights: Vec<f64> = (0..25).map(|cell| {
            let (row, column) = ((cell / 5) as f64, (cell % 5) as f64);
            -(column * angle.cos() + row * angle.sin())
        }).collect();
        let mut table = vec![0i32; 200];
        let mut shares = vec![0.0; 200];
        dinf(&grid, &heights, 1, &mut table, &mut shares).expect("dinf");
        let centre = 12 * 8;
        assert_eq!(table[centre], 13);
        assert_eq!(table[centre + 1], 18);
        assert!((shares[centre + 1] - angle / QUARTER_PI).abs() < 1e-12, "{}", shares[centre + 1]);
        assert!((shares[centre] + shares[centre + 1] - 1.0).abs() < 1e-15);
    }
}
