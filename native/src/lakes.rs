//! Lake routing by the basin graph and its minimum spanning tree (Cordonnier, Bovy & Braun 2019,
//! "A versatile, linear complexity algorithm for flow routing in topographies with
//! depressions", Earth Surface Dynamics 7:549-562). The single-receiver graph splits the grid
//! into basins, one per root: every root that is an outlet belongs to basin 0 (the sea), every
//! pit gets its own basin, numbered from 1 in ascending cell order. Two basins are joined by
//! every pair of 8-neighbours across their border, weighted by the pass height max(h_a, h_b).
//! Kruskal's algorithm over these edges, sorted by (height, lower basin, higher basin, cell,
//! neighbour), gives the minimum spanning tree, oriented from basin 0 outwards; each basin
//! spills through its tree edge into its parent.
//! filling: the pit's receiver becomes the pass cell on the parent's side.
//! carving: the receivers along the path from the pass cell on the basin's side down to the pit
//! are reversed, and the pass cell drains across the pass.
//! The water level of a basin is max(its pass height, its parent's level), the sea's is -inf;
//! cells below their basin's level are lake cells, labelled by the basin whose own pass sets the
//! level, and that basin's pass is the lake's spill point. Basins that no path joins to the sea
//! (no outlet, or walled in by no-data) are rooted at their lowest pit, which stays a pit.

use crate::basin_tree::{basin_edges, boruvka, orient, Tree, SEA};
use crate::error::{check, KernelError, KernelResult};
use crate::ffi::views::atomic_i32;
use crate::grid::{Grid, INTERIOR, OUTLET};
use crate::team::{rows_mut, rows_mut2, spans, I32View};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Fill,
    Carve,
}

/// The label of a cell whose basin is not known yet.
const UNLABELLED: i32 = i32::MIN;

pub struct Routed {
    pub basins: usize,
    pub lakes: usize,
}

pub struct LakeOutputs<'a> {
    pub receivers: &'a mut [i32],
    pub basin: &'a mut [i32],
    pub lake: &'a mut [i32],
    pub water: &'a mut [f64],
    pub spill: &'a mut [i32],
    pub spill_to: &'a mut [i32],
}

/// Labels every cell with its basin (into `basin`) and returns the pit of every basin. Roots get
/// their label first; then each thread takes a run of rows and follows every unlabelled cell's
/// receivers down to the first labelled cell, writing that label back along the path. A cell's
/// label is its root's, so it does not matter which thread writes it, or how often. Receivers
/// are 8-neighbours here, so the walks stay near the rows being visited.
pub fn label_basins(grid: &Grid, status: &[u8], receivers: &[i32], threads: usize, basin: &mut [i32]) -> KernelResult<Vec<u32>> {
    let count = grid.count();
    let is_pit = |cell: usize| status[cell] == INTERIOR && receivers[cell] < 0;
    let roots = spans(count, threads, |_, cells| {
        let mut found = 0usize;
        for cell in cells {
            let receiver = receivers[cell];
            if receiver < -1 || receiver >= count as i32 || receiver == cell as i32 {
                return Err(KernelError::invalid(format!("cell {} has receiver {}, outside 0..{}, not -1 or itself", cell, receiver, count)));
            }
            if status[cell] != INTERIOR && receiver >= 0 {
                return Err(KernelError::invalid(format!("cell {} is an outlet or no-data and must have no receiver, got {}", cell, receiver)));
            }
            found += usize::from(is_pit(cell));
        }
        Ok(found)
    });
    let roots = roots.into_iter().collect::<KernelResult<Vec<usize>>>()?;
    let mut first_id = Vec::with_capacity(roots.len());
    let mut basins = 0usize;
    for found in roots.iter() {
        first_id.push(basins as u32 + 1);
        basins += found;
    }
    let ids = I32View(atomic_i32(basin));
    let pits = spans(count, threads, |index, cells| {
        let mut next = first_id[index];
        let mut found = Vec::new();
        for cell in cells {
            if is_pit(cell) {
                ids.set(cell, next as i32);
                found.push(cell as u32);
                next += 1;
            } else if status[cell] == OUTLET {
                ids.set(cell, SEA as i32);
            } else if receivers[cell] >= 0 {
                ids.set(cell, UNLABELLED);
            } else {
                ids.set(cell, -1);
            }
        }
        found
    });
    let walked = spans(count, threads, |_, cells| {
        let mut path: Vec<usize> = Vec::new();
        for cell in cells {
            if ids.get(cell) != UNLABELLED {
                continue;
            }
            path.clear();
            let mut current = cell;
            let label = loop {
                let found = ids.get(current);
                if found != UNLABELLED {
                    break found;
                }
                if path.len() == count {
                    return Err(KernelError::cycle(format!("the flow graph has a cycle through cell {}", cell)));
                }
                path.push(current);
                current = receivers[current] as usize;
            };
            for visited in path.iter() {
                ids.set(*visited, label);
            }
        }
        Ok(())
    });
    walked.into_iter().collect::<KernelResult<Vec<()>>>()?;
    let mut pit = vec![u32::MAX];
    pit.extend(pits.into_iter().flatten());
    Ok(pit)
}

