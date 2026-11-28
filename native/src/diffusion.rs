//! Hillslope diffusion, dh/dt = div(K grad h), by alternating-direction implicit splitting in
//! its locally one-dimensional form (Yanenko 1971): one implicit step along the rows, then one
//! along the columns, each a tridiagonal system solved by the Thomas algorithm. Each sweep is
//! backward Euler in one direction, so a step is unconditionally stable, keeps the maximum
//! principle and damps every mode, the short ones most, at any time step; the price is first
//! order accuracy in time. (Peaceman-Rachford ADI is second order but leaves the shortest
//! modes undamped at long steps.) Faces between two valid cells carry K, the mean of their
//! cells' values; faces to no-data cells and the grid border carry none (no flux); outlets keep
//! their heights (base level).
//! Non-linear diffusion (Roering, Kirchner & Dietrich 1999, Water Resources Research
//! 35(3):853-870): the flux is K grad h / (1 - (|grad h| / Sc)^2). Each Picard iteration
//! evaluates that factor on every face from the latest iterate, with |grad h| / Sc capped at
//! `max_ratio`, and repeats the implicit step from the start heights.

use crate::error::{check, KernelResult};
use crate::grid::{Grid, INTERIOR};
use crate::team::{all_of, rows_mut, span};

#[derive(Clone, Copy)]
pub struct Critical {
    pub slope: f64,
    pub max_ratio: f64,
    pub iterations: usize,
}

pub struct Faces {
    east: Vec<f64>,
    south: Vec<f64>,
}

fn valid(heights: &[f64], cell: usize) -> bool {
    heights[cell].is_finite()
}

fn cross_gradient(grid: &Grid, heights: &[f64], cell: usize, along_rows: bool) -> f64 {
    let (row, column) = (cell / grid.columns, cell % grid.columns);
    let (before, after, spacing) = if along_rows {
        (if column > 0 { Some(cell - 1) } else { None }, if column + 1 < grid.columns { Some(cell + 1) } else { None }, grid.spacing_x)
    } else {
        (if row > 0 { Some(cell - grid.columns) } else { None }, if row + 1 < grid.rows { Some(cell + grid.columns) } else { None }, grid.spacing_y)
    };
    let before = before.filter(|other| valid(heights, *other));
    let after = after.filter(|other| valid(heights, *other));
    match (before, after) {
        (Some(low), Some(high)) => (heights[high] - heights[low]) / (2.0 * spacing),
        (None, Some(high)) => (heights[high] - heights[cell]) / spacing,
        (Some(low), None) => (heights[cell] - heights[low]) / spacing,
        (None, None) => 0.0,
    }
}

fn roering(gradient_squared: f64, critical: &Critical) -> f64 {
    let mut ratio = gradient_squared.sqrt() / critical.slope;
    if ratio > critical.max_ratio {
        ratio = critical.max_ratio;
    }
    1.0 / (1.0 - ratio * ratio)
}

/// Face conductances dt K / spacing^2 for the faces east and south of every cell.
fn fill_faces(grid: &Grid, current: &[f64], diffusivity: &[f64], dt: f64, critical: Option<&Critical>, threads: usize, faces: &mut Faces) {
    let columns = grid.columns;
    let scale_x = dt / (grid.spacing_x * grid.spacing_x);
    let scale_y = dt / (grid.spacing_y * grid.spacing_y);
    rows_mut(&mut faces.east, columns, threads, |first, block| {
        for (offset, value) in block.iter_mut().enumerate() {
            let cell = first * columns + offset;
            *value = 0.0;
            if (cell % columns) + 1 < columns && valid(current, cell) && valid(current, cell + 1) {
                let mut factor = 1.0;
                if let Some(critical) = critical {
                    let along = (current[cell + 1] - current[cell]) / grid.spacing_x;
                    let across = 0.5 * (cross_gradient(grid, current, cell, false) + cross_gradient(grid, current, cell + 1, false));
                    factor = roering(along * along + across * across, critical);
                }
                *value = scale_x * (0.5 * (diffusivity[cell] + diffusivity[cell + 1])) * factor;
            }
        }
    });
    rows_mut(&mut faces.south, columns, threads, |first, block| {
        for (offset, value) in block.iter_mut().enumerate() {
            let cell = first * columns + offset;
            *value = 0.0;
            if cell / columns + 1 < grid.rows && valid(current, cell) && valid(current, cell + columns) {
                let mut factor = 1.0;
                if let Some(critical) = critical {
                    let along = (current[cell + columns] - current[cell]) / grid.spacing_y;
                    let across = 0.5 * (cross_gradient(grid, current, cell, true) + cross_gradient(grid, current, cell + columns, true));
                    factor = roering(along * along + across * across, critical);
                }
                *value = scale_y * (0.5 * (diffusivity[cell] + diffusivity[cell + columns])) * factor;
            }
        }
    });
}

/// One cell's row of the tridiagonal system: (lower, diagonal, upper), all zero couplings for
/// fixed cells.
#[inline(always)]
fn coefficients(free: bool, before: f64, after: f64) -> (f64, f64, f64) {
    if free {
        (-before, 1.0 + before + after, -after)
    } else {
        (0.0, 1.0, 0.0)
    }
}

