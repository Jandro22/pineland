//! Deterministic particle execution helpers.
//!
//! Trajectory-local execution remains serial, while independent particles are
//! executed with a bounded Rayon pool by default.  The fallback uses scoped
//! standard threads for minimal builds and MPI hosts that deliberately disable
//! the optional dependency.  Both backends preserve logical-index order and
//! never derive a particle RNG from worker identity.

pub fn map_indexed<T, R, F>(items: &[T], threads: usize, function: F) -> Vec<R>
where
    T: Sync,
    R: Send,
    F: Fn(usize, &T) -> R + Sync + Send,
{
    #[cfg(feature = "rayon")]
    {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads.max(1).min(items.len().max(1)))
            .build()
            .expect("valid Rayon particle pool");
        pool.install(|| {
            use rayon::prelude::*;
            items
                .par_iter()
                .enumerate()
                .map(|(index, item)| function(index, item))
                .collect()
        })
    }

    #[cfg(not(feature = "rayon"))]
    {
        let _ = threads;
        items
            .iter()
            .enumerate()
            .map(|(index, item)| function(index, item))
            .collect()
    }
}

pub fn for_each_mut<T, F, E>(items: &mut [T], threads: usize, function: F) -> Result<(), E>
where
    T: Send,
    F: Fn(&mut T) -> Result<(), E> + Sync + Send,
    E: Send,
{
    if items.is_empty() {
        return Ok(());
    }

    #[cfg(feature = "rayon")]
    {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads.max(1).min(items.len()))
            .build()
            .expect("valid Rayon particle pool");
        pool.install(|| {
            use rayon::prelude::*;
            items.par_iter_mut().try_for_each(function)
        })
    }

    #[cfg(not(feature = "rayon"))]
    {
        let worker_count = threads.max(1).min(items.len());
        if worker_count == 1 {
            for item in items {
                function(item)?;
            }
            return Ok(());
        }

        let chunk_size = (items.len() + worker_count - 1) / worker_count;
        std::thread::scope(|scope| {
            let mut handles = Vec::with_capacity(worker_count);
            let mut remaining = items;
            for _ in 0..worker_count {
                if remaining.is_empty() {
                    break;
                }
                let take = chunk_size.min(remaining.len());
                let (chunk, tail) = remaining.split_at_mut(take);
                remaining = tail;
                handles.push(scope.spawn(|| {
                    for item in chunk {
                        function(item)?;
                    }
                    Ok::<(), E>(())
                }));
            }

            // Join in chunk order.  All workers run to completion before the
            // first error is returned, so a failed boundary cannot leave another
            // worker mutating a particle after the caller regains control.
            let mut first_error = None;
            for handle in handles {
                match handle.join() {
                    Ok(Ok(())) => {}
                    Ok(Err(error)) if first_error.is_none() => first_error = Some(error),
                    Ok(Err(_)) => {}
                    Err(_) => panic!("parallel particle worker panicked"),
                }
            }
            first_error.map_or(Ok(()), Err)
        })
    }
}

#[cfg(test)]
mod tests {
    use super::for_each_mut;

    #[test]
    fn worker_count_does_not_change_indexed_results() {
        let mut one = (0..257usize).collect::<Vec<_>>();
        let mut many = one.clone();
        for_each_mut(&mut one, 1, |value| {
            *value = value.wrapping_mul(17).wrapping_add(3);
            Ok::<(), ()>(())
        })
        .unwrap();
        for_each_mut(&mut many, 8, |value| {
            *value = value.wrapping_mul(17).wrapping_add(3);
            Ok::<(), ()>(())
        })
        .unwrap();
        assert_eq!(one, many);
    }
}