pub fn route(grid: &Grid, heights: &[f64], receivers: &[i32], mode: Mode, threads: usize, out: LakeOutputs) -> KernelResult<Routed> {
    let count = grid.count();
    for (name, length) in [("heights", heights.len()), ("receivers", receivers.len()), ("receivers out", out.receivers.len()), ("basin", out.basin.len()), ("lake", out.lake.len()), ("water", out.water.len())] {
        grid.expect_len(name, length, 1)?;
    }
    for (name, length) in [("spill", out.spill.len()), ("spill to", out.spill_to.len())] {
        check(length == count + 1, || format!("{} must hold one value per possible basin, {}, got {}", name, count + 1, length))?;
    }
    let status = grid.status(heights, threads);
    let pit = label_basins(grid, &status, receivers, threads, out.basin)?;
    let basins = pit.len() - 1;
    let basin: &[i32] = out.basin;
    let tree = if basins == 0 {
        orient(heights, &pit, &[], 1)
    } else {
        let tree_edges = boruvka(basin_edges(grid, heights, basin, basins + 1, threads), basin, basins + 1, threads);
        orient(heights, &pit, &tree_edges, basins + 1)
    };
    reroute(receivers, &pit, &tree, mode, threads, out.receivers);
    let columns = grid.columns;
    let flooded = |cell: usize| -> Option<(u32, f64)> {
        let id = basin[cell];
        if id < 0 {
            return None;
        }
        let level = tree.level[id as usize];
        if heights[cell] < level {
            Some((tree.lake_of[id as usize], level))
        } else {
            None
        }
    };
    rows_mut2(out.lake, columns, out.water, columns, threads, |first, lake_block, water_block| {
        for (offset, (lake, water)) in lake_block.iter_mut().zip(water_block.iter_mut()).enumerate() {
            let cell = first * columns + offset;
            match flooded(cell) {
                Some((label, level)) => {
                    *lake = label as i32;
                    *water = level;
                }
                None => {
                    *lake = 0;
                    *water = heights[cell];
                }
            }
        }
    });
    let mut lakes = 0usize;
    rows_mut2(out.spill, 1, out.spill_to, 1, threads, |first, spill_block, across_block| {
        for (offset, (spill, across)) in spill_block.iter_mut().zip(across_block.iter_mut()).enumerate() {
            let child = first + offset;
            let joined = child >= 1 && child <= basins && tree.parent[child] != u32::MAX;
            *spill = if joined { tree.pass[child].0 as i32 } else { -1 };
            *across = if joined { tree.pass[child].1 as i32 } else { -1 };
        }
    });
    for child in 1..=basins {
        if tree.parent[child] != u32::MAX && tree.lake_of[child] == child as u32 {
            lakes += 1;
        }
    }
    Ok(Routed { basins, lakes })
}

/// Carving paths lie each inside its own basin, so the basins are rerouted in parallel.
fn reroute(receivers: &[i32], pit: &[u32], tree: &Tree, mode: Mode, threads: usize, out: &mut [i32]) {
    rows_mut(out, 1, threads, |first, block| block.copy_from_slice(&receivers[first..first + block.len()]));
    let routed = I32View(atomic_i32(out));
    spans(pit.len(), threads, |_, children| {
        for child in children {
            if child == 0 || tree.parent[child] == u32::MAX {
                continue;
            }
            let (inside, across) = tree.pass[child];
            let bottom = pit[child] as usize;
            match mode {
                Mode::Fill => routed.set(bottom, across as i32),
                Mode::Carve => {
                    let mut previous = across as i32;
                    let mut current = inside as usize;
                    loop {
                        let next = receivers[current];
                        routed.set(current, previous);
                        if current == bottom || next < 0 {
                            break;
                        }
                        previous = current as i32;
                        current = next as usize;
                    }
                }
            }
        }
    });
}


#[cfg(test)]
mod tests {
    use super::*;
    use crate::error::CYCLE;

    #[test]
    fn a_receiver_cycle_is_reported_instead_of_walked_forever() {
        let grid = Grid::new(3, 3, 1.0, 1.0, 0).expect("grid");
        let heights = vec![1.0; 9];
        let mut receivers = vec![-1i32; 9];
        receivers[0] = 1;
        receivers[1] = 4;
        receivers[4] = 0;
        receivers[2] = 1;
        let status = grid.status(&heights, 1);
        for threads in [1usize, 3] {
            let mut basin = vec![0i32; 9];
            let error = label_basins(&grid, &status, &receivers, threads, &mut basin).err().expect("a cycle must fail");
            assert_eq!(error.code, CYCLE, "{}", error.message);
        }
    }

    #[test]
    fn every_cell_takes_its_roots_label() {
        let grid = Grid::new(3, 4, 1.0, 1.0, 0).expect("grid");
        let heights = vec![1.0; 12];
        // Two trees: 0 <- 1 <- 2 <- 3 and 11 <- 10 <- 6 <- 5, 7 <- 6; cells 4, 8 and 9 are their own pits.
        let receivers = vec![-1, 0, 1, 2, -1, 6, 10, 6, -1, -1, 11, -1];
        let status = grid.status(&heights, 1);
        for threads in [1usize, 2, 4] {
            let mut basin = vec![0i32; 12];
            let pit = label_basins(&grid, &status, &receivers, threads, &mut basin).expect("labels");
            assert_eq!(pit, vec![u32::MAX, 0, 4, 8, 9, 11]);
            assert_eq!(basin, vec![1, 1, 1, 1, 2, 5, 5, 5, 3, 4, 5, 5], "{} threads", threads);
        }
    }
}