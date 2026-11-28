//! The basin graph of lake routing and its minimum spanning tree (Cordonnier, Bovy & Braun
//! 2019). Every pair of 8-neighbours in different basins is an edge weighted by its pass height
//! max(h_a, h_b). Edges are compared by (height, cell, neighbour), one 128-bit key, so no two
//! compare equal and the minimum spanning tree is unique. Boruvka's algorithm builds it: every
//! round each component takes its lightest edge to another component, and edges inside the
//! merged components are dropped. Each thread keeps the edges of its own rows throughout.
//! The tree is then oriented from the sea (basin 0) outwards; components that never reach the
//! sea are rooted at their lowest pit.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use crate::grid::Grid;
use crate::team::{each_mut, parts, rows_mut, span, spans, spans_exact};

pub const SEA: u32 = 0;
const FORWARD: [(isize, isize); 4] = [(0, 1), (1, 1), (1, 0), (1, -1)];
const NONE: u128 = u128::MAX;

/// An edge of the basin graph: the pass height (as ordered bits) and its two cells.
#[derive(Clone, Copy)]
pub struct Edge {
    pub bits: u64,
    pub cell: u32,
    pub other: u32,
}

/// A tree edge with the basins on its two sides.
#[derive(Clone, Copy)]
pub struct TreeEdge {
    pub edge: Edge,
    pub here: u32,
    pub there: u32,
}

/// The bits of a float, mapped so that unsigned order is the IEEE total order.
pub fn ordered_bits(value: f64) -> u64 {
    let bits = value.to_bits();
    if bits >> 63 == 1 {
        !bits
    } else {
        bits | (1u64 << 63)
    }
}

fn from_ordered_bits(bits: u64) -> f64 {
    f64::from_bits(if bits >> 63 == 1 { bits & !(1u64 << 63) } else { !bits })
}

impl Edge {
    #[inline(always)]
    pub fn key(&self) -> u128 {
        (self.bits as u128) << 64 | (self.cell as u128) << 32 | self.other as u128
    }

    fn from_key(key: u128) -> Edge {
        Edge { bits: (key >> 64) as u64, cell: (key >> 32) as u32, other: key as u32 }
    }

    pub fn height(&self) -> f64 {
        from_ordered_bits(self.bits)
    }

    #[inline(always)]
    fn sides(&self, basin: &[i32]) -> (u32, u32) {
        (basin[self.cell as usize] as u32, basin[self.other as usize] as u32)
    }
}

fn visit_pairs<F: FnMut(usize, usize)>(grid: &Grid, basin: &[i32], rows: std::ops::Range<usize>, mut visit: F) {
    for row in rows {
        for column in 0..grid.columns {
            let cell = row * grid.columns + column;
            let here = basin[cell];
            if here < 0 {
                continue;
            }
            for (row_step, column_step) in FORWARD.iter() {
                let other_row = row as isize + row_step;
                let other_column = column as isize + column_step;
                if other_row >= grid.rows as isize || other_column < 0 || other_column >= grid.columns as isize {
                    continue;
                }
                let other = other_row as usize * grid.columns + other_column as usize;
                let there = basin[other];
                if there >= 0 && there != here {
                    visit(cell, other);
                }
            }
        }
    }
}

/// The edges between basins in one list per thread, made from runs of whole rows chosen so the
/// lists hold about as many edges each, with each list's lightest edge for every basin
/// (Boruvka's first scan, done while the edges are made). `basin` is -1 on no-data.
pub fn basin_edges(grid: &Grid, heights: &[f64], basin: &[i32], nodes: usize, threads: usize) -> Vec<(Vec<Edge>, Vec<u128>)> {
    let groups = parts(grid.count(), threads).min(grid.rows);
    let mut per_row = vec![0usize; grid.rows];
    rows_mut(&mut per_row, 1, threads, |first, block| {
        for (offset, value) in block.iter_mut().enumerate() {
            let row = first + offset;
            visit_pairs(grid, basin, row..row + 1, |_, _| *value += 1);
        }
    });
    let total: usize = per_row.iter().sum();
    let mut bounds = vec![0usize];
    let mut running = 0usize;
    for (row, found) in per_row.iter().enumerate() {
        running += found;
        if bounds.len() < groups && running * groups >= total * bounds.len() && row + 1 < grid.rows {
            bounds.push(row + 1);
        }
    }
    bounds.push(grid.rows);
    let per_row: &[usize] = &per_row;
    let bounds: &[usize] = &bounds;
    spans_exact(bounds.len() - 1, bounds.len() - 1, |_, which| {
        let rows = bounds[which.start]..bounds[which.end];
        let mut found = Vec::with_capacity(per_row[rows.clone()].iter().sum());
        let mut best = vec![NONE; nodes];
        visit_pairs(grid, basin, rows, |cell, other| {
            let height = if heights[cell] >= heights[other] { heights[cell] } else { heights[other] };
            let edge = Edge { bits: ordered_bits(height), cell: cell as u32, other: other as u32 };
            let key = edge.key();
            for slot in [basin[cell] as usize, basin[other] as usize] {
                if key < best[slot] {
                    best[slot] = key;
                }
            }
            found.push(edge);
        });
        (found, best)
    })
}

