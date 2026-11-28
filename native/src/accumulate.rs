//! Accumulation along the queue: from the last level to the first, every cell pulls its donors'
//! totals, total(c) = weight(c) + sum over its donor list of share(e) x total(donor(e)), in
//! donor-list order. Each total is summed by one thread in one fixed order, so totals are
//! bit-identical at every thread count.

use crate::error::{check, KernelResult};
use crate::levels::Levels;
use crate::ffi::views::atomic_f64;
use crate::team::{all_of, spans, F64View};

pub fn check_donors(count: usize, width: usize, donor_start: &[i32], donors: &[i32], threads: usize) -> KernelResult<()> {
    check(donor_start.len() == count + 1, || format!("donor offsets must hold {} values, got {}", count + 1, donor_start.len()))?;
    check(donor_start[0] == 0, || "donor offsets must start at 0".to_string())?;
    let edges = donor_start[count];
    check(edges >= 0 && edges as usize <= donors.len(), || format!("donor offsets end at {}, beyond the {} donors given", edges, donors.len()))?;
    check(all_of(count, threads, |cell| donor_start[cell] <= donor_start[cell + 1]), || "donor offsets must not decrease".to_string())?;
    let limit = (count * width) as u32;
    let used = &donors[..edges as usize];
    let inside = spans(used.len(), threads, |_, range| used[range].iter().all(|edge| (*edge as u32) < limit));
    check(inside.into_iter().all(|found| found), || format!("a donor edge is outside 0..{}", limit))
}

#[allow(clippy::too_many_arguments)]
pub fn accumulate(count: usize, width: usize, shares: &[f64], levels: &Levels, donor_start: &[i32], donors: &[i32], weights: &[f64], threads: usize, total: &mut [f64]) -> KernelResult<()> {
    check(width >= 1 && width <= 8, || format!("a receiver table has 1 to 8 slots per cell, got {}", width))?;
    check(weights.len() == count && total.len() == count, || format!("weights and totals must hold {} values, got {} and {}", count, weights.len(), total.len()))?;
    check(width == 1 || shares.len() == count * width, || format!("shares must hold {} values, got {}", count * width, shares.len()))?;
    check_donors(count, width, donor_start, donors, threads)?;
    let sums = F64View(atomic_f64(total)?);
    sums.fill_from(weights, threads);
    levels.sweep(threads, true, |cell| {
        let mut sum = weights[cell];
        let range = donor_start[cell] as usize..donor_start[cell + 1] as usize;
        if width == 1 {
            for edge in donors[range].iter() {
                sum += sums.get(*edge as usize);
            }
        } else {
            for edge in donors[range].iter() {
                let edge = *edge as usize;
                sum += shares[edge] * sums.get(edge / width);
            }
        }
        sums.set(cell, sum);
    })?;
    Ok(())
}
