//! Buffers shared between the threads of a kernel as relaxed atomics, which compile to plain
//! loads and stores; the barriers of `team` order them.

use std::sync::atomic::{AtomicI32, AtomicU32, AtomicU64, Ordering};

use crate::parts::{rows_mut, spans};

pub struct SharedU32(Vec<AtomicU32>);

impl SharedU32 {
    pub fn new(len: usize, value: u32) -> SharedU32 {
        SharedU32((0..len).map(|_| AtomicU32::new(value)).collect())
    }

    #[inline(always)]
    pub fn get(&self, index: usize) -> u32 {
        self.0[index].load(Ordering::Relaxed)
    }

    #[inline(always)]
    pub fn set(&self, index: usize, value: u32) {
        self.0[index].store(value, Ordering::Relaxed)
    }

    #[inline(always)]
    pub fn take_one(&self, index: usize) -> u32 {
        self.0[index].fetch_sub(1, Ordering::Relaxed)
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

pub struct SharedF64(Vec<AtomicU64>);

impl SharedF64 {
    pub fn from_slice(values: &[f64]) -> SharedF64 {
        SharedF64(values.iter().map(|value| AtomicU64::new(value.to_bits())).collect())
    }

    #[inline(always)]
    pub fn get(&self, index: usize) -> f64 {
        f64::from_bits(self.0[index].load(Ordering::Relaxed))
    }

    #[inline(always)]
    pub fn set(&self, index: usize, value: f64) {
        self.0[index].store(value.to_bits(), Ordering::Relaxed)
    }

    pub fn copy_to(&self, out: &mut [f64], threads: usize) {
        rows_mut(out, 1, threads, |first, block| {
            for (offset, value) in block.iter_mut().enumerate() {
                *value = self.get(first + offset);
            }
        });
    }
}

/// A caller's float64 buffer shared between the threads of a sweep.
pub struct F64View<'a>(pub &'a [AtomicU64]);

impl<'a> F64View<'a> {
    #[inline(always)]
    pub fn get(&self, index: usize) -> f64 {
        f64::from_bits(self.0[index].load(Ordering::Relaxed))
    }

    #[inline(always)]
    pub fn set(&self, index: usize, value: f64) {
        self.0[index].store(value.to_bits(), Ordering::Relaxed)
    }

    pub fn fill_from(&self, values: &[f64], threads: usize) {
        spans(values.len(), threads, |_, cells| {
            for cell in cells {
                self.set(cell, values[cell]);
            }
        });
    }
}

/// A caller's int32 buffer shared between the threads of a kernel.
pub struct I32View<'a>(pub &'a [AtomicI32]);

impl<'a> I32View<'a> {
    #[inline(always)]
    pub fn get(&self, index: usize) -> i32 {
        self.0[index].load(Ordering::Relaxed)
    }

    #[inline(always)]
    pub fn set(&self, index: usize, value: i32) {
        self.0[index].store(value, Ordering::Relaxed)
    }
}
