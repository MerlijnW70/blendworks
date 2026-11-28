//! Flow receivers. D8 (O'Callaghan & Mark 1984): a cell drains to the neighbour with the
//! largest drop per distance, ties to the first in `grid::NEIGHBOURS` order. Multiple flow
//! (Freeman 1991): every strictly lower neighbour receives a share proportional to
//! (drop / distance)^p. Cells on flats that touch lower ground drain across them by the flat
//! resolution of Barnes, Lehman & Mulla (2014), in `flats`; outlets, no-data cells and cells
//! with no way down (pits and closed flats) have no receiver (-1).

use crate::error::{check, KernelResult};
use crate::flats::resolve_flats;
use crate::grid::{Grid, INTERIOR};
use crate::pow::pow;
use crate::team::{rows_mut, rows_mut2};

pub const WIDTH_MFD: usize = 8;

fn steepest(grid: &Grid, heights: &[f64], distances: &[f64; 8], cell: usize) -> i32 {
    let here = heights[cell];
    let mut best = 0.0;
    let mut found = -1i32;
    grid.for_neighbours(cell, |slot, other| {
        let there = heights[other];
        let drop = (here - there) / distances[slot];
        if there.is_finite() && drop > best {
            best = drop;
            found = other as i32;
        }
    });
    found
}

/// Steepest-descent receivers with flats resolved. Returns the number of flat cells that were
/// given a receiver by the flat resolution.
pub fn d8(grid: &Grid, heights: &[f64], threads: usize, receivers: &mut [i32]) -> KernelResult<usize> {
    grid.expect_len("heights", heights.len(), 1)?;
    grid.expect_len("receivers", receivers.len(), 1)?;
    let status = grid.status(heights, threads);
    let distances = grid.distances();
    let columns = grid.columns;
    rows_mut(receivers, columns, threads, |first_row, block| {
        for (offset, receiver) in block.iter_mut().enumerate() {
            let cell = first_row * columns + offset;
            *receiver = if status[cell] == INTERIOR { steepest(grid, heights, &distances, cell) } else { -1 };
        }
    });
    Ok(resolve_flats(grid, heights, &status, receivers, threads))
}

/// Multiple-flow receivers, cell-major: slot k of cell c at c * 8 + k, filled in neighbour order
/// and padded with -1 and share 0. A flat cell drained by the flat resolution sends everything
/// to its D8 receiver.
pub fn mfd(grid: &Grid, heights: &[f64], exponent: f64, threads: usize, receivers: &mut [i32], shares: &mut [f64]) -> KernelResult<usize> {
    grid.expect_len("heights", heights.len(), 1)?;
    grid.expect_len("receivers", receivers.len(), WIDTH_MFD)?;
    grid.expect_len("shares", shares.len(), WIDTH_MFD)?;
    check(exponent.is_finite() && exponent > 0.0 && exponent <= 100.0, || format!("the flow exponent p must be a finite number in (0, 100], got {}", exponent))?;
    let mut single = vec![-1i32; grid.count()];
    let resolved = d8(grid, heights, threads, &mut single)?;
    let distances = grid.distances();
    let columns = grid.columns;
    rows_mut2(receivers, columns * WIDTH_MFD, shares, columns * WIDTH_MFD, threads, |first_row, block_receivers, block_shares| {
        for offset in 0..block_receivers.len() / WIDTH_MFD {
            let cell = first_row * columns + offset;
            let out_receivers = &mut block_receivers[offset * WIDTH_MFD..(offset + 1) * WIDTH_MFD];
            let out_shares = &mut block_shares[offset * WIDTH_MFD..(offset + 1) * WIDTH_MFD];
            spread(grid, heights, exponent, &distances, cell, single[cell], out_receivers, out_shares);
        }
    });
    Ok(resolved)
}

#[allow(clippy::too_many_arguments)]
fn spread(grid: &Grid, heights: &[f64], exponent: f64, distances: &[f64; 8], cell: usize, single: i32, receivers: &mut [i32], shares: &mut [f64]) {
    for slot in 0..WIDTH_MFD {
        receivers[slot] = -1;
        shares[slot] = 0.0;
    }
    if single < 0 {
        return;
    }
    let here = heights[cell];
    let mut weights = [0.0f64; 8];
    let mut targets = [-1i32; 8];
    let mut used = 0usize;
    let mut total = 0.0;
    grid.for_neighbours(cell, |slot, other| {
        let there = heights[other];
        let drop = (here - there) / distances[slot];
        if there.is_finite() && drop > 0.0 {
            let weight = pow(drop, exponent);
            weights[used] = weight;
            targets[used] = other as i32;
            total += weight;
            used += 1;
        }
    });
    if used == 0 || !(total > 0.0) {
        receivers[0] = single;
        shares[0] = 1.0;
        return;
    }
    for index in 0..used {
        receivers[index] = targets[index];
        shares[index] = weights[index] / total;
    }
}
