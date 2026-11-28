//! Exported kernels. Each reads its grid and buffers through `Buffers`, which checks them, and
//! hands safe slices to the kernel.

use super::{grid_of, guarded, BwBuffer, BwGrid, Buffers};
use crate::accumulate::accumulate;
use crate::diffusion::{diffuse, Critical};
use crate::error::{check, KernelError};
use crate::flood::priority_flood;
use crate::incision::{incise, Law};
use crate::lakes::{route, LakeOutputs, Mode};
use crate::levels::Levels;
use crate::order::order;
use crate::receivers::{d8, mfd};
use crate::thermal::slide;

type Buffer = *const BwBuffer;

#[no_mangle]
pub extern "C" fn bw_d8(grid: *const BwGrid, threads: i64, heights: Buffer, receivers: Buffer, resolved: *mut i64) -> i32 {
    guarded(|| unsafe {
        let (grid, threads) = grid_of(grid, threads)?;
        let mut buffers = Buffers::new();
        let heights = buffers.f64s("heights", heights)?;
        let receivers = buffers.i32s_mut("receivers", receivers)?;
        let resolved = buffers.scalar("resolved", resolved)?;
        *resolved = d8(&grid, heights, threads, receivers)? as i64;
        Ok(())
    })
}

#[no_mangle]
pub extern "C" fn bw_mfd(grid: *const BwGrid, threads: i64, heights: Buffer, exponent: f64, receivers: Buffer, shares: Buffer, resolved: *mut i64) -> i32 {
    guarded(|| unsafe {
        let (grid, threads) = grid_of(grid, threads)?;
        let mut buffers = Buffers::new();
        let heights = buffers.f64s("heights", heights)?;
        let receivers = buffers.i32s_mut("receivers", receivers)?;
        let shares = buffers.f64s_mut("shares", shares)?;
        let resolved = buffers.scalar("resolved", resolved)?;
        *resolved = mfd(&grid, heights, exponent, threads, receivers, shares)? as i64;
        Ok(())
    })
}

#[no_mangle]
pub extern "C" fn bw_order(grid: *const BwGrid, threads: i64, receivers: Buffer, width: i64, order_out: Buffer, level_start: Buffer, donor_start: Buffer, donors: Buffer, levels: *mut i64) -> i32 {
    guarded(|| unsafe {
        let (grid, threads) = grid_of(grid, threads)?;
        let mut buffers = Buffers::new();
        let receivers = buffers.i32s("receivers", receivers)?;
        let order_out = buffers.i32s_mut("order", order_out)?;
        let level_start = buffers.i32s_mut("level offsets", level_start)?;
        let donor_start = buffers.i32s_mut("donor offsets", donor_start)?;
        let donors = buffers.i32s_mut("donors", donors)?;
        let levels = buffers.scalar("levels", levels)?;
        let width = usize::try_from(width).map_err(|_| KernelError::invalid(format!("width must be 1 to 8, got {}", width)))?;
        *levels = order(&grid, receivers, width, threads, order_out, level_start, donor_start, donors)?.levels as i64;
        Ok(())
    })
}

#[no_mangle]
pub extern "C" fn bw_accumulate(grid: *const BwGrid, threads: i64, width: i64, shares: Buffer, order_in: Buffer, level_start: Buffer, donor_start: Buffer, donors: Buffer, weights: Buffer, total: Buffer) -> i32 {
    guarded(|| unsafe {
        let (grid, threads) = grid_of(grid, threads)?;
        let mut buffers = Buffers::new();
        let shares = buffers.f64s("shares", shares)?;
        let order_in = buffers.i32s("order", order_in)?;
        let level_start = buffers.i32s("level offsets", level_start)?;
        let donor_start = buffers.i32s("donor offsets", donor_start)?;
        let donors = buffers.i32s("donors", donors)?;
        let weights = buffers.f64s("weights", weights)?;
        let total = buffers.f64s_mut("total", total)?;
        let width = usize::try_from(width).map_err(|_| KernelError::invalid(format!("width must be 1 to 8, got {}", width)))?;
        let levels = Levels::new(order_in, level_start, grid.count(), threads)?;
        accumulate(grid.count(), width, shares, &levels, donor_start, donors, weights, threads, total)
    })
}

#[no_mangle]
pub extern "C" fn bw_incise(grid: *const BwGrid, threads: i64, heights: Buffer, receivers: Buffer, order_in: Buffer, level_start: Buffer, area: Buffer, erodibility: Buffer, area_exponent: f64, slope_exponent: f64, dt: f64, solved: Buffer) -> i32 {
    guarded(|| unsafe {
        let (grid, threads) = grid_of(grid, threads)?;
        let mut buffers = Buffers::new();
        let heights = buffers.f64s("heights", heights)?;
        let receivers = buffers.i32s("receivers", receivers)?;
        let order_in = buffers.i32s("order", order_in)?;
        let level_start = buffers.i32s("level offsets", level_start)?;
        let area = buffers.f64s("area", area)?;
        let erodibility = buffers.f64s("erodibility", erodibility)?;
        let solved = buffers.f64s_mut("solved", solved)?;
        let levels = Levels::new(order_in, level_start, grid.count(), threads)?;
        incise(&grid, heights, receivers, &levels, area, erodibility, &Law { area_exponent, slope_exponent, dt }, threads, solved)
    })
}

