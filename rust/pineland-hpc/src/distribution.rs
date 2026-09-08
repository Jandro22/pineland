use pineland_core::json::JsonValue;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeterministicPartition {
    pub particle_count: usize,
    pub rank_count: usize,
    pub owners: Vec<usize>,
    pub ranges: Vec<(usize, usize)>,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParentTransfer {
    pub source_rank: usize,
    pub destination_rank: usize,
    pub child_particle: usize,
    pub parent_particle: usize,
}

pub fn canonical_owner(particle: usize, particle_count: usize, rank_count: usize) -> usize {
    if rank_count == 0 || particle_count == 0 {
        0
    } else {
        ((particle as u128 * rank_count as u128) / particle_count as u128) as usize
    }
}
impl DeterministicPartition {
    pub fn new(particle_count: usize, rank_count: usize) -> Self {
        let rank_count = rank_count.max(1);
        let mut owners = Vec::with_capacity(particle_count);
        for p in 0..particle_count {
            owners.push(canonical_owner(p, particle_count, rank_count))
        }
        let mut ranges = Vec::with_capacity(rank_count);
        for rank in 0..rank_count {
            // The owner formula above partitions the logical index space at
            // ceil(rank * N / R).  Use the same boundaries here; floor-based
            // ranges disagree for uneven N/R and silently put a particle on
            // a different rank than its migration plan.
            let start = (rank as u128 * particle_count as u128).div_ceil(rank_count as u128);
            let end = ((rank + 1) as u128 * particle_count as u128).div_ceil(rank_count as u128);
            ranges.push((start as usize, end as usize));
        }
        Self {
            particle_count,
            rank_count,
            owners,
            ranges,
        }
    }
    pub fn rank_particles(&self, rank: usize) -> std::ops::Range<usize> {
        let (start, end) = self.ranges.get(rank).copied().unwrap_or((0, 0));
        start..end
    }
    pub fn transfer_plan(&self, parents: &[usize]) -> Vec<ParentTransfer> {
        parents
            .iter()
            .enumerate()
            .filter_map(|(child, parent)| {
                if *parent >= self.particle_count || child >= self.particle_count {
                    return None;
                }
                let source = self.owners[*parent];
                let destination = self.owners[child];
                Some(ParentTransfer {
                    source_rank: source,
                    destination_rank: destination,
                    child_particle: child,
                    parent_particle: *parent,
                })
            })
            .collect()
    }
    pub fn to_json(&self) -> JsonValue {
        let mut o = JsonValue::object();
        o.insert(
            "particle_count",
            JsonValue::integer(self.particle_count as u64),
        );
        o.insert("rank_count", JsonValue::integer(self.rank_count as u64));
        let mut owners = JsonValue::Array(Vec::new());
        if let JsonValue::Array(v) = &mut owners {
            for x in &self.owners {
                v.push(JsonValue::integer(*x as u64))
            }
        }
        o.insert("owners", owners);
        o
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ownership_and_ranges_cover_logical_particles() {
        let partition = DeterministicPartition::new(17, 4);
        let mut covered = Vec::new();
        for rank in 0..4 {
            let range = partition.rank_particles(rank);
            assert!(range
                .clone()
                .all(|particle| partition.owners[particle] == rank));
            covered.extend(range);
        }
        assert_eq!(covered, (0..17).collect::<Vec<_>>());
        assert!(partition.owners.iter().all(|owner| *owner < 4));
    }
    #[test]
    fn transfer_buckets_are_canonical() {
        let partition = DeterministicPartition::new(8, 2);
        let buckets = crate::migration::alltoallv_buckets(&partition, &[7, 0, 3, 3, 6, 1, 5, 2]);
        let mut children = buckets
            .iter()
            .flatten()
            .map(|item| item.child_particle)
            .collect::<Vec<_>>();
        children.sort_unstable();
        assert_eq!(children, (0..8).collect::<Vec<_>>());
    }
}
