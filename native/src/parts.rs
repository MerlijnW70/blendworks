//! The fixed partition of the threads: contiguous spans whose bounds depend only on the length
//! and the thread count, and scoped runs that give each span one thread for a single pass.

use std::ops::Range;

/// The fewest items worth a thread of their own: below this the cost of starting and joining a
/// thread outweighs the work.
pub const MIN_ITEMS_PER_THREAD: usize = 16384;

/// The span of part `index` when `len` items are split into `parts` contiguous parts.
pub fn span(len: usize, parts: usize, index: usize) -> Range<usize> {
    let base = len / parts;
    let extra = len % parts;
    let start = index * base + index.min(extra);
    start..start + base + usize::from(index < extra)
}

/// How many threads `len` items of light work get: at most `threads`, and at least
/// `MIN_ITEMS_PER_THREAD` items each.
pub fn parts(len: usize, threads: usize) -> usize {
    threads.max(1).min((len / MIN_ITEMS_PER_THREAD).max(1))
}

/// Splits `data`, made of rows of `width` items, into one block of whole rows per thread and
/// runs `work(first_row, block)` on each.
pub fn rows_mut<T, F>(data: &mut [T], width: usize, threads: usize, work: F)
where
    T: Send,
    F: Fn(usize, &mut [T]) + Sync,
{
    let rows = if width == 0 { 0 } else { data.len() / width };
    let parts = parts(data.len(), threads).min(rows.max(1));
    if parts == 1 {
        work(0, data);
        return;
    }
    let work = &work;
    std::thread::scope(|scope| {
        let mut rest = data;
        let mut handles = Vec::new();
        for index in 0..parts {
            let rows_here = span(rows, parts, index);
            let (block, tail) = rest.split_at_mut(rows_here.len() * width);
            rest = tail;
            if index + 1 == parts {
                work(rows_here.start, block);
            } else {
                handles.push(scope.spawn(move || work(rows_here.start, block)));
            }
        }
        for handle in handles {
            if let Err(payload) = handle.join() {
                std::panic::resume_unwind(payload);
            }
        }
    });
}

/// Runs `work(index, span)` for each of `parts(len, threads)` spans of `len` light items and
/// collects the results in span order.
pub fn spans<R, F>(len: usize, threads: usize, work: F) -> Vec<R>
where
    R: Send,
    F: Fn(usize, Range<usize>) -> R + Sync,
{
    spans_exact(len, parts(len, threads), work)
}

/// Runs `work(index, span)` for exactly `parts` spans of `len` items, for items heavy enough to
/// split however few they are.
pub fn spans_exact<R, F>(len: usize, parts: usize, work: F) -> Vec<R>
where
    R: Send,
    F: Fn(usize, Range<usize>) -> R + Sync,
{
    let parts = parts.max(1);
    if parts == 1 {
        return vec![work(0, 0..len)];
    }
    let work = &work;
    std::thread::scope(|scope| {
        let handles: Vec<_> = (1..parts).map(|index| scope.spawn(move || work(index, span(len, parts, index)))).collect();
        let mut results = vec![work(0, span(len, parts, 0))];
        for handle in handles {
            match handle.join() {
                Ok(result) => results.push(result),
                Err(payload) => std::panic::resume_unwind(payload),
            }
        }
        results
    })
}

/// Copies `source` into `target` with one span per thread.
pub fn copy_into<T: Copy + Send + Sync>(source: &[T], target: &mut [T], threads: usize) {
    rows_mut(target, 1, threads, |first, block| block.copy_from_slice(&source[first..first + block.len()]));
}

/// True when `valid(i)` holds for every index below `len`, checked one span per thread.
pub fn all_of<F: Fn(usize) -> bool + Sync>(len: usize, threads: usize, valid: F) -> bool {
    spans(len, threads, |_, range| range.into_iter().all(|index| valid(index))).into_iter().all(|found| found)
}

/// Runs `work(item)` on one thread per item, for items that are already one thread's share.
pub fn each_mut<T, F>(items: &mut [T], work: F)
where
    T: Send,
    F: Fn(&mut T) + Sync,
{
    if items.len() <= 1 {
        for item in items.iter_mut() {
            work(item);
        }
        return;
    }
    let work = &work;
    std::thread::scope(|scope| {
        let (first, rest) = items.split_first_mut().expect("at least two items");
        let handles: Vec<_> = rest.iter_mut().map(|item| scope.spawn(move || work(item))).collect();
        work(first);
        for handle in handles {
            if let Err(payload) = handle.join() {
                std::panic::resume_unwind(payload);
            }
        }
    });
}

/// Splits two buffers of rows (`width_a` and `width_b` items per row) the same way and runs
/// `work(first_row, block_a, block_b)` on each pair of blocks.
pub fn rows_mut2<A, B, F>(a: &mut [A], width_a: usize, b: &mut [B], width_b: usize, threads: usize, work: F)
where
    A: Send,
    B: Send,
    F: Fn(usize, &mut [A], &mut [B]) + Sync,
{
    let rows = if width_a == 0 { 0 } else { a.len() / width_a };
    let parts = parts(a.len(), threads).min(rows.max(1));
    let mut blocks: Vec<(usize, &mut [A], &mut [B])> = Vec::with_capacity(parts);
    let (mut rest_a, mut rest_b) = (a, b);
    for index in 0..parts {
        let rows_here = span(rows, parts, index);
        let (block_a, tail_a) = rest_a.split_at_mut(rows_here.len() * width_a);
        let (block_b, tail_b) = rest_b.split_at_mut(rows_here.len() * width_b);
        rest_a = tail_a;
        rest_b = tail_b;
        blocks.push((rows_here.start, block_a, block_b));
    }
    each_mut(&mut blocks, |(first, block_a, block_b)| work(*first, block_a, block_b));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spans_cover_the_range_in_order_without_gaps() {
        for len in [0usize, 1, 7, 64, 1000] {
            for parts in 1..9 {
                let mut next = 0;
                for index in 0..parts {
                    let range = span(len, parts, index);
                    assert_eq!(range.start, next);
                    next = range.end;
                }
                assert_eq!(next, len);
            }
        }
    }
}
