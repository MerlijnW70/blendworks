//! The C ABI, and the only module with unsafe code. Every entry point checks each buffer
//! descriptor's element type, length, contiguity, alignment, writability and overlap with the
//! other buffers of the call before it makes a slice of it, runs the kernel inside
//! `catch_unwind` so that no panic crosses the boundary, and returns 0 or an error code whose
//! message `bw_last_error` copies out. The kernels then check lengths against the grid.
//! `entries` holds the exported kernel functions, `views` the shared views of output buffers.

#![deny(unsafe_op_in_unsafe_fn)]

mod entries;
pub mod views;

use std::cell::RefCell;
use std::ffi::c_void;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr::NonNull;

use crate::error::{KernelError, KernelResult, PANIC};
use crate::grid::Grid;
use crate::team::{check_threads, panic_text};

pub const ABI_VERSION: u32 = 2;
pub const KIND_F64: u32 = 1;
pub const KIND_I32: u32 = 3;

#[repr(C)]
pub struct BwBuffer {
    pub data: *mut c_void,
    pub len: u64,
    pub kind: u32,
    pub item_size: u32,
    pub contiguous: u32,
    pub writable: u32,
}

#[repr(C)]
pub struct BwGrid {
    pub rows: i64,
    pub columns: i64,
    pub spacing_x: f64,
    pub spacing_y: f64,
    pub edges: i64,
}

thread_local! {
    static LAST_ERROR: RefCell<String> = RefCell::new(String::new());
}

fn remember(message: String) {
    LAST_ERROR.with(|last| *last.borrow_mut() = message);
}

pub fn guarded<F: FnOnce() -> KernelResult<()>>(work: F) -> i32 {
    match catch_unwind(AssertUnwindSafe(work)) {
        Ok(Ok(())) => {
            remember(String::new());
            0
        }
        Ok(Err(error)) => {
            remember(error.message);
            error.code
        }
        Err(payload) => {
            remember(format!("internal error in the native core: {}", panic_text(&*payload)));
            PANIC
        }
    }
}

#[derive(Clone, Copy)]
struct Region {
    start: usize,
    bytes: usize,
    mutable: bool,
}

pub struct Buffers {
    taken: Vec<Region>,
}

impl Buffers {
    pub fn new() -> Self {
        Buffers { taken: Vec::new() }
    }

    fn claim(&mut self, name: &str, start: usize, bytes: usize, mutable: bool) -> KernelResult<()> {
        for other in self.taken.iter() {
            let overlap = bytes > 0 && other.bytes > 0 && start < other.start + other.bytes && other.start < start + bytes;
            if overlap && (mutable || other.mutable) {
                return Err(KernelError::invalid(format!("{} overlaps another buffer of the call", name)));
            }
        }
        self.taken.push(Region { start, bytes, mutable });
        Ok(())
    }

    unsafe fn check(&mut self, name: &str, buffer: *const BwBuffer, kind: u32, mutable: bool) -> KernelResult<(usize, usize)> {
        if buffer.is_null() || (buffer as usize) % std::mem::align_of::<BwBuffer>() != 0 {
            return Err(KernelError::invalid(format!("{} is a null or misaligned buffer descriptor", name)));
        }
        let descriptor = unsafe { &*buffer };
        let (wanted, size) = if kind == KIND_F64 { ("float64", 8u32) } else { ("int32", 4u32) };
        if descriptor.kind != kind || descriptor.item_size != size {
            return Err(KernelError::invalid(format!("{} must be {} ({} bytes), got kind {} with {} bytes", name, wanted, size, descriptor.kind, descriptor.item_size)));
        }
        if descriptor.contiguous != 1 {
            return Err(KernelError::invalid(format!("{} must be C-contiguous", name)));
        }
        if mutable && descriptor.writable != 1 {
            return Err(KernelError::invalid(format!("{} must be writable", name)));
        }
        let len = usize::try_from(descriptor.len).map_err(|_| KernelError::invalid(format!("{} is too long", name)))?;
        let bytes = len.checked_mul(size as usize).filter(|bytes| *bytes <= isize::MAX as usize).ok_or_else(|| KernelError::invalid(format!("{} is too long", name)))?;
        let start = descriptor.data as usize;
        if len > 0 {
            if start == 0 {
                return Err(KernelError::invalid(format!("{} has {} values but a null data pointer", name, len)));
            }
            if start % size as usize != 0 {
                return Err(KernelError::invalid(format!("{} is not aligned to {} bytes", name, size)));
            }
            if start.checked_add(bytes).is_none() {
                return Err(KernelError::invalid(format!("{} wraps around the address space", name)));
            }
        }
        self.claim(name, start, bytes, mutable)?;
        Ok((start, len))
    }

    /// # Safety
    /// The descriptor, if not null, must describe memory that stays valid, and is not used
    /// elsewhere, for the rest of the call.
    pub unsafe fn f64s<'a>(&mut self, name: &str, buffer: *const BwBuffer) -> KernelResult<&'a [f64]> {
        let (start, len) = unsafe { self.check(name, buffer, KIND_F64, false) }?;
        Ok(unsafe { std::slice::from_raw_parts(pointer::<f64>(start, len), len) })
    }

    /// # Safety
    /// The descriptor, if not null, must describe memory that stays valid, and is not used
    /// elsewhere, for the rest of the call.
    pub unsafe fn f64s_mut<'a>(&mut self, name: &str, buffer: *const BwBuffer) -> KernelResult<&'a mut [f64]> {
        let (start, len) = unsafe { self.check(name, buffer, KIND_F64, true) }?;
        Ok(unsafe { std::slice::from_raw_parts_mut(pointer::<f64>(start, len), len) })
    }

