//! Thermal slides: slope-limited mass transfer (Musgrave, Kolb & Mace 1989; Olsen 2004) with a
//! critical angle per cell. Material on a cell stands at most at its own critical tangent:
//! towards each valid neighbour the excess is e = (h - h_n) - tan(c) x distance. A cell with
//! positive excesses moves rate x max(e) / 2 of material, shared among those neighbours in
//! proportion to their excess, so a single step never reverses a slope. Every iteration first
//! computes the moving fraction f = rate x max(e) / (2 x sum(e)) of every cell from the same
//! heights (Jacobi), then each cell gathers h' = h - sum_n f e_n + sum_n f_n e_(n to cell), in
//! neighbour order. Outlets keep their heights, so what slides onto them leaves the grid;
//! no-data cells take no part. Mass is conserved otherwise.

use crate::error::{check, KernelResult};
use crate::grid::{Grid, INTERIOR, OPPOSITE};
use crate::team::{all_of, copy_into, rows_mut};

#[inline(always)]
fn excess(here: f64, there: f64, tangent: f64, distance: f64) -> f64 {
    (here - there) - tangent * distance
}

pub fn slide(grid: &Grid, heights: &[f64], tangent: &[f64], rate: f64, iterations: usize, threads: usize, out: &mut [f64]) -> KernelResult<()> {
    grid.expect_len("heights", heights.len(), 1)?;
    grid.expect_len("critical tangent", tangent.len(), 1)?;
    grid.expect_len("out", out.len(), 1)?;
    check(rate.is_finite() && rate > 0.0 && rate <= 1.0, || format!("the slide rate must be in (0, 1], got {}", rate))?;
    check(iterations <= 1_000_000, || format!("at most 1000000 iterations, got {}", iterations))?;
    check(all_of(grid.count(), threads, |cell| !heights[cell].is_finite() || (tangent[cell].is_finite() && tangent[cell] >= 0.0)), || "the critical tangent must be finite and at least 0 on every valid cell".to_string())?;
    let status = grid.status(heights, threads);
    let distances = grid.distances();
    let columns = grid.columns;
    let mut scratch = vec![0.0; grid.count()];
    let mut fraction = vec![0.0; grid.count()];
    if iterations == 0 {
        copy_into(heights, out, threads);
        return Ok(());
    }
    for iteration in 0..iterations {
        let into_out = (iterations - iteration) % 2 == 1;
        let (source, next): (&[f64], &mut [f64]) = match (iteration, into_out) {
            (0, true) => (heights, &mut *out),
            (0, false) => (heights, &mut scratch[..]),
            (_, true) => (&scratch[..], &mut *out),
            (_, false) => (&*out, &mut scratch[..]),
        };
        rows_mut(&mut fraction, columns, threads, |first, block| {
            for (offset, value) in block.iter_mut().enumerate() {
                let cell = first * columns + offset;
                *value = 0.0;
                if status[cell] != INTERIOR {
                    continue;
                }
                let here = source[cell];
                let mut total = 0.0;
                let mut largest = 0.0;
                grid.for_neighbours(cell, |slot, other| {
                    let there = source[other];
                    if there.is_finite() {
                        let found = excess(here, there, tangent[cell], distances[slot]);
                        if found > 0.0 {
                            total += found;
                            if found > largest {
                                largest = found;
                            }
                        }
                    }
                });
                if total > 0.0 {
                    *value = rate * largest / (2.0 * total);
                }
            }
        });
        let fraction: &[f64] = &fraction;
        rows_mut(next, columns, threads, |first, block| {
            for (offset, value) in block.iter_mut().enumerate() {
                let cell = first * columns + offset;
                let here = source[cell];
                *value = here;
                if status[cell] != INTERIOR {
                    continue;
                }
                let mut sent = 0.0;
                let mut received = 0.0;
                grid.for_neighbours(cell, |slot, other| {
                    let there = source[other];
                    if !there.is_finite() {
                        return;
                    }
                    let outgoing = excess(here, there, tangent[cell], distances[slot]);
                    if outgoing > 0.0 {
                        sent += fraction[cell] * outgoing;
                    }
                    let incoming = excess(there, here, tangent[other], distances[OPPOSITE[slot]]);
                    if incoming > 0.0 {
                        received += fraction[other] * incoming;
                    }
                });
                *value = here - sent + received;
            }
        });
    }
    Ok(())
}