/// Boruvka's algorithm over the per-thread edge lists; returns the tree edges.
/// Components are numbered 0..count every round. Each takes its lightest outgoing edge and
/// points at the component across it; since all keys differ, the only cycles of these pointers
/// are pairs that chose the same edge, and the lower-numbered one of a pair becomes the root.
/// Pointer jumping then finds every component's new root (Chung & Condon 1996). Every step
/// runs in spans whose results do not depend on the thread count.
/// The edge lists come with their first scan done (`basin_edges`); later scans are made in the
/// same pass that drops the edges inside merged components.
pub fn boruvka(mut edge_parts: Vec<(Vec<Edge>, Vec<u128>)>, basin: &[i32], nodes: usize, threads: usize) -> Vec<TreeEdge> {
    let mut component: Vec<u32> = (0..nodes as u32).collect();
    let mut count = nodes;
    let mut chosen = Vec::new();
    while edge_parts.iter().any(|(part, _)| !part.is_empty()) {
        let component_now: &[u32] = &component;
        let side = |node: u32| component_now[node as usize] as usize;
        let partial: Vec<&Vec<u128>> = edge_parts.iter().map(|(_, best)| best).collect();
        let mut best = vec![NONE; count];
        rows_mut(&mut best, 1, threads, |first, block| {
            for (offset, value) in block.iter_mut().enumerate() {
                *value = partial.iter().map(|found| found[first + offset]).min().unwrap_or(NONE);
            }
        });
        let best_now: &[u128] = &best;
        let mut target = vec![0u32; count];
        let taken = Mutex::new(Vec::new());
        rows_mut(&mut target, 1, threads, |first, block| {
            let mut found = Vec::new();
            for (offset, value) in block.iter_mut().enumerate() {
                let index = first + offset;
                let key = best_now[index];
                if key == NONE {
                    *value = index as u32;
                    continue;
                }
                let edge = Edge::from_key(key);
                let (here_basin, there_basin) = edge.sides(basin);
                let (here, there) = (side(here_basin), side(there_basin));
                let partner = if here == index { there } else { here };
                let mutual = best_now[partner] == key;
                *value = if mutual && index < partner { index as u32 } else { partner as u32 };
                if !mutual || index < partner {
                    found.push(TreeEdge { edge, here: here_basin, there: there_basin });
                }
            }
            taken.lock().expect("chosen edges").push((first, found));
        });
        let mut taken = taken.into_inner().expect("chosen edges");
        if taken.iter().all(|(_, found)| found.is_empty()) {
            break;
        }
        taken.sort_by_key(|(first, _)| *first);
        chosen.extend(taken.into_iter().flat_map(|(_, found)| found));
        let mut jumped = vec![0u32; count];
        loop {
            let current: &[u32] = &target;
            let moved = AtomicBool::new(false);
            rows_mut(&mut jumped, 1, threads, |first, block| {
                let mut changed = false;
                for (offset, value) in block.iter_mut().enumerate() {
                    *value = current[current[first + offset] as usize];
                    changed |= *value != current[first + offset];
                }
                if changed {
                    moved.store(true, Ordering::Relaxed);
                }
            });
            std::mem::swap(&mut target, &mut jumped);
            if !moved.into_inner() {
                break;
            }
        }
        let target_now: &[u32] = &target;
        let roots_per_span = spans(count, threads, |_, range| range.filter(|index| target_now[*index] as usize == *index).count() as u32);
        let span_count = roots_per_span.len();
        let mut first_number = Vec::with_capacity(span_count);
        let mut running = 0u32;
        for found in roots_per_span.iter() {
            first_number.push(running);
            running += *found;
        }
        let mut numbered = vec![u32::MAX; count];
        rows_mut(&mut numbered, 1, threads, |first, block| {
            let part = (0..span_count).find(|part| span(count, span_count, *part).start == first).unwrap_or(0);
            let mut next = first_number[part];
            for (offset, value) in block.iter_mut().enumerate() {
                if target_now[first + offset] as usize == first + offset {
                    *value = next;
                    next += 1;
                }
            }
        });
        let numbered_now: &[u32] = &numbered;
        rows_mut(&mut component, 1, threads, |_, block| {
            for value in block.iter_mut() {
                *value = numbered_now[target_now[*value as usize] as usize];
            }
        });
        count = running as usize;
        let component_now: &[u32] = &component;
        each_mut(&mut edge_parts, |(part, best)| {
            best.clear();
            best.resize(count, NONE);
            part.retain(|edge| {
                let (here, there) = edge.sides(basin);
                let (here, there) = (component_now[here as usize] as usize, component_now[there as usize] as usize);
                if here == there {
                    return false;
                }
                let key = edge.key();
                for slot in [here, there] {
                    if key < best[slot] {
                        best[slot] = key;
                    }
                }
                true
            })
        });
    }
    chosen
}

