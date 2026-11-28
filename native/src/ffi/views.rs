//! Shared views of buffers a kernel holds exclusively. A level sweep writes a value on one
//! thread and reads it on another after a barrier, so the buffer is viewed as relaxed atomics,
//! which have the same size and bit validity as the plain values; the exclusive borrow
//! guarantees nothing else touches the buffer while the view lives.

use std::sync::atomic::{AtomicI32, AtomicU64};

use crate::error::{KernelError, KernelResult};

pub fn atomic_f64(values: &mut [f64]) -> KernelResult<&[AtomicU64]> {
    if values.as_ptr() as usize % std::mem::align_of::<AtomicU64>() != 0 {
        return Err(KernelError::invalid("a float64 buffer is not aligned for shared use"));
    }
    let len = values.len();
    let start = values.as_mut_ptr() as *const AtomicU64;
    Ok(unsafe { std::slice::from_raw_parts(start, len) })
}

pub fn atomic_i32(values: &mut [i32]) -> &[AtomicI32] {
    let len = values.len();
    let start = values.as_mut_ptr() as *const AtomicI32;
    unsafe { std::slice::from_raw_parts(start, len) }
}