fn sweep_rows(grid: &Grid, status: &[u8], faces: &Faces, source: &[f64], out: &mut [f64], threads: usize) {
    let columns = grid.columns;
    rows_mut(out, columns, threads, |first_row, block| {
        let mut upper = vec![0.0; columns];
        for (index, row_out) in block.chunks_mut(columns).enumerate() {
            let base = (first_row + index) * columns;
            let mut previous_upper = 0.0;
            let mut previous_value = 0.0;
            for column in 0..columns {
                let cell = base + column;
                let before = if column > 0 { faces.east[cell - 1] } else { 0.0 };
                let (a, b, c) = coefficients(status[cell] == INTERIOR, before, faces.east[cell]);
                let denominator = b - a * previous_upper;
                upper[column] = c / denominator;
                let right = if a != 0.0 { source[cell] - a * previous_value } else { source[cell] };
                row_out[column] = right / denominator;
                previous_upper = upper[column];
                previous_value = row_out[column];
            }
            for column in (0..columns.saturating_sub(1)).rev() {
                if upper[column] != 0.0 {
                    row_out[column] -= upper[column] * row_out[column + 1];
                }
            }
        }
    });
}

fn sweep_columns(grid: &Grid, status: &[u8], faces: &Faces, source: &[f64], out: &mut [f64], threads: usize) {
    let (rows, columns) = (grid.rows, grid.columns);
    let parts = crate::team::parts(rows * columns, threads).min(columns);
    let mut blocks: Vec<(usize, Vec<&mut [f64]>)> = (0..parts).map(|index| (span(columns, parts, index).start, Vec::with_capacity(rows))).collect();
    for row_out in out.chunks_mut(columns) {
        let mut rest = row_out;
        for (index, block) in blocks.iter_mut().enumerate() {
            let (piece, tail) = rest.split_at_mut(span(columns, parts, index).len());
            rest = tail;
            block.1.push(piece);
        }
    }
    crate::team::each_mut(&mut blocks, |(first_column, pieces)| {
        {
            let width = pieces.first().map_or(0, |piece| piece.len());
            let mut upper = vec![0.0; rows * width];
            for row in 0..rows {
                for offset in 0..width {
                    let cell = row * columns + *first_column + offset;
                    let before = if row > 0 { faces.south[cell - columns] } else { 0.0 };
                    let (a, b, c) = coefficients(status[cell] == INTERIOR, before, faces.south[cell]);
                    let (previous_upper, previous_value) = if row > 0 { (upper[(row - 1) * width + offset], pieces[row - 1][offset]) } else { (0.0, 0.0) };
                    let denominator = b - a * previous_upper;
                    upper[row * width + offset] = c / denominator;
                    let right = if a != 0.0 { source[cell] - a * previous_value } else { source[cell] };
                    pieces[row][offset] = right / denominator;
                }
            }
            for row in (0..rows.saturating_sub(1)).rev() {
                for offset in 0..width {
                    let factor = upper[row * width + offset];
                    if factor != 0.0 {
                        let below = pieces[row + 1][offset];
                        pieces[row][offset] -= factor * below;
                    }
                }
            }
        }
    });
}

#[allow(clippy::too_many_arguments)]
pub fn diffuse(grid: &Grid, heights: &[f64], diffusivity: &[f64], dt: f64, critical: Option<Critical>, threads: usize, out: &mut [f64]) -> KernelResult<()> {
    grid.expect_len("heights", heights.len(), 1)?;
    grid.expect_len("diffusivity", diffusivity.len(), 1)?;
    grid.expect_len("out", out.len(), 1)?;
    check(dt.is_finite() && dt >= 0.0, || format!("the time step must be finite and at least 0, got {}", dt))?;
    check(all_of(grid.count(), threads, |cell| !heights[cell].is_finite() || (diffusivity[cell].is_finite() && diffusivity[cell] >= 0.0)), || "diffusivity must be finite and at least 0 on every valid cell".to_string())?;
    if let Some(critical) = critical.as_ref() {
        check(critical.slope.is_finite() && critical.slope > 0.0, || format!("the critical slope must be finite and above 0, got {}", critical.slope))?;
        check(critical.max_ratio > 0.0 && critical.max_ratio < 1.0, || format!("the slope ratio cap must be in (0, 1), got {}", critical.max_ratio))?;
        check(critical.iterations >= 1 && critical.iterations <= 100, || format!("the Picard iterations must be 1 to 100, got {}", critical.iterations))?;
    }
    let status = grid.status(heights, threads);
    let iterations = critical.map_or(1, |critical| critical.iterations);
    let mut half = vec![0.0; grid.count()];
    let mut faces = Faces { east: vec![0.0; grid.count()], south: vec![0.0; grid.count()] };
    for iteration in 0..iterations {
        let current: &[f64] = if iteration == 0 { heights } else { out };
        fill_faces(grid, current, diffusivity, dt, critical.as_ref(), threads, &mut faces);
        sweep_rows(grid, &status, &faces, heights, &mut half, threads);
        sweep_columns(grid, &status, &faces, &half, out, threads);
    }
    Ok(())
}