#[no_mangle]
pub extern "C" fn bw_route_lakes(grid: *const BwGrid, threads: i64, heights: Buffer, receivers: Buffer, order_in: Buffer, level_start: Buffer, carve: i64, out_receivers: Buffer, basin: Buffer, lake: Buffer, water: Buffer, spill: Buffer, spill_to: Buffer, basins: *mut i64, lakes: *mut i64) -> i32 {
    guarded(|| unsafe {
        let (grid, threads) = grid_of(grid, threads)?;
        let mut buffers = Buffers::new();
        let heights = buffers.f64s("heights", heights)?;
        let receivers = buffers.i32s("receivers", receivers)?;
        let order_in = buffers.i32s("order", order_in)?;
        let level_start = buffers.i32s("level offsets", level_start)?;
        let outputs = LakeOutputs {
            receivers: buffers.i32s_mut("receivers out", out_receivers)?,
            basin: buffers.i32s_mut("basin", basin)?,
            lake: buffers.i32s_mut("lake", lake)?,
            water: buffers.f64s_mut("water", water)?,
            spill: buffers.i32s_mut("spill", spill)?,
            spill_to: buffers.i32s_mut("spill to", spill_to)?,
        };
        let basins = buffers.scalar("basins", basins)?;
        let lakes = buffers.scalar("lakes", lakes)?;
        let mode = match carve {
            0 => Mode::Fill,
            1 => Mode::Carve,
            _ => return Err(KernelError::invalid(format!("the mode must be 0 (filling) or 1 (carving), got {}", carve))),
        };
        // The basins come from the receivers alone; the order stays in the signature for the
        // reference implementation and is only checked for size.
        grid.expect_len("order", order_in.len(), 1)?;
        check(level_start.len() == grid.count() + 1, || format!("level offsets must hold {} values, got {}", grid.count() + 1, level_start.len()))?;
        let routed = route(&grid, heights, receivers, mode, threads, outputs)?;
        *basins = routed.basins as i64;
        *lakes = routed.lakes as i64;
        Ok(())
    })
}

#[no_mangle]
pub extern "C" fn bw_priority_flood(grid: *const BwGrid, heights: Buffer, epsilon: i64, filled: Buffer, raised: *mut i64) -> i32 {
    guarded(|| unsafe {
        let (grid, _) = grid_of(grid, 1)?;
        let mut buffers = Buffers::new();
        let heights = buffers.f64s("heights", heights)?;
        let filled = buffers.f64s_mut("filled", filled)?;
        let raised = buffers.scalar("raised", raised)?;
        if epsilon != 0 && epsilon != 1 {
            return Err(KernelError::invalid(format!("epsilon must be 0 or 1, got {}", epsilon)));
        }
        *raised = priority_flood(&grid, heights, epsilon == 1, filled)? as i64;
        Ok(())
    })
}

#[no_mangle]
pub extern "C" fn bw_diffuse(grid: *const BwGrid, threads: i64, heights: Buffer, diffusivity: Buffer, dt: f64, critical_slope: f64, max_ratio: f64, iterations: i64, out: Buffer) -> i32 {
    guarded(|| unsafe {
        let (grid, threads) = grid_of(grid, threads)?;
        let mut buffers = Buffers::new();
        let heights = buffers.f64s("heights", heights)?;
        let diffusivity = buffers.f64s("diffusivity", diffusivity)?;
        let out = buffers.f64s_mut("out", out)?;
        let critical = if critical_slope == 0.0 {
            None
        } else {
            let iterations = usize::try_from(iterations).map_err(|_| KernelError::invalid(format!("the Picard iterations must be 1 to 100, got {}", iterations)))?;
            Some(Critical { slope: critical_slope, max_ratio, iterations })
        };
        diffuse(&grid, heights, diffusivity, dt, critical, threads, out)
    })
}

#[no_mangle]
pub extern "C" fn bw_slide(grid: *const BwGrid, threads: i64, heights: Buffer, tangent: Buffer, rate: f64, iterations: i64, out: Buffer) -> i32 {
    guarded(|| unsafe {
        let (grid, threads) = grid_of(grid, threads)?;
        let mut buffers = Buffers::new();
        let heights = buffers.f64s("heights", heights)?;
        let tangent = buffers.f64s("critical tangent", tangent)?;
        let out = buffers.f64s_mut("out", out)?;
        let iterations = usize::try_from(iterations).map_err(|_| KernelError::invalid(format!("iterations must be at least 0, got {}", iterations)))?;
        slide(&grid, heights, tangent, rate, iterations, threads, out)
    })
}
