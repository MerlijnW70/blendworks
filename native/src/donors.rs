//! Receiver tables and their donor lists. A table has `width` slots per cell, cell-major
//! (slot k of cell c at c * width + k), each a cell index or -1. The donor list of a cell holds
//! the table entries (edges e = d * width + k) that point at it, in a fixed order: first the
//! donors among its neighbours, neighbour by neighbour in `grid::NEIGHBOURS` order and slot by
//! slot, then donors farther away (lake routing can join a pit to a distant pass) in ascending
//! edge order. Each cell gathers its own list, so the lists are built in parallel without
//! depending on the thread count.

use crate::error::{check, KernelError, KernelResult};
use crate::grid::Grid;
use crate::team::{rows_mut, span, spans};

pub fn check_table(grid: &Grid, receivers: &[i32], width: usize, threads: usize) -> KernelResult<()> {
    check(width >= 1 && width <= 8, || format!("a receiver table has 1 to 8 slots per cell, got {}", width))?;
    grid.expect_len("receivers", receivers.len(), width)?;
    let count = grid.count();
    check(count.checked_mul(width).map_or(false, |edges| edges <= i32::MAX as usize), || "the receiver table has more entries than the core indexes".to_string())?;
    let found = spans(count, threads, |_, cells| {
        for cell in cells {
            for slot in 0..width {
                let receiver = receivers[cell * width + slot];
                if receiver < -1 || receiver >= count as i32 {
                    return Err(KernelError::invalid(format!("cell {} has receiver {}, outside 0..{} and not -1", cell, receiver, count)));
                }
                if receiver == cell as i32 {
                    return Err(KernelError::cycle(format!("cell {} is its own receiver", cell)));
                }
                if receiver >= 0 && receivers[cell * width..cell * width + slot].contains(&receiver) {
                    return Err(KernelError::invalid(format!("cell {} names receiver {} twice", cell, receiver)));
                }
            }
        }
        Ok(())
    });
    found.into_iter().collect()
}

fn is_neighbour(grid: &Grid, cell: usize, other: usize) -> bool {
    let rows = (cell / grid.columns) as isize - (other / grid.columns) as isize;
    let columns = (cell % grid.columns) as isize - (other % grid.columns) as isize;
    rows.abs() <= 1 && columns.abs() <= 1 && (rows != 0 || columns != 0)
}

/// Edges whose receiver is not a neighbour, as (receiver, edge), sorted.
fn far_edges(grid: &Grid, receivers: &[i32], width: usize, threads: usize) -> Vec<(u32, u32)> {
    let parts = spans(grid.count(), threads, |_, cells| {
        let mut found = Vec::new();
        for cell in cells {
            for slot in 0..width {
                let receiver = receivers[cell * width + slot];
                if receiver >= 0 && !is_neighbour(grid, cell, receiver as usize) {
                    found.push((receiver as u32, (cell * width + slot) as u32));
                }
            }
        }
        found
    });
    let mut all: Vec<(u32, u32)> = parts.into_iter().flatten().collect();
    all.sort_unstable();
    all
}

#[inline(always)]
fn gather<F: FnMut(u32)>(grid: &Grid, receivers: &[i32], width: usize, far: &[(u32, u32)], cell: usize, mut take: F) {
    let target = cell as i32;
    grid.for_neighbours(cell, |_, other| {
        for slot in 0..width {
            if receivers[other * width + slot] == target {
                take((other * width + slot) as u32);
            }
        }
    });
    let first = far.partition_point(|(receiver, _)| (*receiver as usize) < cell);
    for (receiver, edge) in far[first..].iter() {
        if *receiver as usize != cell {
            break;
        }
        take(*edge);
    }
}

/// Fills `start` (count + 1 offsets) and `donors` (at least as many values as edges) and
/// returns the number of edges.
pub fn donor_lists(grid: &Grid, receivers: &[i32], width: usize, threads: usize, start: &mut [i32], donors: &mut [i32]) -> KernelResult<usize> {
    let count = grid.count();
    check(start.len() == count + 1, || format!("donor offsets must hold {} values, got {}", count + 1, start.len()))?;
    let far = far_edges(grid, receivers, width, threads);
    let columns = grid.columns;
    rows_mut(&mut start[..count], columns, threads, |first_row, block| {
        for (offset, value) in block.iter_mut().enumerate() {
            let mut found = 0i32;
            gather(grid, receivers, width, &far, first_row * columns + offset, |_| found += 1);
            *value = found;
        }
    });
    let parts = crate::team::parts(count, threads);
    let sums = spans(count, parts, |_, cells| start[cells].iter().map(|value| *value as i64).sum::<i64>());
    let mut bases = Vec::with_capacity(parts);
    let mut running = 0i64;
    for sum in sums.iter() {
        bases.push(running);
        running += sum;
    }
    let edges = running as usize;
    check(donors.len() >= edges, || format!("donors must hold at least {} values, got {}", edges, donors.len()))?;
    let mut blocks: Vec<(usize, i64, &mut [i32])> = Vec::with_capacity(parts);
    let mut rest = &mut start[..count];
    for (index, base) in bases.iter().enumerate() {
        let (block, tail) = rest.split_at_mut(span(count, parts, index).len());
        rest = tail;
        blocks.push((span(count, parts, index).start, *base, block));
    }
    crate::team::each_mut(&mut blocks, |(_, base, block)| {
        {
            let mut running = *base;
            for value in block.iter_mut() {
                let here = *value as i64;
                *value = running as i32;
                running += here;
            }
        }
    });
    start[count] = edges as i32;
    let start: &[i32] = start;
    let mut lists: Vec<(usize, &mut [i32])> = Vec::with_capacity(parts);
    let mut rest = &mut donors[..edges];
    for index in 0..parts {
        let cells = span(count, parts, index);
        let length = (start[cells.end] - start[cells.start]) as usize;
        let (block, tail) = rest.split_at_mut(length);
        rest = tail;
        lists.push((cells.start, block));
    }
    crate::team::each_mut(&mut lists, |(first, block)| {
        {
            let mut written = 0usize;
            let base = start[*first] as usize;
            let mut cell = *first;
            while written < block.len() {
                let mut position = start[cell] as usize - base;
                gather(grid, receivers, width, &far, cell, |edge| {
                    block[position] = edge as i32;
                    position += 1;
                });
                written = position;
                cell += 1;
            }
        }
    });
    Ok(edges)
}
