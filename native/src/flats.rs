//! Drainage across flats (Barnes, Lehman & Mulla 2014, "An efficient assignment of drainage
//! direction over flat surfaces in raster digital elevation models", Computers & Geosciences
//! 62:128-135). A flat cell is an interior cell without a lower neighbour that has a
//! neighbour of the same height. Low edges are draining cells (with a receiver, or outlets)
//! beside such a cell; high edges are flat cells beside higher ground. Each flat reached from a
//! low edge is labelled by a flood fill over equal heights; a breadth-first pass away from
//! the high edges and one towards the low edges build an increment field
//! 2 x (steps from the low edge) + (largest away count of the flat - steps from the high edge),
//! and every flat cell drains to the neighbour of its label with the smallest increment, ties to
//! the first in neighbour order. Flats no low edge reaches are depressions and keep -1.
//! The passes are sequential first-in first-out queues, as in the paper.

use std::collections::VecDeque;

use crate::grid::{Grid, INTERIOR, OUTLET};
use crate::team::rows_mut;

const NO_LABEL: u32 = 0;

fn is_flat(grid: &Grid, heights: &[f64], status: &[u8], receivers: &[i32], cell: usize) -> bool {
    if status[cell] != INTERIOR || receivers[cell] >= 0 {
        return false;
    }
    let here = heights[cell];
    let mut equal = false;
    grid.for_neighbours(cell, |_, other| equal |= heights[other] == here);
    equal
}

/// Gives flat cells their receivers in place and returns how many it gave.
pub fn resolve_flats(grid: &Grid, heights: &[f64], status: &[u8], receivers: &mut [i32], threads: usize) -> usize {
    let count = grid.count();
    let mut flat = vec![false; count];
    let columns = grid.columns;
    let given: &[i32] = receivers;
    rows_mut(&mut flat, columns, threads, |first_row, block| {
        for (offset, value) in block.iter_mut().enumerate() {
            *value = is_flat(grid, heights, status, given, first_row * columns + offset);
        }
    });
    if !flat.iter().any(|value| *value) {
        return 0;
    }
    let drains = |cell: usize, receivers: &[i32]| receivers[cell] >= 0 || status[cell] == OUTLET;
    let mut low_edges = VecDeque::new();
    let mut high_edges = VecDeque::new();
    for cell in 0..count {
        let here = heights[cell];
        if !here.is_finite() {
            continue;
        }
        if drains(cell, receivers) {
            let mut beside_flat = false;
            grid.for_neighbours(cell, |_, other| beside_flat |= flat[other] && heights[other] == here);
            if beside_flat {
                low_edges.push_back(cell);
            }
        } else if flat[cell] {
            let mut beside_higher = false;
            grid.for_neighbours(cell, |_, other| beside_higher |= heights[other].is_finite() && heights[other] > here);
            if beside_higher {
                high_edges.push_back(cell);
            }
        }
    }
    let mut labels = vec![NO_LABEL; count];
    let mut next_label = 1u32;
    let mut fill = VecDeque::new();
    for start in low_edges.iter() {
        if labels[*start] != NO_LABEL {
            continue;
        }
        let height = heights[*start];
        labels[*start] = next_label;
        fill.push_back(*start);
        while let Some(cell) = fill.pop_front() {
            grid.for_neighbours(cell, |_, other| {
                if labels[other] == NO_LABEL && heights[other] == height {
                    labels[other] = next_label;
                    fill.push_back(other);
                }
            });
        }
        next_label += 1;
    }
    high_edges.retain(|cell| labels[*cell] != NO_LABEL);
    let mut mask = vec![0i64; count];
    let mut flat_height = vec![0i64; next_label as usize];
    away_from_higher(grid, &labels, &flat, high_edges, &mut mask, &mut flat_height);
    towards_lower(grid, &labels, &flat, low_edges, &mut mask, &flat_height);
    let mut given = 0usize;
    for cell in 0..count {
        if !flat[cell] || labels[cell] == NO_LABEL {
            continue;
        }
        let mut best = mask[cell];
        let mut chosen = -1i32;
        grid.for_neighbours(cell, |_, other| {
            if labels[other] == labels[cell] && mask[other] < best {
                best = mask[other];
                chosen = other as i32;
            }
        });
        if chosen >= 0 {
            receivers[cell] = chosen;
            given += 1;
        }
    }
    given
}

fn away_from_higher(grid: &Grid, labels: &[u32], flat: &[bool], mut queue: VecDeque<usize>, mask: &mut [i64], flat_height: &mut [i64]) {
    let mut loops = 1i64;
    let mut next = VecDeque::new();
    while !queue.is_empty() {
        while let Some(cell) = queue.pop_front() {
            if mask[cell] > 0 {
                continue;
            }
            mask[cell] = loops;
            flat_height[labels[cell] as usize] = loops;
            grid.for_neighbours(cell, |_, other| {
                if labels[other] == labels[cell] && flat[other] {
                    next.push_back(other);
                }
            });
        }
        std::mem::swap(&mut queue, &mut next);
        loops += 1;
    }
}

fn towards_lower(grid: &Grid, labels: &[u32], flat: &[bool], mut queue: VecDeque<usize>, mask: &mut [i64], flat_height: &[i64]) {
    for value in mask.iter_mut() {
        *value = -*value;
    }
    let mut loops = 1i64;
    let mut next = VecDeque::new();
    while !queue.is_empty() {
        while let Some(cell) = queue.pop_front() {
            if mask[cell] > 0 {
                continue;
            }
            if mask[cell] < 0 {
                mask[cell] = flat_height[labels[cell] as usize] + mask[cell] + 2 * loops;
            } else {
                mask[cell] = 2 * loops;
            }
            grid.for_neighbours(cell, |_, other| {
                if labels[other] == labels[cell] && flat[other] {
                    next.push_back(other);
                }
            });
        }
        std::mem::swap(&mut queue, &mut next);
        loops += 1;
    }
}
