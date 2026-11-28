//! Threads with a fixed partition. Work is split into contiguous spans whose bounds depend only
//! on the length and the thread count, and every kernel computes each output value with the
//! same operations in the same order whatever the span it falls in, so results are identical at
//! every thread count. Values that one thread writes and another reads after a barrier live in
//! relaxed atomics, which compile to plain loads and stores; the barrier orders them.
//!
//! This module starts, synchronises and joins a team of threads; `parts` holds the partition and
//! the one-shot scoped runs over it, `shared` the atomic views the threads share. Both are
//! re-exported here.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

use crate::error::{KernelError, KernelResult};

pub use crate::parts::*;
pub use crate::shared::*;

pub const MAX_THREADS: usize = 64;
const SPINS_BEFORE_YIELD: u32 = 4096;
const PEER_FAILED: &str = "another thread of the kernel failed";

/// A sense-counting spin barrier that yields after a while, so a thread that the system has
/// descheduled does not leave the others burning a core. A failed thread poisons it, and every
/// waiting thread then stops instead of waiting forever.
pub struct Barrier {
    parties: usize,
    arrived: AtomicUsize,
    generation: AtomicUsize,
    failed: AtomicBool,
}

impl Barrier {
    pub fn new(parties: usize) -> Barrier {
        Barrier { parties, arrived: AtomicUsize::new(0), generation: AtomicUsize::new(0), failed: AtomicBool::new(false) }
    }

    pub fn parties(&self) -> usize {
        self.parties
    }

    pub fn wait(&self) {
        if self.parties == 1 {
            return;
        }
        let generation = self.generation.load(Ordering::Acquire);
        if self.arrived.fetch_add(1, Ordering::AcqRel) + 1 == self.parties {
            self.arrived.store(0, Ordering::Relaxed);
            self.generation.store(generation.wrapping_add(1), Ordering::Release);
            return;
        }
        let mut spins = 0u32;
        while self.generation.load(Ordering::Acquire) == generation {
            if self.failed.load(Ordering::Relaxed) {
                panic!("{}", PEER_FAILED);
            }
            if spins < SPINS_BEFORE_YIELD {
                spins += 1;
                std::hint::spin_loop();
            } else {
                std::thread::yield_now();
            }
        }
    }

    fn fail(&self) {
        self.failed.store(true, Ordering::Relaxed);
    }
}

pub fn panic_text(payload: &(dyn std::any::Any + Send)) -> String {
    payload.downcast_ref::<&str>().map(|text| text.to_string()).or_else(|| payload.downcast_ref::<String>().cloned()).unwrap_or_else(|| "unknown panic".to_string())
}

pub fn check_threads(threads: i64) -> KernelResult<usize> {
    if threads < 1 || threads > MAX_THREADS as i64 {
        return Err(KernelError::invalid(format!("threads must be between 1 and {}, got {}", MAX_THREADS, threads)));
    }
    Ok(threads as usize)
}

/// Runs `work(index, barrier)` on `threads` threads, the calling thread being index 0, and
/// returns the first real error in thread order. A panic in any thread becomes an error.
pub fn team<F>(threads: usize, work: F) -> KernelResult<()>
where
    F: Fn(usize, &Barrier) -> KernelResult<()> + Sync,
{
    let barrier = Barrier::new(threads.max(1));
    let run = |index: usize| -> KernelResult<()> {
        let outcome = catch_unwind(AssertUnwindSafe(|| work(index, &barrier)));
        let result = match outcome {
            Ok(result) => result,
            Err(payload) => Err(KernelError::panic(format!("internal error in the native core: {}", panic_text(&*payload)))),
        };
        if result.is_err() {
            barrier.fail();
        }
        result
    };
    if threads <= 1 {
        return run(0);
    }
    let run = &run;
    let results: Vec<KernelResult<()>> = std::thread::scope(|scope| {
        let handles: Vec<_> = (1..threads).map(|index| scope.spawn(move || run(index))).collect();
        let mut results = vec![run(0)];
        for handle in handles {
            results.push(handle.join().unwrap_or_else(|payload| Err(KernelError::panic(panic_text(&*payload)))));
        }
        results
    });
    let mut first: KernelResult<()> = Ok(());
    for result in results {
        if let Err(error) = result {
            let real = !error.message.ends_with(PEER_FAILED);
            if first.is_ok() || real && matches!(&first, Err(found) if found.message.ends_with(PEER_FAILED)) {
                first = Err(error);
            }
        }
    }
    first
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::error::PANIC;


    #[test]
    fn a_panicking_thread_stops_its_team_instead_of_leaving_it_waiting() {
        for failing in 0..4 {
            let result = team(4, |thread, barrier| {
                barrier.wait();
                if thread == failing {
                    panic!("kernel bug in thread {}", thread);
                }
                for _ in 0..3 {
                    barrier.wait();
                }
                Ok(())
            });
            let error = result.expect_err("the panic must become an error");
            assert_eq!(error.code, PANIC);
            assert!(error.message.contains(&format!("kernel bug in thread {}", failing)), "{}", error.message);
        }
    }

    #[test]
    fn a_returned_error_wins_over_the_peers_it_stopped() {
        let result = team(3, |thread, barrier| {
            if thread == 2 {
                return Err(KernelError::invalid("bad input seen by thread 2"));
            }
            barrier.wait();
            Ok(())
        });
        assert_eq!(result.expect_err("error").message, "bad input seen by thread 2");
    }
}
