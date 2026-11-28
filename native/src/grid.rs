//! Grids are row-major, `rows x columns`, with rows growing along +y (south on a map) and
//! columns along +x. A cell whose height is not finite is no-data: it neither drains nor
//! receives. Base level is set by `edges`, a bit mask of the open sides; a valid cell on an
//! open side, or next to a no-data cell when `EDGE_NODATA` is set, is an outlet.

use crate::error::{check, KernelError, KernelResult};

/// Neighbour order as (row step, column step): east, then clockwise.
pub const NEIGHBOURS: [(isize, isize); 8] = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)];
/// The slot of the opposite direction for every slot of `NEIGHBOURS`.
pub const OPPOSITE: [usize; 8] = [4, 5, 6, 7, 0, 1, 2, 3];

pub const EDGE_NORTH: u32 = 1;
pub const EDGE_EAST: u32 = 2;
pub const EDGE_SOUTH: u32 = 4;
pub const EDGE_WEST: u32 = 8;
pub const EDGE_NODATA: u32 = 16;
pub const EDGE_ALL: u32 = 31;

pub const NODATA: u8 = 0;
pub const INTERIOR: u8 = 1;
pub const OUTLET: u8 = 2;

/// The largest grid the kernels accept: cell indices are stored as 32-bit signed integers.
pub const MAX_CELLS: usize = i32::MAX as usize;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Grid {
    pub rows: usize,
    pub columns: usize,
    pub spacing_x: f64,
    pub spacing_y: f64,
    pub edges: u32,
}

impl Grid {
    pub fn new(rows: i64, columns: i64, spacing_x: f64, spacing_y: f64, edges: i64) -> KernelResult<Grid> {
        check(rows >= 1 && columns >= 1, || format!("the grid needs at least one row and one column, got {} x {}", rows, columns))?;
        let count = (rows as u128) * (columns as u128);
        check(count <= MAX_CELLS as u128, || format!("a grid of {} x {} cells is larger than the {} cells the core indexes", rows, columns, MAX_CELLS))?;
        for (name, value) in [("spacing x", spacing_x), ("spacing y", spacing_y)] {
            check(value.is_finite() && value > 0.0, || format!("{} must be a finite number above 0, got {}", name, value))?;
        }
        check((0..=EDGE_ALL as i64).contains(&edges), || format!("edges must be a mask of the bits 1 north, 2 east, 4 south, 8 west and 16 no-data, got {}", edges))?;
        Ok(Grid { rows: rows as usize, columns: columns as usize, spacing_x, spacing_y, edges: edges as u32 })
    }

    pub fn count(&self) -> usize {
        self.rows * self.columns
    }

    pub fn neighbour(&self, cell: usize, slot: usize) -> Option<usize> {
        let (row_step, column_step) = NEIGHBOURS[slot];
        let row = (cell / self.columns) as isize + row_step;
        let column = (cell % self.columns) as isize + column_step;
        if row < 0 || column < 0 || row >= self.rows as isize || column >= self.columns as isize {
            None
        } else {
            Some(row as usize * self.columns + column as usize)
        }
    }

    /// Calls `visit(slot, neighbour)` for every neighbour inside the grid, in slot order.
    #[inline(always)]
    pub fn for_neighbours<F: FnMut(usize, usize)>(&self, cell: usize, mut visit: F) {
        let row = cell / self.columns;
        let column = cell % self.columns;
        if row > 0 && column > 0 && row + 1 < self.rows && column + 1 < self.columns {
            let offsets = self.offsets();
            for (slot, offset) in offsets.iter().enumerate() {
                visit(slot, (cell as isize + offset) as usize);
            }
        } else {
            for slot in 0..8 {
                if let Some(other) = self.neighbour(cell, slot) {
                    visit(slot, other);
                }
            }
        }
    }

    pub fn offsets(&self) -> [isize; 8] {
        let width = self.columns as isize;
        let mut found = [0isize; 8];
        for (slot, (row_step, column_step)) in NEIGHBOURS.iter().enumerate() {
            found[slot] = row_step * width + column_step;
        }
        found
    }

    pub fn distances(&self) -> [f64; 8] {
        let diagonal = (self.spacing_x * self.spacing_x + self.spacing_y * self.spacing_y).sqrt();
        let mut found = [0.0; 8];
        for (slot, (row_step, column_step)) in NEIGHBOURS.iter().enumerate() {
            found[slot] = match (*row_step != 0, *column_step != 0) {
                (true, true) => diagonal,
                (true, false) => self.spacing_y,
                _ => self.spacing_x,
            };
        }
        found
    }

    /// The straight-line distance between the centres of two cells.
    pub fn distance(&self, cell: usize, other: usize) -> f64 {
        let rows = (cell / self.columns) as f64 - (other / self.columns) as f64;
        let columns = (cell % self.columns) as f64 - (other % self.columns) as f64;
        let along_y = rows * self.spacing_y;
        let along_x = columns * self.spacing_x;
        (along_x * along_x + along_y * along_y).sqrt()
    }

    pub fn expect_len(&self, name: &str, len: usize, per_cell: usize) -> KernelResult<()> {
        let wanted = self.count().checked_mul(per_cell).ok_or_else(|| KernelError::invalid("buffer size overflows"))?;
        check(len == wanted, || format!("{} holds {} values, the {} x {} grid needs {}", name, len, self.rows, self.columns, wanted))
    }

    fn on_open_edge(&self, row: usize, column: usize) -> bool {
        (self.edges & EDGE_NORTH != 0 && row == 0)
            || (self.edges & EDGE_SOUTH != 0 && row + 1 == self.rows)
            || (self.edges & EDGE_WEST != 0 && column == 0)
            || (self.edges & EDGE_EAST != 0 && column + 1 == self.columns)
    }

    /// The status of one cell: `NODATA`, `OUTLET` or `INTERIOR`.
    pub fn status_of(&self, heights: &[f64], cell: usize) -> u8 {
        if !heights[cell].is_finite() {
            return NODATA;
        }
        if self.on_open_edge(cell / self.columns, cell % self.columns) {
            return OUTLET;
        }
        if self.edges & EDGE_NODATA != 0 {
            let mut beside_nodata = false;
            self.for_neighbours(cell, |_, other| beside_nodata |= !heights[other].is_finite());
            if beside_nodata {
                return OUTLET;
            }
        }
        INTERIOR
    }

    pub fn status_into(&self, heights: &[f64], status: &mut [u8], threads: usize) {
        let columns = self.columns;
        crate::team::rows_mut(status, columns, threads, |first_row, block| {
            for (offset, value) in block.iter_mut().enumerate() {
                *value = self.status_of(heights, first_row * columns + offset);
            }
        });
    }

    pub fn status(&self, heights: &[f64], threads: usize) -> Vec<u8> {
        let mut status = vec![NODATA; self.count()];
        self.status_into(heights, &mut status, threads);
        status
    }
}

/// The slot of `other` among the neighbours of `cell`, if it is one.
pub fn slot_of(grid: &Grid, cell: usize, other: usize) -> Option<usize> {
    (0..8).find(|slot| grid.neighbour(cell, *slot) == Some(other))
}
