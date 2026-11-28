//! Compiled terrain kernels for Blendworks: flow receivers, the breadth-first receiver queue,
//! accumulation, lake routing, Priority-Flood, implicit stream-power incision, hillslope
//! diffusion and thermal slides. Every kernel is safe Rust on slices; `ffi` is the only module
//! with unsafe code.
#![deny(unsafe_code)]

pub mod accumulate;
pub mod basin_tree;
pub mod diffusion;
pub mod dinf;
pub mod donors;
pub mod error;
#[allow(unsafe_code)]
pub mod ffi;
pub mod flats;
pub mod flood;
pub mod grid;
pub mod incision;
pub mod lakes;
pub mod levels;
pub mod order;
pub mod parts;
pub mod pow;
pub mod receivers;
pub mod shared;
pub mod team;
pub mod thermal;
pub mod threshold;