/// A tree edge seen from one end: the basin across it, the pass cells on that basin's side and
/// on this side, and the pass height.
#[derive(Clone, Copy)]
struct Step {
    to: u32,
    inside: u32,
    across: u32,
    height: f64,
}

pub struct Tree {
    pub parent: Vec<u32>,
    pub pass: Vec<(u32, u32)>,
    pub level: Vec<f64>,
    pub lake_of: Vec<u32>,
}

/// Orients the tree: parent, pass (cell on the child's side, cell across), water level and the
/// basin whose own pass sets that level, for every basin. In a tree each basin has one neighbour
/// nearer the root, so the result does not depend on the order of the tree edges.
pub fn orient(heights: &[f64], pit: &[u32], tree_edges: &[TreeEdge], nodes: usize) -> Tree {
    let mut tree = Tree { parent: vec![u32::MAX; nodes], pass: vec![(u32::MAX, u32::MAX); nodes], level: vec![f64::NEG_INFINITY; nodes], lake_of: (0..nodes as u32).collect() };
    let mut start = vec![0u32; nodes + 1];
    for edge in tree_edges.iter() {
        start[edge.here as usize + 1] += 1;
        start[edge.there as usize + 1] += 1;
    }
    for node in 0..nodes {
        start[node + 1] += start[node];
    }
    let mut fill = start.clone();
    let mut adjacency = vec![Step { to: 0, inside: 0, across: 0, height: 0.0 }; 2 * tree_edges.len()];
    for tree_edge in tree_edges.iter() {
        let edge = &tree_edge.edge;
        let height = edge.height();
        for (from, to) in [(tree_edge.here, tree_edge.there), (tree_edge.there, tree_edge.here)] {
            let (inside, across) = if tree_edge.here == to { (edge.cell, edge.other) } else { (edge.other, edge.cell) };
            adjacency[fill[from as usize] as usize] = Step { to, inside, across, height };
            fill[from as usize] += 1;
        }
    }
    let mut visited = vec![false; nodes];
    let mut queue: Vec<u32> = Vec::with_capacity(nodes);
    let mut walk = |root: u32, tree: &mut Tree, visited: &mut Vec<bool>| {
        visited[root as usize] = true;
        queue.clear();
        queue.push(root);
        let mut head = 0usize;
        while head < queue.len() {
            let node = queue[head] as usize;
            head += 1;
            let above = tree.level[node];
            let lake_above = tree.lake_of[node];
            for step in adjacency[start[node] as usize..start[node + 1] as usize].iter() {
                let child = step.to as usize;
                if visited[child] {
                    continue;
                }
                visited[child] = true;
                tree.parent[child] = node as u32;
                tree.pass[child] = (step.inside, step.across);
                let own = step.height >= above;
                tree.level[child] = if own { step.height } else { above };
                tree.lake_of[child] = if own { step.to } else { lake_above };
                queue.push(step.to);
            }
        }
    };
    walk(SEA, &mut tree, &mut visited);
    let mut closed: Vec<u32> = (1..nodes as u32).filter(|node| !visited[*node as usize]).collect();
    closed.sort_by(|a, b| heights[pit[*a as usize] as usize].total_cmp(&heights[pit[*b as usize] as usize]).then(a.cmp(b)));
    for root in closed {
        if !visited[root as usize] {
            tree.level[root as usize] = heights[pit[root as usize] as usize];
            walk(root, &mut tree, &mut visited);
        }
    }
    tree
}
