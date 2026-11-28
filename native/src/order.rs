//! The breadth-first receiver queue with levels (Barnes 2019, "Accelerating a fluvial incision
//! and landscape evolution model with parallelism", Geomorphology 330:28-39). Level 0 holds the
//! cells without receivers (outlets, pits, no-data) in ascending order. The queue then takes the
//! cells of each level in turn and appends their donors in donor-list order; a donor with several
//! receivers joins once its last receiver has been taken, so every cell comes after all of its
//! receivers and each level holds cells that depend only on earlier levels. With one receiver
//! per cell this is the plain breadth-first search from the outlets. Each level is split among
//! the threads in contiguous spans and a donor joins at the position the sequential queue would
//! give it, so the order is the same at every thread count.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Mutex, RwLock};

use crate::donors::{check_table, donor_lists};
use crate::error::{check, KernelError, KernelResult};
use crate::grid::Grid;
use crate::ffi::views::atomic_i32;
use crate::team::{span, team, I32View, SharedU32};

/// Levels smaller than this are taken by one thread, which saves a barrier per level.
pub const SMALL_LEVEL: usize = 256;

pub struct Ordered {
    pub levels: usize,
    pub edges: usize,
}

struct Queue {
    banks: Vec<RwLock<Vec<u32>>>,
    lengths: SharedU32,
    threads: usize,
}

impl Queue {
    fn bank(&self, side: usize, thread: usize) -> &RwLock<Vec<u32>> {
        &self.banks[side * self.threads + thread]
    }

    fn total(&self, side: usize) -> usize {
        (0..self.threads).map(|thread| self.lengths.get(side * self.threads + thread) as usize).sum()
    }