    /// # Safety
    /// The descriptor, if not null, must describe memory that stays valid, and is not used
    /// elsewhere, for the rest of the call.
    pub unsafe fn i32s<'a>(&mut self, name: &str, buffer: *const BwBuffer) -> KernelResult<&'a [i32]> {
        let (start, len) = unsafe { self.check(name, buffer, KIND_I32, false) }?;
        Ok(unsafe { std::slice::from_raw_parts(pointer::<i32>(start, len), len) })
    }

    /// # Safety
    /// The descriptor, if not null, must describe memory that stays valid, and is not used
    /// elsewhere, for the rest of the call.
    pub unsafe fn i32s_mut<'a>(&mut self, name: &str, buffer: *const BwBuffer) -> KernelResult<&'a mut [i32]> {
        let (start, len) = unsafe { self.check(name, buffer, KIND_I32, true) }?;
        Ok(unsafe { std::slice::from_raw_parts_mut(pointer::<i32>(start, len), len) })
    }

    /// # Safety
    /// The pointer, if not null, must point to memory that stays valid for the rest of the call.
    pub unsafe fn scalar<'a>(&mut self, name: &str, value: *mut i64) -> KernelResult<&'a mut i64> {
        let start = value as usize;
        let bytes = std::mem::size_of::<i64>();
        if value.is_null() || start % std::mem::align_of::<i64>() != 0 || start.checked_add(bytes).is_none() {
            return Err(KernelError::invalid(format!("{} must be a valid, aligned pointer", name)));
        }
        self.claim(name, start, bytes, true)?;
        Ok(unsafe { &mut *value })
    }
}

impl Default for Buffers {
    fn default() -> Self {
        Buffers::new()
    }
}

fn pointer<T>(start: usize, len: usize) -> *mut T {
    if len == 0 {
        NonNull::<T>::dangling().as_ptr()
    } else {
        start as *mut T
    }
}

/// Reads a grid description and the thread count.
/// # Safety
/// The pointer, if not null, must point to a `BwGrid` that stays valid for the call.
pub unsafe fn grid_of(grid: *const BwGrid, threads: i64) -> KernelResult<(Grid, usize)> {
    if grid.is_null() || (grid as usize) % std::mem::align_of::<BwGrid>() != 0 {
        return Err(KernelError::invalid("the grid must be a valid, aligned pointer"));
    }
    let given = unsafe { &*grid };
    Ok((Grid::new(given.rows, given.columns, given.spacing_x, given.spacing_y, given.edges)?, check_threads(threads)?))
}

#[no_mangle]
pub extern "C" fn bw_abi_version() -> u32 {
    ABI_VERSION
}

#[no_mangle]
pub extern "C" fn bw_last_error(out: *mut u8, capacity: u64) -> u64 {
    LAST_ERROR.with(|last| {
        let message = last.borrow();
        let bytes = message.as_bytes();
        if !out.is_null() && capacity > 0 {
            let room = usize::try_from(capacity - 1).unwrap_or(usize::MAX).min(bytes.len());
            unsafe {
                std::ptr::copy_nonoverlapping(bytes.as_ptr(), out, room);
                *out.add(room) = 0;
            }
        }
        bytes.len() as u64
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn last_error() -> String {
        let mut text = vec![0u8; 256];
        let size = bw_last_error(text.as_mut_ptr(), text.len() as u64) as usize;
        String::from_utf8_lossy(&text[..size.min(255)]).into_owned()
    }

    #[test]
    fn a_panic_inside_a_kernel_becomes_an_error_code_and_message() {
        let code = guarded(|| panic!("index out of bounds in a kernel"));
        assert_eq!(code, PANIC);
        assert!(last_error().contains("index out of bounds in a kernel"));
        assert_eq!(guarded(|| Ok(())), 0);
        assert_eq!(last_error(), "");
    }

    #[test]
    fn a_panic_in_a_kernel_thread_is_caught_at_the_boundary() {
        let code = guarded(|| crate::team::team(4, |thread, _| if thread == 3 { panic!("thread three failed") } else { Ok(()) }));
        assert_eq!(code, PANIC);
        assert!(last_error().contains("thread three failed"));
    }

    #[test]
    fn null_and_misaligned_pointers_are_refused() {
        let grid = BwGrid { rows: 2, columns: 2, spacing_x: 1.0, spacing_y: 1.0, edges: 31 };
        let mut resolved = 0i64;
        assert_eq!(entries::bw_d8(std::ptr::null(), 1, std::ptr::null(), std::ptr::null(), &mut resolved), crate::error::INVALID_ARGUMENT);
        assert_eq!(entries::bw_d8(&grid, 1, std::ptr::null(), std::ptr::null(), &mut resolved), crate::error::INVALID_ARGUMENT);
        let heights = [1.0f64, 2.0, 3.0, 4.0];
        let receivers = [0i32; 4];
        let heights_buffer = BwBuffer { data: heights.as_ptr() as *mut c_void, len: 4, kind: KIND_F64, item_size: 8, contiguous: 1, writable: 0 };
        let receivers_buffer = BwBuffer { data: receivers.as_ptr() as *mut c_void, len: 4, kind: KIND_I32, item_size: 4, contiguous: 1, writable: 1 };
        assert_eq!(entries::bw_d8(&grid, 1, &heights_buffer, &receivers_buffer, &mut resolved), 0);
        let shifted = BwBuffer { data: (heights.as_ptr() as usize + 4) as *mut c_void, len: 3, kind: KIND_F64, item_size: 8, contiguous: 1, writable: 0 };
        assert_eq!(entries::bw_d8(&grid, 1, &shifted, &receivers_buffer, &mut resolved), crate::error::INVALID_ARGUMENT);
        assert!(last_error().contains("aligned"));
    }
}
