//! Sweeps over the levels of an order. Cells of one level depend only on cells of earlier levels
//! (or, in reverse, of later ones), so a level is split among the threads in contiguous spans
//! with one barrier after it; a run of small levels is taken by one thread with one barrier
//! after the run. Which thread computes a cell never changes what is computed.

use crate::error::{check, KernelError, KernelResult};
use crate::order::SMALL_LEVEL;
use crate::team::{span, spans, team};

#[derive(Debug, Clone, Copy)]
struct Step {
    first: usize,
    end: usize,
    parallel: bool,
}

pub struct Levels<'a> {
    pub order: &'a [i32],
    pub starts: Vec<usize>,
}

impl<'a> Levels<'a> {
    /// Reads and checks an order and its level offsets (levels + 1 values, then -1 padding).
    pub fn new(order: &'a [i32], level_start: &[i32], count: usize, threads: usize) -> KernelResult<Levels<'a>> {
        check(order.len() == count, || format!("order must hold {} values, got {}", count, order.len()))?;
        check(level_start.len() == count + 1, || format!("level offsets must hold {} values, got {}", count + 1, level_start.len()))?;
        let mut starts = Vec::new();
        for value in level_start.iter() {
            if *value < 0 {
                break;
            }
            starts.push(*value as usize);
        }
        check(starts.first() == Some(&0) && starts.last() == Some(&count), || "level offsets must start at 0 and end at the cell count".to_string())?;
        check(starts.windows(2).all(|pair| pair[0] < pair[1]) || count == 0, || "level offsets must increase".to_string())?;
        check(level_start[starts.len()..].iter().all(|value| *value == -1), || "level offsets must be padded with -1".to_string())?;
        let words = (count + 63) / 64;
        let marks = spans(count, threads, |_, positions| {
            let mut bits = vec![0u64; words];
            for cell in order[positions].iter() {
                if *cell < 0 || *cell as usize >= count {
                    return Err(KernelError::invalid(format!("order holds {}, outside the {} cells", cell, count)));
                }
                let (word, bit) = (*cell as usize / 64, 1u64 << (*cell as usize % 64));
                if bits[word] & bit != 0 {
                    return Err(KernelError::invalid(format!("order is not a permutation of the cells: {} repeats", cell)));
                }
                bits[word] |= bit;
            }
            Ok(bits)
        });
        let marks = marks.into_iter().collect::<KernelResult<Vec<Vec<u64>>>>()?;
        let clash = spans(words, threads, |_, range| range.into_iter().any(|word| {
            let mut seen = 0u64;
            for bits in marks.iter() {
                if seen & bits[word] != 0 {
                    return true;
                }
                seen |= bits[word];
            }
            false
        }));
        check(!clash.into_iter().any(|found| found), || "order is not a permutation of the cells: a cell repeats".to_string())?;
        Ok(Levels { order, starts })
    }

    pub fn levels(&self) -> usize {
        self.starts.len() - 1
    }

    /// The level of every cell.
    pub fn level_of(&self) -> Vec<u32> {
        let mut found = vec![0u32; self.order.len()];
        for level in 0..self.levels() {
            for cell in self.order[self.starts[level]..self.starts[level + 1]].iter() {
                found[*cell as usize] = level as u32;
            }
        }
        found
    }

    fn steps(&self, threads: usize) -> Vec<Step> {
        let mut steps: Vec<Step> = Vec::new();
        for level in 0..self.levels() {
            let parallel = threads > 1 && self.starts[level + 1] - self.starts[level] >= SMALL_LEVEL;
            match steps.last_mut() {
                Some(step) if !step.parallel && !parallel => step.end = level + 1,
                _ => steps.push(Step { first: level, end: level + 1, parallel }),
            }
        }
        steps
    }

    /// Calls `visit(cell)` for every cell, level by level, from the first level or (reverse)
    /// from the last.
    pub fn sweep<F: Fn(usize) + Sync>(&self, threads: usize, reverse: bool, visit: F) -> KernelResult<()> {
        let mut steps = self.steps(threads);
        if reverse {
            steps.reverse();
        }
        team(threads.max(1), |thread, barrier| {
            for step in steps.iter() {
                if step.parallel {
                    let low = self.starts[step.first];
                    let size = self.starts[step.end] - low;
                    for index in span(size, barrier.parties(), thread) {
                        visit(self.order[low + index] as usize);
                    }
                } else if thread == 0 {
                    let mut levels: Vec<usize> = (step.first..step.end).collect();
                    if reverse {
                        levels.reverse();
                    }
                    for level in levels {
                        for cell in self.order[self.starts[level]..self.starts[level + 1]].iter() {
                            visit(*cell as usize);
                        }
                    }
                }
                barrier.wait();
            }
            Ok(())
        })
    }
}