    fn read_range<F: FnMut(usize, u32)>(&self, side: usize, range: std::ops::Range<usize>, mut visit: F) {
        let mut base = 0usize;
        for thread in 0..self.threads {
            let length = self.lengths.get(side * self.threads + thread) as usize;
            let low = range.start.max(base);
            let high = range.end.min(base + length);
            if low < high {
                let bank = self.bank(side, thread).read().expect("queue bank");
                for index in low..high {
                    visit(index, bank[index - base]);
                }
            }
            base += length;
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub fn order(grid: &Grid, receivers: &[i32], width: usize, threads: usize, order: &mut [i32], level_start: &mut [i32], donor_start: &mut [i32], donors: &mut [i32]) -> KernelResult<Ordered> {
    check_table(grid, receivers, width, threads)?;
    let count = grid.count();
    check(order.len() == count, || format!("order must hold {} values, got {}", count, order.len()))?;
    check(level_start.len() == count + 1, || format!("level offsets must hold {} values, got {}", count + 1, level_start.len()))?;
    let edges = donor_lists(grid, receivers, width, threads, donor_start, donors)?;
    let donor_start: &[i32] = donor_start;
    let donors: &[i32] = donors;
    let threads = threads.max(1);
    let queue = Queue { banks: (0..2 * threads).map(|_| RwLock::new(Vec::new())).collect(), lengths: SharedU32::new(2 * threads, 0), threads };
    let remaining = SharedU32::new(if width > 1 { count } else { 0 }, 0);
    let position = SharedU32::new(if width > 1 { count } else { 0 }, 0);
    let placed = I32View(atomic_i32(order));
    let starts = Mutex::new(Vec::new());
    let next_base = AtomicUsize::new(0);
    let place = |cell: usize, at: usize| {
        placed.set(at, cell as i32);
        if width > 1 {
            position.set(cell, at as u32);
        }
    };
    let joins = |donor: usize, receiver: usize| -> bool {
        if width == 1 {
            return true;
        }
        if remaining.get(donor) != 0 {
            return false;
        }
        let mut last = 0u32;
        for slot in 0..width {
            let target = receivers[donor * width + slot];
            if target >= 0 {
                last = last.max(position.get(target as usize));
            }
        }
        last == position.get(receiver)
    };
    team(threads, |thread, barrier| {
        {
            let mut bank = queue.bank(0, thread).write().expect("queue bank");
            bank.clear();
            for cell in span(count, threads, thread) {
                if width > 1 {
                    let slots = (0..width).filter(|slot| receivers[cell * width + slot] >= 0).count();
                    remaining.set(cell, slots as u32);
                }
                if (0..width).all(|slot| receivers[cell * width + slot] < 0) {
                    bank.push(cell as u32);
                }
            }
            queue.lengths.set(thread, bank.len() as u32);
        }
        barrier.wait();
        let mut side = 0usize;
        let mut base = 0usize;
        loop {
            let size = queue.total(side);
            if thread == 0 {
                starts.lock().expect("level starts").push(base as u32);
            }
            if size == 0 {
                break;
            }
            let other = 1 - side;
            if size < SMALL_LEVEL || threads == 1 {
                if thread == 0 {
                    let mut current = Vec::with_capacity(size);
                    queue.read_range(side, 0..size, |_, cell| current.push(cell));
                    let mut next = Vec::new();
                    let mut first = base;
                    loop {
                        for (index, cell) in current.iter().enumerate() {
                            place(*cell as usize, first + index);
                        }
                        next.clear();
                        for cell in current.iter() {
                            visit_donors(donor_start, donors, width, *cell as usize, &remaining, &mut next, &joins);
                        }
                        first += current.len();
                        std::mem::swap(&mut current, &mut next);
                        if current.is_empty() || (current.len() >= SMALL_LEVEL && threads > 1) {
                            break;
                        }
                        starts.lock().expect("level starts").push(first as u32);
                    }
                    let mut bank = queue.bank(other, 0).write().expect("queue bank");
                    bank.clear();
                    bank.extend_from_slice(&current);
                    queue.lengths.set(other * threads, bank.len() as u32);
                    for peer in 1..threads {
                        queue.lengths.set(other * threads + peer, 0);
                    }
                    next_base.store(first, Ordering::Relaxed);
                }
                barrier.wait();
                base = next_base.load(Ordering::Relaxed);
                side = other;
                continue;
            }
            let mine = span(size, threads, thread);
            let mut cells = Vec::with_capacity(mine.len());
            queue.read_range(side, mine.clone(), |index, cell| {
                place(cell as usize, base + index);
                cells.push(cell);
            });
            if width > 1 {
                for cell in cells.iter() {
                    let cell = *cell as usize;
                    for index in donor_start[cell] as usize..donor_start[cell + 1] as usize {
                        remaining.take_one(donors[index] as usize / width);
                    }
                }
                barrier.wait();
            }
            {
                let mut bank = queue.bank(other, thread).write().expect("queue bank");
                bank.clear();
                for cell in cells.iter() {
                    collect_joined(donor_start, donors, width, *cell as usize, &mut bank, &joins);
                }
                queue.lengths.set(other * threads + thread, bank.len() as u32);
            }
            barrier.wait();
            base += size;
            side = other;
        }
        if thread == 0 {
            let total = base;
            if total != count {
                return Err(KernelError::cycle(format!("the flow graph has a cycle: {} of {} cells cannot be ordered", count - total, count)));
            }
        }
        Ok(())
    })?;
    let starts = starts.into_inner().expect("level starts");
    for (index, value) in starts.iter().enumerate() {
        level_start[index] = *value as i32;
    }
    for value in level_start[starts.len()..].iter_mut() {
        *value = -1;
    }
    Ok(Ordered { levels: starts.len() - 1, edges })
}

fn visit_donors<J: Fn(usize, usize) -> bool>(donor_start: &[i32], donors: &[i32], width: usize, cell: usize, remaining: &SharedU32, next: &mut Vec<u32>, joins: &J) {
    for index in donor_start[cell] as usize..donor_start[cell + 1] as usize {
        let donor = donors[index] as usize / width;
        if width > 1 {
            remaining.take_one(donor);
        }
        if joins(donor, cell) {
            next.push(donor as u32);
        }
    }
}

fn collect_joined<J: Fn(usize, usize) -> bool>(donor_start: &[i32], donors: &[i32], width: usize, cell: usize, bank: &mut Vec<u32>, joins: &J) {
    for index in donor_start[cell] as usize..donor_start[cell + 1] as usize {
        let donor = donors[index] as usize / width;
        if joins(donor, cell) {
            bank.push(donor as u32);
        }
    }
}
